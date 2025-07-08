import logging
import re
import api.api_constants as api
from typing import Optional

data_extractor_logger = logging.getLogger("Bilibili.DataExtractors")


def extract_bili_jct(cookie_str: str) -> Optional[str]:
    """提取bili_jct"""
    if not cookie_str:
        return None
    match = re.search(r"bili_jct=([^;]+)", cookie_str)
    return match.group(1).strip() if match else None


def extract_dynamic_id(url: str) -> Optional[str]:
    """提取动态ID"""
    patterns = [
        r"(?:www|m)\.bilibili\.com/dynamic/(\d+)",
        r"(?:www|m)\.bilibili\.com/opus/(\d+)",
        r"t\.bilibili\.com/(\d+)"
    ]
    
    for pattern in patterns:
        if match := re.search(pattern, url):
            return match.group(1)
    
    data_extractor_logger.error(f"无法从URL中提取dynamic_id: {url}")
    return None


def get_comment_oid_str(client: 'BilibiliClient', dynamic_id: str) -> Optional[str]:
    """获取评论区OID"""
    detail_data = client._request("GET", api.URL_DYNAMIC_CONTENT, params={"id": dynamic_id})

    if not detail_data or detail_data.get("code") != 0:
        error_msg = detail_data.get("message") if detail_data else "请求失败"
        data_extractor_logger.error(f"获取动态 {dynamic_id} 评论OID失败: {error_msg}")
        return None

    modules = detail_data.get("data", {}).get("item", {}).get("modules", [])

    module_stat_data = None
    for module in modules:
        if module.get("module_type") == "MODULE_TYPE_STAT":
            module_stat_data = module.get("module_stat", {})
            break
    if not module_stat_data:
        data_extractor_logger.error(f"动态 {dynamic_id} 数据中未找到module_stat")
        return None

    comment_id_str = module_stat_data.get("comment", {}).get("comment_id")

    if comment_id_str:
        data_extractor_logger.debug(f"获取到评论OID: {comment_id_str}")
        return comment_id_str
    data_extractor_logger.error(f"动态 {dynamic_id} 返回数据中未找到评论OID")
    return None

def fetch_comment_type_from_api(client: 'BilibiliClient', dynamic_id: str) -> Optional[int]:
    """获取动态的评论类型"""
    detail_data = client._request("GET", api.URL_DYNAMIC_CONTENT, params={"id": dynamic_id})

    if not detail_data or detail_data.get("code") != 0:
        error_msg = detail_data.get("message") if detail_data else "请求失败"
        data_extractor_logger.error(f"API错误: 获取动态 {dynamic_id} 评论类型失败: {error_msg}")
        return None

    modules = detail_data.get('data', {}).get("item", {}).get("modules", [])
    module_stat_data = None
    for module in modules:
        if module.get("module_type") == "MODULE_TYPE_STAT":
            module_stat_data = module.get("module_stat", {})
            break

    if not module_stat_data:
        data_extractor_logger.error(f"动态 {dynamic_id} 数据中未找到module_stat")
        return None
    comment_type = module_stat_data.get("comment", {}).get("comment_type")
    if comment_type is None:
        data_extractor_logger.warning(f"动态 {dynamic_id} 返回数据中未找到 comment_type")
        return None

    data_extractor_logger.debug(f"获取到comment_type: {comment_type}")
    return int(comment_type)

def get_dynamic_type_for_comment(client: 'BilibiliClient', dynamic_id: str, url: str) -> int:
    """获取动态的评论类型"""
    comment_type = fetch_comment_type_from_api(client, dynamic_id)
    return comment_type if comment_type is not None else 11


def get_dynamic_type_for_repost(dynamic_id: str, url: str) -> int:
    """判断转发动态的类型参数"""
    url_type_mapping = [
        (r"bilibili\.com/opus/\d+", 2, "图文/opus"),
        (r"t\.bilibili\.com/\d+", 4, "普通动态")
    ]
    
    for pattern, type_val, type_name in url_type_mapping:
        if re.search(pattern, url):
            return type_val
    
    data_extractor_logger.debug(f"无法确定动态{dynamic_id}的类型，使用默认值4")
    return 4

def get_author_mid(client: 'BilibiliClient', dynamic_id: str) -> Optional[int]:
    """获取动态作者的UID"""
    detail_data = client._request("GET", api.URL_DYNAMIC_CONTENT, params={"id": dynamic_id})

    if not detail_data or detail_data.get("code") != 0:
        error_msg = detail_data.get("message") if detail_data else "请求失败"
        data_extractor_logger.error(f"API错误: {error_msg}")
        return None

    modules = detail_data.get("data", {}).get("item", {}).get("modules", [])
    module_author_data = modules[0].get("module_author", {})
    author_mid = module_author_data.get('user', {}).get("mid")
    if not author_mid:
        data_extractor_logger.warning(f"返回数据中未找到作者UID")
        return None

    data_extractor_logger.debug(f"获取到作者UID: {author_mid}")
    return author_mid


def check_follow_status(client: 'BilibiliClient', target_uid: int) -> tuple[int, str]:
    """检查关注状态"""
    params = {"fid": target_uid, "jsonp": "jsonp", "mid": client.mid}
    response_data = client._request("GET", api.URL_CHECK_FOLLOW, params=params)

    if not response_data or response_data.get("code") != 0:
        error_msg = response_data.get("message") if response_data else "请求失败"
        data_extractor_logger.error(f"API错误: {error_msg}")
        return -1, error_msg

    code = int(response_data.get("data", {}).get("attribute", -1))
    data_extractor_logger.debug(f"关注状态值: {code}")
    status_mapping = {
        2: f"已关注 UID {target_uid}，无需操作",
        6: f"互相关注 UID {target_uid}，无需操作",
        128: f"已拉黑 UID {target_uid}，跳过对该动态的操作",
        0: "未关注"
    }
    message = status_mapping.get(code, "unknown")
    
    return code, message