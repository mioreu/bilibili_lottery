import logging
import re
from typing import Optional

data_extractor_logger = logging.getLogger("Bilibili.DataExtractors")

URL_DYNAMIC_DETAIL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail"
URL_CHECK_FOLLOW = "https://api.bilibili.com/x/relation"


def extract_bili_jct(cookie_str: str) -> Optional[str]:
    """提取 CSRF Token"""
    if not cookie_str:
        return None
    match = re.search(r"bili_jct=([^;]+)", cookie_str)
    if match:
        csrf_token = match.group(1).strip()
        return csrf_token
    return None


def extract_dynamic_id(url: str) -> Optional[str]:
    """提取 dynamic_id"""
    if match := re.search(r"(?:www|m)\.bilibili\.com/dynamic/(\d+)", url):
        return match.group(1)
    
    if match := re.search(r"(?:www|m)\.bilibili\.com/opus/(\d+)", url):
        return match.group(1)

    if match := re.search(r"t\.bilibili\.com/(\d+)", url):
        return match.group(1)
        
    data_extractor_logger.error(f"无法从给定的 URL 中提取有效的 dynamic_id: {url}")
    return None


def fetch_comment_type_from_api(client: 'BilibiliClient', dynamic_id: str) -> Optional[int]:
    """
    获取动态的 comment_type
    """
    if client is None:
        data_extractor_logger.warning("BilibiliClient 实例未提供，无法通过 API 获取 comment_type")
        return None

    data_extractor_logger.debug(f"账号 [{client.remark}] 尝试通过 API 获取动态 {dynamic_id} 的 comment_type")
    detail_data = client._request("GET", URL_DYNAMIC_DETAIL, params={"id": dynamic_id})

    if detail_data and detail_data.get("code") == 0:
        try:
            comment_type = detail_data["data"]["item"]["basic"].get("comment_type")
            if comment_type is not None:
                data_extractor_logger.debug(f"账号 [{client.remark}] 成功从 API 获取 comment_type: {comment_type}")
                return int(comment_type)
            else:
                data_extractor_logger.warning(f"账号 [{client.remark}] API 返回数据中未找到 comment_type 字段 (动态: {dynamic_id})")
        except (KeyError, TypeError, ValueError) as e:
            data_extractor_logger.error(f"账号 [{client.remark}] 解析 comment_type 时出错 (动态: {dynamic_id}): {e}", exc_info=False)
    elif detail_data:
        data_extractor_logger.error(f"账号 [{client.remark}] 获取动态详情 API 返回错误: Code: {detail_data.get('code')} | Message: {detail_data.get('message')}")
    else:
        data_extractor_logger.warning(f"账号 [{client.remark}] 获取动态详情 API 请求失败以获取 comment_type (动态: {dynamic_id})")
    return None


def get_dynamic_type_for_comment(client: 'BilibiliClient', dynamic_id: str, url: str) -> Optional[int]:
    """
    判断评论 API 需要的 type 参数
    """
    # 尝试通过API获取 comment_type (主要针对opus/t类型)
    comment_type = fetch_comment_type_from_api(client, dynamic_id)
    if comment_type is not None:
        data_extractor_logger.debug(f"获取 comment_type 成功: {comment_type}")
        return comment_type

    # 根据 URL 模式判断类型
    if re.search(r'bilibili\.com/video/(av|bv)', url, re.IGNORECASE):
        data_extractor_logger.debug(f"根据 URL 判断动态 {dynamic_id} 的评论类型为 1 (视频)")
        return 1
    if re.search(r'bilibili\.com/read/', url):
        data_extractor_logger.debug(f"根据 URL 判断动态 {dynamic_id} 的评论类型为 12 (专栏)")
        return 12
    if re.search(r"(t\.bilibili\.com/\d+|bilibili\.com/opus/\d+)", url):
        # 针对普通动态/图文，通常是17或11，这里统一用11作为常见类型
        data_extractor_logger.debug(f"根据 URL 判断动态 {dynamic_id} 的评论类型为 11 (普通动态/图文)")
        return 11

    data_extractor_logger.warning(f"账号 [{client.remark}] 无法明确判断动态 {dynamic_id} (来自 {url}) 的评论类型，无法评论。")
    return None


def get_dynamic_type_for_repost(dynamic_id: str, url: str) -> Optional[int]:
    """
    判断转发需要的 type 参数
    """
    if re.search(r"bilibili\.com/opus/\d+", url): 
        data_extractor_logger.debug(f"判断动态 {dynamic_id} (来自 {url}) 的转发类型为 2 (图文/opus)") 
        return 2
    if re.search(r"t\.bilibili\.com/\d+", url): 
        data_extractor_logger.debug(f"判断动态 {dynamic_id} (来自 {url}) 的转发类型为 4 (普通动态)") 
        return 4
    if re.search(r'bilibili\.com/read/', url): 
        data_extractor_logger.debug(f"判断动态 {dynamic_id} (来自 {url}) 的转发类型为 64 (专栏)") 
        return 64

    data_extractor_logger.debug(f"无法明确判断动态 {dynamic_id} (来自 {url}) 的转发类型，使用默认参数4") 
    return 4


