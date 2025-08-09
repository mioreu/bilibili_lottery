import json
import logging
import time
import urllib.parse
from typing import Dict, Any, Optional, Tuple
import requests
import urllib3
from services.wbi_sign import getWbiKeys, encWbi
import api.api_constants as api
from utils.data_extractors import extract_bili_jct
from utils.file_operations import save_at_id_to_file, load_at_id, load_reply_id, save_msg_id_to_file, load_message_id

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
api_logger = logging.getLogger("Bilibili.Api")


class BilibiliClient:
    # 评论状态常量
    STATE_NORMAL = "正常"
    STATE_DELETED = "已删除"
    STATE_SHADOW_BANNED = "仅自己可见（审核通过但仅发布者可见）"
    STATE_API_ERROR = "API错误"

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
        self.img_key, self.sub_key = "", ""
        self._refresh_wbi_keys()  # 初始化时刷新密钥

        if not self.csrf:
            api_logger.error(
                f"账号 [{self.remark}] 初始化失败：无法从 Cookie 中提取 bili_jct。请确保 Cookie 完整"
            )
            return

    def _refresh_wbi_keys(self):
        """刷新WBI签名密钥"""
        # 调用getWbiKeys时传入会话对象
        self.img_key, self.sub_key = getWbiKeys(self.session)
        if not self.img_key or not self.sub_key:
            api_logger.warning(f"账号 [{self.remark}] 刷新WBI密钥失败。部分接口可能无法使用")
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

    def _request(self, method: str, url: str, params: Optional[Dict[str, Any]] = None,
                 data: Optional[Dict[str, Any]] = None, use_wbi: bool = False,
                 **kwargs) -> Optional[Dict[str, Any]]:
        """通用请求方法"""
        max_retries = 1
        for attempt in range(max_retries):
            try:
                # 检查并应用WBI签名
                if use_wbi:
                    if not self.img_key or not self.sub_key:
                        self._refresh_wbi_keys()
                        if not self.img_key or not self.sub_key:
                            api_logger.error(f"账号 [{self.remark}] WBI密钥不可用，无法进行WBI签名")
                            return None

                    # 针对GET请求，签名params
                    if method.upper() == "GET" and params is not None:
                        signed_params = encWbi(params.copy(), self.img_key, self.sub_key)
                        url_with_query = f"{url}?{urllib.parse.urlencode(signed_params)}"
                        response = self.session.request(method, url_with_query, timeout=20, verify=False, **kwargs)
                    # 针对POST请求，签名data
                    elif method.upper() == "POST" and data is not None:
                        signed_data = encWbi(data.copy(), self.img_key, self.sub_key)
                        response = self.session.request(method, url, data=signed_data, timeout=20, verify=False,
                                                        **kwargs)
                    else:
                        api_logger.error(f"账号 [{self.remark}] 尝试对非GET/POST请求或无参数请求使用WBI签名")
                        return None
                else:
                    kwargs.setdefault('verify', False)
                    response = self.session.request(method, url, params=params, data=data, timeout=20, **kwargs)

                response.raise_for_status()
                data = response.json()
                if data.get("code") == 0:
                    return data
                else:
                    api_logger.debug(
                        f"账号 [{self.remark}] API 请求返回错误: {url} | Code: {data.get('code')} | Message: {data.get('message')}"
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
        data = self._request("POST", api.URL_FOLLOW, data=payload)
        api_logger.debug(f"账号 [{self.remark}] 尝试关注用户 {target_uid}...\n返回数据:{data}")
        if data and data.get("code") == 0:
            return True, "关注成功"

        else:
            error_msg = data.get("message", "未知错误") if data else "无数据"
        return False, error_msg

    def like_dynamic(self, dynamic_id: str) -> tuple[bool, str]:
        """点赞动态"""
        payload = {
            "dynamic_id": dynamic_id,
            "optype": 1,
            "csrf_token": self.csrf,
            "csrf": self.csrf,
        }
        data = self._request("POST", api.URL_LIKE_THUMB, data=payload)
        api_logger.debug(f"账号 [{self.remark}] 尝试点赞动态 {dynamic_id}...\n返回数据:{data}")
        if data and data.get("code") == 0:
            return True, "点赞成功"
        else:
            error_msg = data.get('message', '未知错误') if data else '无数据'
            return False, error_msg

    def repost_dynamic(self, dynamic_id: str, message: str, url: str) -> tuple[bool, str]:
        """转发动态"""
        payload = {
            "dynamic_id": dynamic_id,
            "content": message,
            "type": 4,
            "csrf_token": self.csrf,
            "csrf": self.csrf,
        }
        data = self._request("POST", api.URL_REPOST_DYNAMIC, data=payload)
        api_logger.debug(f"账号 [{self.remark}] 尝试转发动态 {url}...\n返回数据:{data}")
        if data and data.get("code") == 0:
            return True, "转发成功"
        else:
            error_msg = data.get('message', '未知错误') if data else '无数据'
            return False, error_msg

    def comment_dynamic(self, dynamic_id: str, message: str, comment_type, oid) -> tuple[bool, str, int]:
        """评论动态"""
        payload = {
            "oid": oid,
            "type": comment_type,
            "message": message,
            "csrf": self.csrf,
            "csrf_token": self.csrf,
        }
        data = self._request("POST", api.URL_COMMENT, data=payload)
        api_logger.debug(
            f"账号 [{self.remark}] 尝试评论动态 {dynamic_id}... \n返回数据:{data}")

        if data and data.get("code") == 0:
            rpid = str(data["data"]["rpid"])
            return True, (f"评论成功\n"
                          f"├─ 内容:{message}\n"
                          f"└─ 评论链接: https://www.bilibili.com/opus/{dynamic_id}#reply{rpid}"), rpid
        else:
            error_msg = data.get('message', '未知错误') if data else '无数据'
            return False, error_msg, ""

    def repost_video(self, aid: int, title: str) -> tuple[bool, str]:
        """转发视频"""
        payload = {"dyn_req": {"content": {"contents": [{"raw_text": "分享视频", "type": 1}]}, "scene": 5},
                   "web_repost_src": {"revs_id": {"dyn_type": 8, "rid": aid}}}
        data = self._request(
            "POST",
            api.URL_REPOST_VIDEO,
            json=payload,
            params={"csrf": self.csrf}
        )
        api_logger.debug(
            f"账号 [{self.remark}] 尝试转发视频  {title} ...\n"
            f"发送数据: {payload}\n返回数据: {data}"
        )

        if data and data.get("code") == 0:
            return True, f" {title} 转发成功"
        else:
            error_msg = data.get('message', '未知错误') if data else '无数据'
            return False, error_msg

    def comment_video(self, aid: int, message: str) -> tuple[bool, str, str]:
        """评论视频"""
        payload = {
            "oid": aid,
            "type": 1,
            "message": message,
            "csrf": self.csrf
        }
        data = self._request("POST", api.URL_COMMENT, data=payload)
        api_logger.debug(
            f"账号 [{self.remark}] 尝试评论视频 https://www.bilibili.com/av{aid} ... \n返回数据:{data}")

        if data and data.get("code") == 0:
            rpid = str(data["data"]["rpid"])
            return True, (f"评论成功\n"
                          f"├─ 内容:{message}\n"
                          f"└─ 评论链接: https://www.bilibili.com/av{aid}#reply{rpid}"), rpid
        else:
            error_msg = data.get('message', '未知错误') if data else '无数据'
            return False, error_msg, ""

    def like_video(self, aid: int) -> tuple[bool, str]:
        """点赞视频"""
        payload = {
            "aid": aid,
            "like": 1,
            "csrf": self.csrf
        }
        data = self._request("POST", api.URL_LIKE_VIDEO, data=payload)
        api_logger.debug(f"账号 [{self.remark}] 尝试点赞视频 av{aid}...\n返回数据:{data}")
        if data and data.get("code") == 0:
            return True, "点赞成功"
        else:
            error_msg = data.get('message', '未知错误') if data else '无数据'
            return False, error_msg

    def fetch_video_detail(self, bvid: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """获取视频详情"""
        params = {"bvid": bvid}
        api_logger.debug(f"发送参数: {params}")
        data = self._request("GET", api.URL_VIDEO_DETAIL, params=params)
        api_logger.debug(f"返回数据: {data}")

        if data.get("code") != 0:
            error_msg = data.get('message', '未知API错误')
            api_logger.error(f"视频 {bvid} 爬取失败 | Code: {data.get('code')} | Message: {error_msg}")
            return False, error_msg
        details = {}
        data = data.get('data')
        aid = data.get('aid')
        title = data.get('title', '')
        desc = data.get('desc', '')
        author_mid = data.get('owner').get('mid')

        content = f"标题:{title}\n简介:{desc}"
        details["video_content"] = content
        details["video_aid"] = aid
        details["mid"] = author_mid
        return True, details

    def fetch_dynamic_content(self, dynamic_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
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
            raise Exception(f"\nCode: 412 | 被风控，请稍后再试或更换 【{self.remark}】 账号")

        response.raise_for_status()
        data = response.json()
        api_logger.debug(f"返回数据: {data}")

        if data.get("code") != 0:
            error_msg = data.get('message', '未知API错误')
            api_logger.error(f"动态 {dynamic_id} 爬取失败 | Code: {data.get('code')} | Message: {error_msg}")
            return False, error_msg, None

        item = data.get('data', {}).get('item', {})
        modules = item.get('modules', [])
        text_content = ""
        module_stat = None
        module_author = None
        details = {}

        # 判断是否为转发动态
        is_forward = any(
            module.get("module_type") == "MODULE_TYPE_DYNAMIC"
            and module.get("module_dynamic", {}).get("type") == "MDL_DYN_TYPE_FORWARD"
            for module in modules
        )
        # 判断是否为互动抽奖
        is_lottery = any(
            module.get("module_type") == "MODULE_TYPE_DESC"
            and any(
                rich_text_node.get("type") == "RICH_TEXT_NODE_TYPE_LOTTERY"
                for rich_text_node in module.get("module_desc", {}).get("rich_text_nodes", [])
            )
            for module in modules
        )

        # 提取动态文本内容, uid, 评论oid, 类型
        for module in modules:
            module_type = module.get('module_type')
            if module_type == "MODULE_TYPE_DESC" and not text_content:
                desc_module = module.get('module_desc', {})
                rich_text_nodes = desc_module.get('rich_text_nodes', [])

                for node in rich_text_nodes:
                    node_type = node.get('type')
                    if node_type == 'RICH_TEXT_NODE_TYPE_TEXT':
                        text_content += node.get('text', '')
                    elif node_type == 'RICH_TEXT_NODE_TYPE_AT':
                        text_content += node.get('text', '')
                    elif node_type == 'RICH_TEXT_NODE_TYPE_TOPIC':
                        text_content += node.get('text', '')

            elif module_type == "MODULE_TYPE_STAT":
                module_stat = module.get("module_stat", {})
            elif module_type == "MODULE_TYPE_AUTHOR":
                module_author = module.get("module_author", {})

            if text_content and module_stat and module_author:
                break

        author_user = module_author.get('user', {}) if module_author else {}
        comment_info = module_stat.get("comment", {}) if module_stat else {}

        details["text_content_full"] = text_content
        details["comment_oid"] = comment_info.get("comment_id")
        details["comment_type"] = int(comment_info.get("comment_type", 11))
        details["author_mid"] = author_user.get("mid")
        details["author_name"] = author_user.get("name")
        details["is_forward"] = is_forward
        details["is_lottery"] = is_lottery

        return True, text_content, details

    def get_two_comment(self, oid: int, comment_type: int) -> str:
        """获取置顶评论和3条普通评论"""
        params = {"oid": oid, "type": comment_type}
        data = self._request("GET", api.URL_GET_COMMENT, params=params)

        if data and data.get("code") == 0:
            replies = data.get("data", {}).get("replies", [])
            top_replies = data.get("data", {}).get("top_replies", [])

            comment_strings = []
            if top_replies:
                top_comment_content = top_replies[0].get("content", {}).get("message", "无置顶评论内容")
                comment_strings.append(f"评论4: {top_comment_content}")

            if replies:
                for i, reply in enumerate(replies[:3], 1):
                    comment_content = reply.get("content", {}).get("message", "无评论内容")
                    comment_strings.append(f"评论{i}: {comment_content}")

            if not comment_strings:
                return "暂无评论"

            api_logger.debug(f"评论数据: {comment_strings}")
            return "\n".join(comment_strings)
        else:
            error_msg = data.get("message", "未知错误") if data else "无数据"
            api_logger.error(f"获取评论失败: {error_msg}")
            return f"获取评论失败: {error_msg}"

    def check_comment_status(self, oid: int, rpid: int, comment_type: int) -> tuple[bool, dict]:
        """检查评论状态"""
        api_logger.debug(f"账号 [{self.remark}] 正在检查评论状态 rpid: {rpid}...")
        params = {"oid": oid, "type": comment_type, "root": rpid, "ps": 1, "pn": 1}

        try:
            # 1. 使用认证身份检查评论状态, 返回12022, 说明评论已删除
            auth_response = self.session.get(api.URL_COMMENT_REPLY, params=params, timeout=30)
            auth_data = auth_response.json()
            if auth_data.get("code") == 12022:
                api_logger.debug(f"评论 {rpid} 状态检查 -> [{self.STATE_DELETED}]")
                return True, {"status": self.STATE_DELETED, "code": 1}

            # 2. 不使用认证身份检查评论状态, 返回12022, 说明评论被ShadowBan
            with requests.Session() as no_auth_session:
                no_auth_session.headers.update(api.BASE_HEADERS)
                no_auth_response = no_auth_session.get(api.URL_COMMENT_REPLY, params=params, timeout=30)
                no_auth_data = no_auth_response.json()
                if no_auth_data.get("code") == 12022:
                    api_logger.debug(f"评论 {rpid} 状态检查 -> [{self.STATE_SHADOW_BANNED}]")
                    return True, {"status": self.STATE_SHADOW_BANNED, "code": 2}

            # 3. 非以上两种情况, 则正常
            api_logger.debug(f"评论 {rpid} 状态 -> [{self.STATE_NORMAL}]")
            return True, {"status": self.STATE_NORMAL, "code": 0}

        except Exception as e:
            api_logger.error(f"检查评论 {rpid} 状态时发生未知错误: {e}")
            return False, {"status": self.STATE_API_ERROR, "message": str(e)}

    def get_at_message(self, config: Dict[str, Any]) -> tuple[bool, list[dict]]:
        """获取@详情列表"""
        old_at_id = load_at_id(config['file_paths']['history_at_ids'])
        response = self.session.get(
            api.URL_CHECK_AT,
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
                    api_logger.debug(f"@id {at_id} 已在记录中，跳过")
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
                    save_at_id_to_file(config['file_paths']['history_at_ids'], at_id)
                    at_list.append(at_data)
            return True, at_list

        else:
            error_msg = data.get('message', '未知错误')
            api_logger.error(f"Code: {data.get('code')} | Message: {error_msg}")
            return False, error_msg

    def get_reply_message(self, config: Dict[str, Any]) -> tuple[bool, list[dict]]:
        """获取回复详情"""
        old_reply_id = load_reply_id(config['file_paths']['history_reply_ids'])
        response = self.session.get(
            api.URL_CHECK_REPLY,
            headers=api.BASE_HEADERS,
            timeout=20,
            verify=False
        )
        data = response.json()

        if data.get("code") == 0:
            items = data.get('data', {}).get('items', [])
            reply_list = []

            for i in items:
                reply_id = str(i.get('id'))
                reply_uid = i.get('user', {}).get('mid')
                nickname = i.get('user', {}).get('nickname')
                url = i.get('item', {}).get('uri')
                content = i.get('item', {}).get('source_content')

                if reply_id in old_reply_id:
                    api_logger.debug(f"回复id {reply_id} 已在记录中，跳过")
                    continue
                else:
                    reply_data = {
                        "id": reply_id,
                        "uid": reply_uid,
                        "nickname": nickname,
                        "content": content,
                        "url": url
                    }
                    api_logger.debug(f"提取到回复内容: \n{reply_data}")
                    save_at_id_to_file(config['file_paths']['history_reply_ids'], reply_id)
                    reply_list.append(reply_data)
            return True, reply_list

        else:
            error_msg = data.get('message', '未知错误')
            api_logger.error(f"Code: {data.get('code')} | Message: {error_msg}")
            return False, error_msg

    def get_session_messages(self, config: Dict[str, Any]) -> tuple[bool, list[dict]]:
        """获取私信列表及详情"""
        old_msg_ids = load_message_id(config['file_paths']['history_message_ids'])

        # 获取私信列表
        response = self.session.get(
            api.URL_GET_SESSION_INFO,
            headers=api.BASE_HEADERS,
            params={'session_type': 1}
        )
        data = response.json()

        if data.get("code") == 0:
            sessions = data.get('data', {}).get('session_list', [])
            message_list = []

            for session in sessions:
                talker_id = session.get('talker_id')
                unread_count = session.get('unread_count', 0)

                if unread_count > 0:
                    api_logger.debug(f"找到UID {talker_id} 的 {unread_count} 条未读私信，正在获取详情...")

                    # 获取私信详情
                    msg_response = self.session.get(
                        api.URL_MESSAGE_DETAIL,
                        headers=api.BASE_HEADERS,
                        params={
                            'talker_id': talker_id,
                            'session_type': 1,
                            'size': unread_count
                        },
                    )
                    msg_data = msg_response.json()
                    if msg_data.get("code") == 0 and msg_data.get("data"):
                        messages = msg_data["data"]["messages"]

                        for msg in messages:
                            msg_id = str(msg.get('msg_seqno'))
                            sender_uid = msg.get('sender_uid')
                            content = json.loads(msg.get('content', '{}')).get('content', '')
                            msg_source = msg.get('msg_source')

                            if msg_source in [8, 9]:
                                api_logger.debug(
                                    f"跳过自动回复消息 (来源类型: {msg_source})，内容: {msg.get('content')[:30]}...")
                                continue
                            if msg.get('msg_type') != 1:
                                api_logger.debug(f"跳过非文本消息 (类型: {msg.get('msg_type')})")
                                continue
                            if msg_id in old_msg_ids:
                                api_logger.debug(f"私信ID {msg_id} 已在记录中，跳过")
                                continue
                            else:
                                message_data = {
                                    "id": msg_id,
                                    "sender_uid": sender_uid,
                                    "content": content,
                                    "talker_id": talker_id
                                }
                                api_logger.debug(f"提取到私信内容: \n{message_data}")
                                save_msg_id_to_file(config['file_paths']['history_message_ids'], msg_id)
                                message_list.append(message_data)
            return True, message_list
        else:
            error_msg = data.get('message', '未知错误')
            api_logger.error(f"获取私信会话列表失败 | Code: {data.get('code')} | Message: {error_msg}")
            return False, error_msg

    def fetch_popular_video(self) -> tuple[bool, list[dict]]:
        """获取热门视频"""
        response = self.session.get(
            api.URL_POPULAR_VIDEO,
            headers=api.BASE_HEADERS,
            timeout=20,
            verify=False
        )
        data = response.json()

        if data.get('code') == 0:
            item = data.get('data', {}).get('item', [])
            video_list = []

            for i in item:
                aid = i.get('id')
                bvid = i.get('bvid')
                cid = i.get('cid')
                url = i.get('uri')
                title = i.get('title')

                video_data = {
                    "aid": aid,
                    "bvid": bvid,
                    "cid": cid,
                    "url": url,
                    "title": title
                }
                api_logger.debug(f"提取到视频内容: \n{video_data}")
                video_list.append(video_data)

            api_logger.debug(f"成功获取 {len(video_list)} 个热门视频")
            return True, video_list

        else:
            error_msg = data.get('message', '未知错误')
            api_logger.error(f"获取热门视频错误 Code: {data.get('code')} | Message: {error_msg}")
            return False, error_msg