import json
import logging
import time
from typing import Dict, Any, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

api_logger = logging.getLogger("Bilibili.Api")

from utils.data_extractors import extract_bili_jct, get_dynamic_type_for_repost, check_follow_status, \
    get_comment_oid_str


class BilibiliClient:
    """封装 Bilibili API"""

    BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Origin": "https://www.bilibili.com",
    }
    URL_NAV_INFO = "https://api.bilibili.com/x/web-interface/nav"
    URL_LIKE_THUMB = "https://api.vc.bilibili.com/dynamic_like/v1/dynamic_like/thumb"  # 点赞
    URL_REPOST = "https://api.vc.bilibili.com/dynamic_repost/v1/dynamic_repost/repost"  # 转发
    URL_COMMENT = "https://api.bilibili.com/x/v2/reply/add"  # 评论
    URL_FOLLOW = "https://api.bilibili.com/x/relation/modify" # 关注/取关
    URL_DYNAMIC_DETAIL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail" # 获取动态详情
    URL_CHECK_FOLLOW = "https://api.bilibili.com/x/relation" # 检查关注状态


    def __init__(self, cookie: str, remark: str, proxy_config: Optional[Dict[str, str]] = None):
        """
        初始化 Bilibili 客户端
        """
        self.remark = remark
        self.session = requests.Session()
        self.session.headers.update(self.BASE_HEADERS)
        self.session.headers["Cookie"] = cookie
        self.csrf = extract_bili_jct(cookie) 
        self.is_valid = False
        self.mid = None
        self.uname = None
        self.account_config: Dict[str, Any] = {}
        self.proxies = self._validate_and_set_proxy(proxy_config)

        if not self.csrf:
            api_logger.error(
                f"账号 [{self.remark}] 初始化失败：无法从 Cookie 中提取 bili_jct。请确保 Cookie 完整。"
            )
            return

        # 初始化检查登录状态和 Cookie 有效性
        self._check_login_status()

    def _validate_and_set_proxy(self, proxy_config: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """验证并设置代理配置"""
        if not proxy_config or not proxy_config.get("enable"):
            return None

        validated = {}
        allowed_schemes = {
            'http': ['http://', 'socks5://'],
            'https': ['https://', 'socks5://', 'http://']
        }

        for proto in ['http', 'https']:
            if url := proxy_config.get(proto):
                if any(url.startswith(p) for p in allowed_schemes.get(proto, [])):
                    validated[proto] = url
                    display_url = url.split('@')[-1] if '@' in url else url
                    api_logger.debug(f"账号 [{self.remark}] 已配置 {proto.upper()} 代理: {display_url}")
                else:
                    allowed_formats_str = ' 或 '.join(allowed_schemes.get(proto, []))
                    api_logger.warning(f"账号 [{self.remark}] 无效 {proto.upper()} 代理格式: {url[:30]}... (应以 {allowed_formats_str} 开头)。此代理将不会被使用。")

        return validated if validated else None


    def _check_login_status(self):
        """检查 Cookie 有效性并获取用户信息"""
        api_logger.debug(f"账号 [{self.remark}] 正在执行初始化登录状态检查 (访问 /nav)...")
        try:
            response = self.session.get(
                self.URL_NAV_INFO, 
                timeout=15, 
                proxies=self.proxies, 
                verify=False  # 忽略SSL验证
            ) 
            response.raise_for_status() # 检查 HTTP 状态码

            data = response.json() 
            api_code = data.get("code") 
            api_message = data.get("message", "No message") 

            api_logger.debug(f"账号 [{self.remark}] /nav 接口返回 | Code: {api_code} | Message: {api_message}")

            if api_code == 0:
                user_info = data.get("data", {})
                if user_info.get("isLogin"):
                    self.uname = user_info.get("uname", "未知用户名")
                    self.mid = user_info.get("mid")
                    money = user_info.get("money", "?")
                    level = user_info.get("level_info", {}).get("current_level", "?")
                    api_logger.info(
                        f"账号 [{self.remark}] Cookie 验证成功。\n"
                        f"├─ 用户: {self.uname} \n"
                        f"├─ 等级: Lv.{level} \n"
                        f"├─ UID: {self.mid} \n"
                        f"└─ 硬币: {money}"
                    )
                    self.is_valid = True
                    
                    time.sleep(1)
                    
                else:
                    api_logger.error(
                        f"账号 [{self.remark}] 初始化检查失败：API 报告未登录 (isLogin=false)。请检查 Cookie 是否过期或无效。"
                    )
            else:
                api_logger.error(
                    f"账号 [{self.remark}] 初始化检查失败：/nav 接口返回错误 | Code: {api_code} | Message: {api_message}。请检查 Cookie。"
                )

        except requests.exceptions.Timeout: 
            api_logger.error(f"账号 [{self.remark}] 初始化检查请求超时: GET {self.URL_NAV_INFO}")
        except requests.exceptions.RequestException as e: 
            http_status = e.response.status_code if e.response is not None else "N/A"
            api_logger.error(
                f"账号 [{self.remark}] 初始化检查请求错误: GET {self.URL_NAV_INFO} | 状态码: {http_status} | 错误: {e}"
            )
        except Exception as e:
            api_logger.exception(f"账号 [{self.remark}] 初始化检查时发生未知错误: {e}")

    def _request(self, method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """通用请求方法"""
        max_retries = 2
        for attempt in range(max_retries): 
            try:
                # 忽略SSL验证
                kwargs.setdefault('verify', False)
                
                response = self.session.request(
                    method, 
                    url, 
                    timeout=15, 
                    proxies=self.proxies, 
                    **kwargs
                ) 
                response.raise_for_status() 
                data = response.json() 
                if data.get("code") == 0: 
                    return data 
                else:
                    api_logger.warning(
                        f"账号 [{self.remark}] API 请求返回错误: {url} | Code: {data.get('code')} | Message: {data.get('message')} | 尝试 {attempt + 1}/{max_retries}"
                    )
                    return data
            except (requests.exceptions.Timeout, 
                    requests.exceptions.SSLError, 
                    requests.exceptions.ProxyError) as e: 
                api_logger.warning(
                    f"账号 [{self.remark}] API 请求遇到网络错误: {url} | 错误类型: {type(e).__name__} | 尝试 {attempt + 1}/{max_retries} | 错误: {e}"
                )
            except requests.exceptions.RequestException as e: 
                api_logger.debug(
                    f"账号 [{self.remark}] API 请求遇到一般错误: {url} | 错误: {e} | 尝试 {attempt + 1}/{max_retries}"
                )
            except Exception as e:
                api_logger.debug(
                    f"账号 [{self.remark}] API 请求遇到未知错误: {url} | 错误: {e} | 尝试 {attempt + 1}/{max_retries}"
                )
                
            time.sleep(1 + attempt * 2)

        api_logger.error(f"账号 [{self.remark}] API 请求在 {max_retries} 次尝试后失败: {e[:12]}") 
        return None 

    def like_dynamic(self, dynamic_id: str) -> bool:
        """点赞"""
        if not self.is_valid:
            api_logger.warning(f"账号 [{self.remark}] 无效，无法点赞动态 {dynamic_id}。")
            return False


        payload = {
            "dynamic_id": dynamic_id,
            "optype": 1,
            "csrf_token": self.csrf,
            "csrf": self.csrf,
        }
        api_logger.debug(f"账号 [{self.remark}] 尝试点赞动态 {dynamic_id}...")
        data = self._request("POST", self.URL_LIKE_THUMB, data=payload) 
        if data and data.get("code") == 0:
            return True
        else:
            api_logger.error(
                f"账号 [{self.remark}] 点赞动态 {dynamic_id} 失败: {data.get('message', '未知错误') if data else '无数据'}"
            ) 
            return False

    def repost_dynamic(self, dynamic_id: str, message: str, url: str) -> bool: 
        """转发"""
        if not self.is_valid:
            api_logger.warning(f"账号 [{self.remark}] 无效，无法转发动态 {dynamic_id}。") 
            return False
        
        repost_type = get_dynamic_type_for_repost(dynamic_id, url) 
        
        if repost_type is None:
            return False

        payload = { 
            "dynamic_id": dynamic_id, 
            "content": message, 
            "type": repost_type,
            "csrf_token": self.csrf, 
            "csrf": self.csrf, 
        }
        api_logger.debug(f"账号 [{self.remark}] 尝试转发动态 {dynamic_id}...") 
        data = self._request("POST", self.URL_REPOST, data=payload) 
        if data and data.get("code") == 0:
            return True
        else:
            api_logger.error( 
                f"账号 [{self.remark}] 转发动态 {dynamic_id} 失败: {data.get('message', '未知错误') if data else '无数据'}" 
            ) 
            return False 
            
            
    def comment_dynamic(self, dynamic_id: str, message: str, comment_type: int) -> bool: 
        """评论"""
        if not self.is_valid:
            api_logger.warning(f"账号 [{self.remark}] 无效，无法评论动态 {dynamic_id}。")
            return False
            
        oid = get_comment_oid_str(self, dynamic_id)
        
        if not oid:
            api_logger.error(f"账号 [{self.remark}] 未能获取动态 {dynamic_id} 的评论 OID，评论操作中止。")
            return False

        payload = {
            "oid": oid,
            "type": comment_type, 
            "message": message, 
            "csrf": self.csrf, 
            "csrf_token": self.csrf,  
        }
        api_logger.debug(f"账号 [{self.remark}] 尝试评论动态 {oid} (类型: {comment_type})... 发送评论参数：{json.dumps(payload, ensure_ascii=False)}")
        data = self._request("POST", self.URL_COMMENT, data=payload) 
        
        if data and data.get("code") == 0: 
            rpid = str(data["data"]["rpid"])
            return True
        else:
            api_logger.error(
                f"账号 [{self.remark}] 评论动态 {oid} 失败: {data.get('message', '未知错误') if data else '无数据'}"
            ) 
            return False


    def follow_user(self, target_uid: int) -> bool:
        """关注"""
        if not self.is_valid:
            api_logger.warning(f"账号 [{self.remark}] 无效，无法关注用户 {target_uid}。")
            return False
    
        # 先检查关注状态
        status = check_follow_status(self, target_uid)
        
        if status == "is_follow":
            api_logger.info(f"账号 [{self.remark}] 已关注用户 {target_uid}，无需操作。")
            return True
        elif status == "black_user":
            api_logger.warning(f"账号 [{self.remark}] 已拉黑用户 {target_uid}，无法关注。")
            return False
        elif status == "unfollow":
            # 执行关注操作
            payload = {
                "fid": target_uid,
                "act": 1,
                "re_src": 11,
                "csrf": self.csrf,
            }
            api_logger.debug(f"账号 [{self.remark}] 尝试关注用户 {target_uid}...")
            data = self._request("POST", self.URL_FOLLOW, data=payload)
            
            if data and data.get("code") == 0:
                return True
            
            else:
                error_msg = data.get("message", "未知错误") if data else "无数据"
                api_logger.error(
                    f"账号 [{self.remark}] 关注用户 {target_uid} 失败: {error_msg}"
                ) 
            return False
            
        else:
            api_logger.error(f"账号 [{self.remark}] 检查关注状态时遇到未知状态")
            return False

    def fetch_dynamic_content_from_api(self, dynamic_id: str, retry_times: int, timeout: int, headers: Dict[str, str]) -> Optional[str]:
        """获取动态详情"""
        api_logger.debug(f"账号 [{self.remark}] 正在爬取动态 {dynamic_id} 的详情...")
        params = {"id": dynamic_id}
        
        current_headers = self.session.headers.copy()
        current_headers.update(headers)

        for attempt in range(retry_times):
            try:
                response = self.session.get(
                    self.URL_DYNAMIC_DETAIL,
                    params=params,
                    headers=current_headers,
                    timeout=timeout,
                    verify=False,  # 忽略SSL验证
                    proxies=self.proxies
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") == 0:
                    item = data.get("data", {}).get("item")
                    modules = item.get("modules")

                    # 提取文本内容
                    text_content = ""
                    if "module_dynamic" in modules and modules["module_dynamic"].get("desc") and modules["module_dynamic"]["desc"].get("text"):
                        text_content = modules["module_dynamic"]["desc"]["text"]
                    elif "module_word" in modules and modules["module_word"].get("items"):
                        texts = [item.get("text") for item in modules["module_word"]["items"] if item.get("type") == "TEXT"]
                        text_content = "\n".join(texts)
                    else:
                        api_logger.warning(f"动态 {dynamic_id} 详情API返回数据中未能提取到有效文本内容。原始类型: {item.get('type')}")
                        return None

                    return text_content

                else:
                    api_logger.warning(
                        f"动态 {dynamic_id} 详情API返回错误: Code: {data.get('code')} | Message: {data.get('message')} | 尝试 {attempt + 1}/{retry_times}"
                    )

            except (requests.exceptions.Timeout, 
                    requests.exceptions.SSLError, 
                    requests.exceptions.ProxyError) as e:
                # 捕获网络错误并重试
                api_logger.warning(
                    f"爬取动态 {dynamic_id} 详情时遇到网络错误: {type(e).__name__} | 尝试 {attempt + 1}/{retry_times} | 错误: {e}"
                )
            except Exception as e:
                api_logger.exception(f"爬取动态 {dynamic_id} 详情时发生未预期错误: {e}")

            time.sleep(1 + attempt * 2)

        api_logger.error(f"动态 {dynamic_id} 详情在 {retry_times} 次尝试后未能成功爬取。")
        return None