def get_author_mid(client: 'BilibiliClient', dynamic_id: str) -> Optional[int]:
    """获取up主的UID"""
    if client is None:
        data_extractor_logger.warning("BilibiliClient 实例未提供，无法通过 API 获取作者 MID")
        return None

    data_extractor_logger.debug(f"账号 [{client.remark}] 尝试通过 API 获取动态 {dynamic_id} 的作者 MID")
    detail_data = client._request("GET", URL_DYNAMIC_DETAIL, params={"id": dynamic_id})

    if detail_data and detail_data.get("code") == 0:
        try:
            author_mid = detail_data["data"]["item"]["modules"]["module_author"]["mid"]
            if author_mid:
                data_extractor_logger.debug(f"账号 [{client.remark}] 成功从 API 获取动态 {dynamic_id} 作者 MID: {author_mid}")
                return int(author_mid)
            else:
                data_extractor_logger.warning(f"账号 [{client.remark}] API 返回数据中未找到作者 MID 字段 (动态: {dynamic_id})")
        except (KeyError, TypeError, ValueError) as e:
            data_extractor_logger.error(f"账号 [{client.remark}] 解析作者 MID 时出错 (动态: {dynamic_id}): {e}", exc_info=False)
    elif detail_data:
        data_extractor_logger.error(f"账号 [{client.remark}] 获取动态详情 API 返回错误以获取作者 MID: Code: {detail_data.get('code')} | Message: {detail_data.get('message')}")
    else:
        data_extractor_logger.warning(f"账号 [{client.remark}] 获取动态详情 API 请求失败以获取作者 MID (动态: {dynamic_id})")
    return None

def check_follow_status(client: 'BilibiliClient', target_uid: int) -> str:
    """检查关注状态"""
    params = {"fid": target_uid, "jsonp": "jsonp", "mid": client.mid}
    data_extractor_logger.debug(f"账号 [{client.remark}] 正在检查对 UID {target_uid} 的关注状态...")
    response_data = client._request("GET", URL_CHECK_FOLLOW, params=params)

    if response_data and response_data.get("code") == 0:
        follow_attribute = response_data["data"]["attribute"]
        data_extractor_logger.debug(f"返回原始json \n {response_data}")
        data_extractor_logger.debug(f"账号 [{client.remark}] 检查 UID {target_uid} 关注状态 API 返回 attribute: {follow_attribute}")

        if follow_attribute == 2 or follow_attribute == 6:
            return "is_follow"
        elif follow_attribute == 128:
            return "black_user"
        elif follow_attribute == 0:
            return "unfollow"
        else:
            return "error"
            
    elif response_data:
        data_extractor_logger.error(f"账号 [{client.remark}] 检查关注状态 API 返回错误: Code: {response_data.get('code')} | Message: {response_data.get('message')}")
    else:
        data_extractor_logger.warning(f"账号 [{client.remark}] 检查关注状态 API 请求失败 (目标 UID: {target_uid})")
    return "error"


def get_comment_oid_str(client: 'BilibiliClient', dynamic_id: str) -> Optional[str]:
    """获取评论oid"""
    data_extractor_logger.debug(f"账号 [{client.remark}] 正在获取动态 {dynamic_id} 的评论 OID...")
    detail_data = client._request("GET", client.URL_DYNAMIC_DETAIL, params={"id": dynamic_id})

    if detail_data and detail_data.get("code") == 0:
        try:
            item_data = detail_data.get("data", {}).get("item", {})
            if not item_data:
                data_extractor_logger.error(f"账号 [{client.remark}] 获取动态 {dynamic_id} 评论 OID 失败: API响应中缺少 'item' 结构。")
                return None
            
            basic_data = item_data.get("basic")
            if not basic_data:
                data_extractor_logger.error(f"账号 [{client.remark}] 获取动态 {dynamic_id} 评论 OID 失败: API响应中缺少 'basic' 结构。")
                data_extractor_logger.debug(f"详细 item 数据结构: {str(item_data)[:300]}")
                return None

            comment_id_str = basic_data.get("comment_id_str")
            if comment_id_str:
                data_extractor_logger.debug(f"账号 [{client.remark}] 成功从 API 获取动态 {dynamic_id} 评论 OID: {comment_id_str}")
                return comment_id_str
            else:
                data_extractor_logger.error(f"账号 [{client.remark}] 获取动态 {dynamic_id} 评论 OID 失败: API响应中缺少 'comment_id_str'。")
                data_extractor_logger.debug(f"详细 basic 数据结构: {str(basic_data)[:300]}")
                return None
        except (KeyError, TypeError) as e:
            data_extractor_logger.error(f"账号 [{client.remark}] 解析动态 {dynamic_id} 评论 OID 时出错: {e}", exc_info=True)
            return None
    elif detail_data:
        data_extractor_logger.error(f"账号 [{client.remark}] 获取动态 {dynamic_id} 评论 OID API 返回错误: Code: {detail_data.get('code')} | Message: {detail_data.get('message')}")
        return None
    else:
        data_extractor_logger.error(f"账号 [{client.remark}] 获取动态 {dynamic_id} 评论 OID API 请求失败。")
        return None