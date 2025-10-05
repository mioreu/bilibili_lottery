import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, Tuple, List

import requests
import urllib3

import api.api_constants as api
from services.wbi_sign import get_wbi_keys, enc_wbi
from utils import database_operations
from utils.data_extractors import extract_bili_jct

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
api_logger = logging.getLogger("Bilibili.Api")

class CommentStatus(Enum):
    NORMAL = "正常"
    DELETED = "已删除（评论被秒删）"
    SHADOW_BANNED = "仅自己可见（审核通过但仅发布者可见）"
    API_ERROR = "API错误"

@dataclass
class DynamicContent:
    mid: Optional[int]
    author_name: Optional[str]
    text: str
    oid: Optional[int]
    comment_oid: Optional[int]
    comment_type: int
    is_lottery: bool
    is_forward: bool
    is_video: bool
    video_info: Dict[str, Any] = field(default_factory=dict)
    rich_text_nodes: List[Dict[str, Any]] = field(default_factory=list)


class BilibiliClient:
    def __init__(self, cookie: str, remark: str):
        """初始化"""
        self.remark = remark
        self.session = requests.Session()
        self.session.headers.update(api.BASE_HEADERS)
        self.session.headers["Cookie"] = cookie
        self.csrf = extract_bili_jct(cookie)
        self.is_valid = False
        self.mid = None
        self.uname = None
        self.db_path: Optional[str] = None
        self.account_config: Dict[str, Any] = {}
        self.img_key, self.sub_key = "", ""
        self._refresh_wbi_keys(check_login=True)

    def _refresh_wbi_keys(self, check_login: bool = True):
        """刷新WBI签名密钥"""
        self.img_key, self.sub_key = get_wbi_keys(self.session)
        if not self.img_key or not self.sub_key:
            api_logger.warning(f"账号 [{self.remark}] 刷新WBI密钥失败。部分接口可能无法使用")

        if check_login:
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
                level = user_info.get("level_info", {}).get("current_level", "?")
                api_logger.info(
                    f"账号 [{self.remark}] Cookie 验证成功\n"
                    f"├─ 用户: {self.uname} \n"
                    f"├─ 等级: Lv.{level} \n"
                    f"└─ UID: {self.mid} "
                )
                self.is_valid = True
                time.sleep(1)
            else:
                api_logger.error(
                    f"账号 [{self.remark}] 初始化失败：Code: {api_code} | Message: {api_message} | 请检查Cookie有效性"
                )

        except requests.exceptions.RequestException as e:
            api_logger.error(f"账号 [{self.remark}] 初始化请求时发生网络错误: {api.URL_NAV_INFO}, {e}")
        except Exception as e:
            api_logger.exception(f"账号 [{self.remark}] 初始化时发生未知错误: {e}")

    def _request(self, method: str, url: str, params: Optional[Dict[str, Any]] = None,
                 data: Optional[Dict[str, Any]] = None, use_wbi: bool = False,
                 **kwargs) -> Optional[Dict[str, Any]]:
        """通用请求方法"""
        max_retries = 2
        final_params = params.copy() if params else {}

        if use_wbi:
            self._refresh_wbi_keys(check_login=False)
            signed_params = enc_wbi(final_params, self.img_key, self.sub_key)
            final_params = signed_params

        for attempt in range(max_retries):
            try:
                kwargs.setdefault('verify', False)
                kwargs.setdefault('timeout', 60)

                response = self.session.request(method, url, params=final_params, data=data, **kwargs)
                response.raise_for_status()
                response_data = response.json()

                if response_data.get("code") != 0:
                    api_logger.error(
                        f"账号 [{self.remark}] API 请求返回错误: {url} | "
                        f"Code: {response_data.get('code')} | Message: {response_data.get('message')}"
                    )
                return response_data

            except requests.exceptions.RequestException as e:
                api_logger.warning(
                    f"账号 [{self.remark}] API 请求遇到网络错误 (尝试 {attempt + 1}/{max_retries}): {url} | 错误: {e}"
                )
                time.sleep(1 + attempt * 2)
            except json.JSONDecodeError as e:
                api_logger.error(f"账号 [{self.remark}] API 响应 JSON 解析失败: {url} | 错误: {e}")
                break

        return None

    def _handle_api_response(self, data: Optional[Dict[str, Any]], success_msg: str, action_log: str) -> Tuple[
        bool, str]:
        """通用API响应处理器"""
        api_logger.debug(f"账号 [{self.remark}] {action_log}\n返回数据:{data}")
        if data and data.get("code") == 0:
            return True, success_msg
        else:
            error_msg = data.get('message', '未知错误') if data else '请求失败，无数据返回'
            return False, error_msg

    def follow_user(self, target_uid: int) -> tuple[bool, str]:
        """关注"""
        payload = {
            "fid": target_uid,
            "act": 1,
            "re_src": 11,
            "csrf": self.csrf,
        }
        data = self._request("POST", api.URL_FOLLOW, data=payload)
        return self._handle_api_response(data, "关注成功", f"尝试关注用户 {target_uid}...")

    def like_dynamic(self, dynamic_id: str) -> tuple[bool, str]:
        """点赞动态"""
        payload = {
            "dynamic_id": dynamic_id,
            "optype": 1,
            "csrf_token": self.csrf,
            "csrf": self.csrf,
        }
        data = self._request("POST", api.URL_LIKE_THUMB, data=payload)
        return self._handle_api_response(data, "点赞成功", f"尝试点赞动态 {dynamic_id}...")

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
        return self._handle_api_response(data, "转发成功", f"尝试转发动态 {url}...")

    def create_dyn(self, dynamic_id: int, content_data: Dict[str, Any], message: str):
        """创建动态(转发)"""
        author_name = content_data.get("author_name")
        author_mid = content_data.get("mid")
        repost_nodes = []

        if message:
            repost_nodes.append({"raw_text": message, "type": 1, "biz_id": ""})

        repost_nodes.extend([
            {"raw_text": "//", "type": 1, "biz_id": ""},
            {"raw_text": f"@{author_name}", "type": 2, "biz_id": f"{author_mid}"},
            {"raw_text": ":", "type": 1, "biz_id": ""}
        ])

        for node in content_data.get("rich_text_nodes", []):
            node_type = node.get("type")
            raw_text = node.get("orig_text", "")

            if node_type == "RICH_TEXT_NODE_TYPE_AT":
                repost_nodes.append({"raw_text": raw_text, "type": 2, "biz_id": node.get("rid", "")})
            else:
                repost_nodes.append({"raw_text": raw_text, "type": 1, "biz_id": ""})

        payload = {
            "csrf": self.csrf,
            "dyn_req": {
                "scene": 4,
                "content": {
                    "contents": repost_nodes if repost_nodes else [
                        {"raw_text": "转发动态", "type": 1, "biz_id": ""}]
                },
            },
            "web_repost_src": {
                "dyn_id_str": dynamic_id,
            }
        }

        data = self._request("POST", api.URL_CREATE_DYNAMIC, params={'csrf': self.csrf}, data=json.dumps(payload),
                             use_wbi=False, headers={'Content-Type': 'application/json'})
        return self._handle_api_response(data, "转发成功", f"尝试通过 create_dyn 转发动态 {dynamic_id}...")

    def comment_dynamic(self, dynamic_id: str, message: str, comment_type, oid) -> tuple[bool, str, str, int]:
        """评论动态"""
        payload = {
            "plat": 1,
            "oid": oid,
            "type": comment_type,
            "message": message,
            "gaia_source": "main_web",
            "at_name_to_mid": {},
            "csrf": self.csrf,
            "statistics": json.dumps({"appId": 1, "platform": 3, "version": "2.38.0", "abtest": ""}),
        }

        data = self._request("POST", api.URL_COMMENT, params=payload, use_wbi=True)
        api_logger.debug(f"账号 [{self.remark}] 尝试评论动态 {dynamic_id}... \n返回数据:{data}")

        if data:
            code = data.get("code")
            if code == 0:
                rpid = data.get("data", {}).get("rpid")
                success_msg = f"评论成功\n├─ 内容:{message}\n└─ 评论链接: https://www.bilibili.com/opus/{dynamic_id}#reply{rpid}"
                return True, success_msg, str(rpid), 0
            elif code == 12015:
                return False, "评论弹出验证码", "", 12015
            else:
                error_msg = data.get('message', '未知错误')
                return False, error_msg, "", code if code is not None else -1

        return False, "请求失败，无数据返回", "", -1

    def repost_video(self, aid: int, title: str) -> tuple[bool, str]:
        """转发视频"""
        payload = {
            "dyn_req": {"content": {"contents": [{"raw_text": "分享视频", "type": 1}]}, "scene": 5},
            "web_repost_src": {"revs_id": {"dyn_type": 8, "rid": aid}}
        }
        data = self._request(
            "POST",
            api.URL_CREATE_DYNAMIC,
            json=payload,
            params={"csrf": self.csrf}
        )
        return self._handle_api_response(data, "转发成功", f"尝试转发视频 {title}...")

    def comment_video(self, aid: int, message: str) -> tuple[bool, str, str, int]:
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

        if data:
            code = data.get("code")
            if code == 0:
                rpid = str(data.get("data", {}).get("rpid"))
                return True, (f"评论成功\n"
                              f"├─ 内容:{message}\n"
                              f"└─ 评论链接: https://www.bilibili.com/av{aid}#reply{rpid}"), rpid, 0
            elif code == 12015:
                return False, "评论弹出验证码", "", code
            else:
                error_msg = data.get('message', '未知错误')
                return False, error_msg, "", code if code is not None else -1

        return False, "请求失败，无数据返回", "", -1

    def like_video(self, aid: int) -> tuple[bool, str]:
        """点赞视频"""
        payload = {
            "aid": aid,
            "like": 1,
            "csrf": self.csrf
        }
        data = self._request("POST", api.URL_LIKE_VIDEO, data=payload)
        return self._handle_api_response(data, "点赞成功", f"尝试点赞视频 av{aid}...")

    def fetch_video_detail(self, bvid: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """获取视频详情"""
        params = {"bvid": bvid}
        data = self._request("GET", api.URL_VIDEO_DETAIL, params=params)

        if not data or data.get("code") != 0:
            error_msg = data.get('message', '未知API错误') if data else "请求失败"
            api_logger.error(f"视频 {bvid} 内容获取失败 | Code: {data.get('code')} | Message: {error_msg}")
            return False, error_msg, None

        video_data = data.get('data', {})
        mid = video_data.get('owner', {}).get('mid')
        cid = video_data.get('cid')

        base_text = f"标题:{video_data.get('title', '')}\n简介:{video_data.get('desc', '')}"

        time.sleep(2)
        summary_success, msg, summary_text = self.video_ai_summary(bvid, cid, mid)
        if summary_success and summary_text:
            text = f"{base_text}\nAI总结:{summary_text}"
        else:
            text = base_text
            api_logger.warning(f"获取视频 {bvid} 的AI总结失败, {msg}")

        content = {
            "mid": mid,
            "author_name": video_data.get('owner', {}).get('name'),
            "text": text,
            "video_aid": video_data.get('aid'),
            "oid": video_data.get('aid'),
            "video_content": base_text,
            "comment_oid": video_data.get('aid'),
            "comment_type": 1,
            "is_lottery": False,
            "is_forward": False,
            "is_video": True,
        }

        return True, "成功获取视频详情", content

    def video_ai_summary(self, bvid: str, cid: int, mid: int) -> Tuple[bool, Optional[str], Optional[str]]:
        """获取视频的AI总结"""
        for _ in range(2):
            params = {"bvid": bvid, "cid": cid, "up_mid": mid}
            data = self._request("GET", api.URL_VIDEO_SUMMARY, use_wbi=True, params=params)

            if not data:
                return False, "请求失败，无数据返回", None

            if data.get("code") != 0:
                error_msg = data.get("message", "未知API错误")
                api_logger.error(f"获取视频总结失败 | Code: {data.get('code')} | Message: {error_msg}")
                return False, error_msg, None

            summary = data.get("data", {}).get("model_result", {}).get("summary")

            if summary:
                print(f"成功获取视频 {bvid} 的AI总结:\n{summary}")
                return True, "成功获取视频总结", summary
            time.sleep(5)
        return False, "视频总结数据为空", None

    def fetch_dynamic_content(self, dynamic_id: str) -> Tuple[bool, Optional[str], Optional[DynamicContent]]:
        """获取动态详情"""
        params = {"id": dynamic_id}
        data = self._request("GET", api.URL_DYNAMIC_CONTENT, params=params)

        if not data or data.get("code") != 0:
            error_msg = data.get('message', '未知API错误') if data else "请求失败，无数据返回"
            api_logger.error(f"动态 {dynamic_id} 爬取失败 | Code: {data.get('code')} | Message: {error_msg}")
            return False, error_msg, None

        item = data.get('data', {}).get('item', {})
        modules = item.get('modules', [])

        text_content = ""
        rich_text_nodes_list = []
        is_video = False
        is_forward = False
        is_lottery = False
        video_info = {}
        module_stat = None
        module_author = None

        for module in modules:
            module_type = module.get('module_type')

            if module_type == "MODULE_TYPE_DYNAMIC":
                dyn_module = module.get("module_dynamic", {})
                if dyn_module.get("type") == "MDL_DYN_TYPE_ARCHIVE":
                    is_video = True
                    dyn_archive = dyn_module.get("dyn_archive", {})
                    video_info = {"aid": dyn_archive.get("aid"), "bvid": dyn_archive.get("bvid")}
                elif dyn_module.get("type") == "MDL_DYN_TYPE_FORWARD":
                    is_forward = True

            elif module_type == "MODULE_TYPE_DESC":
                desc_module = module.get('module_desc', {})
                rich_text_nodes = desc_module.get('rich_text_nodes', [])
                rich_text_nodes_list.extend(rich_text_nodes)
                for node in rich_text_nodes:
                    node_type = node.get('type')
                    if node_type == 'RICH_TEXT_NODE_TYPE_LOTTERY':
                        is_lottery = True
                    text_content += node.get('text', '') or node.get('orig_text', '')

            elif module_type == "MODULE_TYPE_STAT":
                module_stat = module.get("module_stat", {})
            elif module_type == "MODULE_TYPE_AUTHOR":
                module_author = module.get("module_author", {})

        author_user = module_author.get('user', {}) if module_author else {}
        comment_info = module_stat.get("comment", {}) if module_stat else {}

        content = DynamicContent(
            mid=author_user.get("mid"),
            author_name=author_user.get("name"),
            text=text_content,
            oid=comment_info.get("comment_id"),
            comment_oid=comment_info.get("comment_id"),
            comment_type=int(comment_info.get("comment_type", 11)),
            is_lottery=is_lottery,
            is_forward=is_forward,
            is_video=is_video,
            video_info=video_info,
            rich_text_nodes=rich_text_nodes_list
        )
        api_logger.debug(f"动态 {dynamic_id} 详情:\n{content}")

        return True, text_content, content

    def get_some_comment(self, oid: int, comment_type: int) -> str:
        """获取置顶评论和3条普通评论"""
        params = {"oid": oid, "type": comment_type}
        data = self._request("GET", api.URL_GET_COMMENT, params=params)

        if data and data.get("code") == 0:
            replies = data.get("data", {}).get("replies", [])
            top_replies = data.get("data", {}).get("top_replies", [])

            comment_strings = []
            if top_replies:
                top_comment_content = top_replies[0].get("content", {}).get("message", "无置顶评论内容")
                comment_strings.append(f"{top_comment_content}")

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
            auth_response = self.session.get(api.URL_COMMENT_REPLY, params=params, timeout=40)
            auth_data = auth_response.json()
            if auth_data.get("code") == 12022:
                api_logger.debug(f"评论 {rpid} 状态检查 -> [{CommentStatus.DELETED.value}]")
                return True, {"status": CommentStatus.DELETED.value, "code": 1}

            with requests.Session() as no_auth_session:
                no_auth_session.headers.update(api.BASE_HEADERS)
                no_auth_response = no_auth_session.get(api.URL_COMMENT_REPLY, params=params, timeout=40)
                no_auth_data = no_auth_response.json()
                if no_auth_data.get("code") == 12022:
                    api_logger.debug(f"评论 {rpid} 状态检查 -> [{CommentStatus.SHADOW_BANNED.value}]")
                    return True, {"status": CommentStatus.SHADOW_BANNED.value, "code": 2}

            api_logger.debug(f"评论 {rpid} 状态 -> [{CommentStatus.NORMAL.value}]")
            return True, {"status": CommentStatus.NORMAL.value, "code": 0}

        except Exception as e:
            api_logger.error(f"检查评论 {rpid} 状态时发生未知错误: {e}")
            return False, {"status": CommentStatus.API_ERROR, "message": str(e)}

    def get_at_message(self) -> tuple[bool, list[dict]]:
        """获取@详情列表"""
        data = self._request("GET", api.URL_CHECK_AT)

        if data and data.get("code") == 0:
            items = data.get('data', {}).get('items', [])
            at_list = []
            for i in items:
                at_id = str(i.get('id'))

                if database_operations.check_id_exists(self.db_path, at_id):
                    api_logger.debug(f"@id {at_id} 已在记录中，跳过")
                    continue
                else:
                    at_data = {
                        "id": at_id,
                        "uid": i.get('user', {}).get('mid'),
                        "nickname": i.get('user', {}).get('nickname'),
                        "content": i.get('item', {}).get('source_content'),
                        "url": i.get('item', {}).get('uri')
                    }
                    api_logger.debug(f"提取到@详情内容: \n{at_data}")
                    database_operations.add_id(self.db_path, at_id, 'at')
                    at_list.append(at_data)
            return True, at_list
        else:
            error_msg = data.get('message', '未知错误') if data else "请求失败"
            return False, [{"error": error_msg}]

    def get_reply_message(self) -> tuple[bool, list[dict]]:
        """获取回复详情"""
        data = self._request("GET", api.URL_CHECK_REPLY)

        if data and data.get("code") == 0:
            items = data.get('data', {}).get('items', [])
            reply_list = []

            for i in items:
                reply_id = str(i.get('id'))

                if database_operations.check_id_exists(self.db_path, reply_id):
                    api_logger.debug(f"回复id {reply_id} 已在记录中，跳过")
                    continue
                else:
                    reply_data = {
                        "id": reply_id,
                        "uid": i.get('user', {}).get('mid'),
                        "nickname": i.get('user', {}).get('nickname'),
                        "content": i.get('item', {}).get('source_content'),
                        "url": i.get('item', {}).get('uri')
                    }
                    api_logger.debug(f"提取到回复内容: \n{reply_data}")
                    database_operations.add_id(self.db_path, reply_id, 'reply')
                    reply_list.append(reply_data)
            return True, reply_list
        else:
            error_msg = data.get('message', '未知错误') if data else "请求失败"
            return False, [{"error": error_msg}]

    def get_session_messages(self) -> tuple[bool, list[dict]]:
        """获取私信列表及详情"""
        params = {'session_type': 1}
        data = self._request("GET", api.URL_GET_SESSION_INFO, params=params)

        if data and data.get("code") == 0:
            sessions = data.get('data', {}).get('session_list', [])
            message_list = []
            if sessions is None:
                sessions = []

            for session in sessions:
                talker_id = session.get('talker_id', 0)
                unread_count = session.get('unread_count', 0)

                if unread_count > 0:
                    api_logger.debug(f"找到UID {talker_id} 的 {unread_count} 条未读私信，正在获取详情...")

                    msg_params = {
                        'talker_id': talker_id, 'session_type': 1, 'size': unread_count
                    }
                    msg_data = self._request("GET", api.URL_MESSAGE_DETAIL, params=msg_params)

                    if msg_data and msg_data.get("code") == 0 and msg_data.get("data"):
                        messages = msg_data["data"].get("messages", [])

                        for msg in messages:
                            msg_id = str(msg.get('msg_seqno'))
                            if msg.get('msg_source') in [8, 9] or msg.get('msg_type') != 1:
                                continue

                            if database_operations.check_id_exists(self.db_path, msg_id):
                                api_logger.debug(f"私信ID {msg_id} 已在记录中，跳过")
                                continue

                            try:
                                content = json.loads(msg.get('content', '{}')).get('content', '')
                            except json.JSONDecodeError:
                                content = msg.get('content', '')

                            message_data = {
                                "id": msg_id,
                                "sender_uid": msg.get('sender_uid'),
                                "content": content,
                                "talker_id": talker_id
                            }
                            api_logger.debug(f"提取到私信内容: \n{message_data}")
                            database_operations.add_id(self.db_path, msg_id, 'message')
                            message_list.append(message_data)
            return True, message_list
        else:
            error_msg = data.get('message', '未知错误') if data else "获取私信会话列表失败"
            api_logger.error(f"获取私信会话列表失败 | Code: {data.get('code')} | Message: {error_msg}")
            return False, []

    def fetch_popular_video(self) -> tuple[bool, list[dict]]:
        """获取热门视频"""
        data = self._request("GET", api.URL_POPULAR_VIDEO, use_wbi=False)

        if data and data.get('code') == 0:
            items = data.get('data', {}).get('list', [])
            video_list = []

            for i in items:
                video_data = {
                    "aid": i.get('aid'),
                    "bvid": i.get('bvid'),
                    "cid": i.get('cid'),
                    "url": i.get('short_link_v2') or i.get('uri'),
                    "title": i.get('title')
                }
                api_logger.debug(f"提取到视频内容: \n{video_data}")
                video_list.append(video_data)

            api_logger.debug(f"成功获取 {len(video_list)} 个热门视频")
            return True, video_list
        else:
            error_msg = data.get('message', '未知错误') if data else "请求失败，无数据"
            api_logger.error(f"获取热门视频错误 Code: {data.get('code') if data else 'N/A'} | Message: {error_msg}")
            return False, [{"error": error_msg}]

    def fetch_user_forwarded_dynamic_url(self, mid: int, limit: int = 120) -> Tuple[bool, str, Optional[List[str]]]:
        """获取指定用户转发动态"""
        offset = ""
        has_more = True
        dynamic_list = []
        total_fetched_count = 0

        while has_more:
            if len(dynamic_list) >= limit:
                break

            params = {"host_mid": mid, "offset": offset}
            data = self._request("GET", api.URL_SPACE_DYNAMIC, use_wbi=True, params=params)

            if not data or data.get("code") != 0:
                error_msg = data.get("message", "未知API错误") if data else "请求失败，无数据返回"
                return False, error_msg, None

            items = data.get("data", {}).get("items", [])
            if not items:
                break

            for item in items:
                if item.get("type") == "DYNAMIC_TYPE_FORWARD":
                    orig_data = item.get("orig", {})
                    dynamic_id = orig_data.get("id_str")
                    timestamp = item.get("timestamp", 0) or orig_data.get("timestamp", 0)
                    if dynamic_id:
                        url = f"https://t.bilibili.com/{dynamic_id}"
                        dynamic_list.append((timestamp, url))

            total_fetched_count += len(items)
            print(f"已获取 {total_fetched_count} 条动态")

            has_more = data.get("data", {}).get("has_more", False)
            offset = data.get("data", {}).get("offset", "")

            if has_more and len(dynamic_list) < limit:
                time.sleep(1)

        dynamic_list.sort(key=lambda x: x[0], reverse=True)
        final_urls = [url for _, url in dynamic_list[:limit]]

        return True, "成功", final_urls