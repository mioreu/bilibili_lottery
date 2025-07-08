import json
import logging
import time
from typing import Dict, Any, Optional
import requests
import urllib3

import api.api_constants as api
from utils.data_extractors import extract_bili_jct, get_dynamic_type_for_repost
from utils.file_operations import save_at_id_to_file, load_at_id

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
api_logger = logging.getLogger("Bilibili.Api")

class BilibiliClient:
    def __init__(self, cookie: str, remark: str):
        """初始化 Bilibili 客户端"""
        self.remark = remark
        self.session = requests.Session()
        self.session.headers.update(api.BASE_HEADERS)
        self.session.headers["Cookie"] = cookie
        self.csrf = extract_bili_jct(cookie) 
        self.is_valid = False
        self.mid = None
        self.uname = None
        self.account_config: Dict[str, Any] = {}

        if not self.csrf:
            api_logger.error(
                f"账号 [{self.remark}] 初始化失败：无法从 Cookie 中提取 bili_jct。请确保 Cookie 完整。"
            )
            return

        # 初始化检查登录状态
        self._check_login_status()

    def _check_login_status(self):
        """检查 Cookie 有效性"""
        api_logger.debug(f"账号 [{self.remark}] 正在执行初始化登录状态检查 (访问 /nav)...")
        try:
            response = self.session.get(
                api.URL_NAV_INFO,
                timeout=15,
                verify=False
            ) 
            response.raise_for_status()

            data = response.json() 
            api_code = data.get("code") 
            api_message = data.get("message", "无信息")

            api_logger.debug(f"账号 [{self.remark}] /nav 接口返回 | Code: {api_code} | Message: {api_message}")

            if api_code == 0:
                user_info = data.get("data", {})
                self.uname = user_info.get("uname", "未知用户名")
                self.mid = user_info.get("mid")
                coin = user_info.get("money", "?")
                level = user_info.get("level_info", {}).get("current_level", "?")
                api_logger.info(
                    f"账号 [{self.remark}] Cookie 验证成功。\n"
                    f"├─ 用户: {self.uname} \n"
                    f"├─ 等级: Lv.{level} \n"
                    f"├─ UID: {self.mid} \n"
                    f"└─ 硬币: {coin}"
                )
                self.is_valid = True
                    
                time.sleep(1)

            else:
                api_logger.error(
                    f"账号 [{self.remark}] 初始化失败：Code: {api_code} | Message: {api_message} | 请检查Cookie有效性"
                )

        except requests.exceptions.Timeout: 
            api_logger.error(f"账号 [{self.remark}] 初始化请求超时: GET {api.URL_NAV_INFO},请检查网络状况")
        except Exception as e:
            api_logger.exception(f"账号 [{self.remark}] 初始化时发生未知错误: {e}")

    def _request(self, method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """通用请求方法"""
        max_retries = 1
        for attempt in range(max_retries): 
            try:
                kwargs.setdefault('verify', False)
                response = self.session.request(
                    method, 
                    url, 
                    timeout=20,
                    **kwargs
                ) 
                response.raise_for_status() 
                data = response.json() 
                if data.get("code") == 0: 
                    return data 
                else:
                    api_logger.debug(
                        f"账号 [{self.remark}] API 请求返回错误: {url} | Code: {data.get('code')} | Message: {data.get('message')} | 尝试 {attempt + 1}/{max_retries}"
                    )
                    return data
            except Exception as e:
                api_logger.debug(
                    f"账号 [{self.remark}] API 请求遇到错误: {url} | 错误: {e}"
                )
                time.sleep(1 + attempt * 2)
        return None

    def follow_user(self, target_uid: int) -> tuple[bool, str]:
        """关注"""

        payload = {
            "fid": target_uid,
            "act": 1,
            "re_src": 11,
            "csrf": self.csrf,
        }
        api_logger.debug(f"账号 [{self.remark}] 尝试关注用户 {target_uid}...")
        data = self._request("POST", api.URL_FOLLOW, data=payload)

        if data and data.get("code") == 0:
            return True, "关注成功"

        else:
            error_msg = data.get("message", "未知错误") if data else "无数据"
            api_logger.error(
                f"账号 [{self.remark}] 关注用户 {target_uid} 失败: {error_msg}"
            )
        return False, error_msg

    def like_dynamic(self, dynamic_id: str) -> tuple[bool, str]:
        """点赞"""
        payload = {
            "dynamic_id": dynamic_id,
            "optype": 1,
            "csrf_token": self.csrf,
            "csrf": self.csrf,
        }
        api_logger.debug(f"账号 [{self.remark}] 尝试点赞动态 {dynamic_id}...")
        data = self._request("POST", api.URL_LIKE_THUMB, data=payload)
        if data and data.get("code") == 0:
            return True, "点赞成功"
        else:
            error_msg = data.get('message', '未知错误') if data else '无数据'
            api_logger.error(
                f"账号 [{self.remark}] 点赞动态 {dynamic_id} 失败: {error_msg}"
            ) 
            return False, error_msg

    def repost_dynamic(self, dynamic_id: str, message: str, url: str) -> tuple[bool, str]:
        """转发"""
        repost_type = get_dynamic_type_for_repost(dynamic_id, url) 

        payload = { 
            "dynamic_id": dynamic_id, 
            "content": message, 
            "type": repost_type,
            "csrf_token": self.csrf, 
            "csrf": self.csrf, 
        }
        api_logger.debug(f"账号 [{self.remark}] 尝试转发动态 {dynamic_id}...") 
        data = self._request("POST", api.URL_REPOST, data=payload)
        if data and data.get("code") == 0:
            return True, "转发成功"
        else:
            error_msg = data.get('message', '未知错误') if data else '无数据'
            api_logger.error( 
                f"账号 [{self.remark}] 转发动态 {dynamic_id} 失败: {error_msg}"
            ) 
            return False, error_msg
            
            
    def comment_dynamic(self, dynamic_id: str, message: str, comment_type, oid) -> tuple[bool, str]:
        """评论"""
        if not oid:
            return False, f"未能获取动态 {dynamic_id} 的评论 OID"

        payload = {
            "oid": oid,
            "type": comment_type, 
            "message": message, 
            "csrf": self.csrf, 
            "csrf_token": self.csrf,  
        }
        api_logger.debug(f"账号 [{self.remark}] 尝试评论动态 {oid} (类型: {comment_type})... 发送评论参数：{json.dumps(payload, ensure_ascii=False)}")
        data = self._request("POST", api.URL_COMMENT, data=payload)
        
        if data and data.get("code") == 0: 
            rpid = str(data["data"]["rpid"])
            return True, f"评论成功\n内容: {message}...\n评论链接: https://www.bilibili.com/opus/{dynamic_id}#reply{rpid}"
        else:
            error_msg = data.get('message', '未知错误') if data else '无数据'
            api_logger.error(
                f"账号 [{self.remark}] 评论动态 {oid} 失败: {error_msg}"
            ) 
            return False, error_msg

    def fetch_dynamic_content(self, dynamic_id: str) -> tuple[bool, str]:
        """获取动态详情"""
        params = {"id": dynamic_id}
        response = self.session.get(
            api.URL_DYNAMIC_CONTENT,
            params=params,
            headers=api.BASE_HEADERS,
            timeout=20,
            verify=False
        )
        if response.status_code == 412:
            raise Exception(f"\nCode: {response.status_code} | 被风控，请稍后再试或更换 【{self.remark}】 账号")

        response.raise_for_status()
        data = response.json()

        if data.get("code") == 0:
            api_logger.debug(f"{data}")
            item = data.get('data', {}).get('item', {})
            modules = item.get('modules', [])

            for module in modules:
                if module.get('module_type') == "MODULE_TYPE_DESC":
                    desc_module = module.get('module_desc', {})
                    rich_text_nodes = desc_module.get('rich_text_nodes', [])

                    text_content = "".join([node.get('text', '')
                                         for node in rich_text_nodes
                                         if node.get('type') == 'RICH_TEXT_NODE_TYPE_TEXT'])
                    if text_content:
                        api_logger.debug(f"提取到动态描述内容: \n{text_content}")
                        return True, text_content
                    else:
                        return False, f"动态 {dynamic_id} 找到描述模块但内容为空"

        else:
            message = data.get('message', '未知错误')
            api_logger.error(f"动态 {dynamic_id} 爬取失败 | Code: {data.get('code')} | Message: {message}")
            return False, message

    def get_at_messages(self, config: Dict[str, Any]) -> tuple[bool, list[dict]]:
        """获取@详情列表"""
        old_at_id = load_at_id(config['file_paths']['history_at_ids'])

        params = {"platform": "web", "build": 0, "mobi_app": "web"}
        response = self.session.get(
            api.URL_CHECK_AT,
            params=params,
            headers=api.BASE_HEADERS,
            timeout=20,
            verify=False
        )
        data = response.json()

        if data.get("code") == 0:
            items = data.get('data', {}).get('items', [])
            at_list = []

            for i in items:
                at_id = str(i.get('id'))
                at_uid = i.get('user', {}).get('mid')
                nickname = i.get('user', {}).get('nickname')
                url = i.get('item', {}).get('uri')
                content = i.get('item', {}).get('source_content')

                if at_id in old_at_id:
                    api_logger.debug(f"@id {at_id} 已在记录中，跳过: {at_id}")
                    continue
                else:
                    at_data = {
                        "id": at_id,
                        "uid": at_uid,
                        "nickname": nickname,
                        "content": content,
                        "url": url
                    }
                    api_logger.debug(f"提取到@详情内容: \n{at_data}")
                    save_at_id_to_file(config['file_paths']['history_at_ids'],at_id)
                    at_list.append(at_data)
            return True, at_list

        else:
            error_msg = data.get('message', '未知错误')
            api_logger.error(f"Code: {data.get('code')} | Message: {error_msg}")
            return False, error_msg