import logging
from typing import Optional
import re
import api.api_constants as api
from services.deepseek_ai import check_at_requirement

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
        r'(?:bilibili\.com/(?:opus|dynamic)/)(\d+)(?=\D|$)',
        r'(?:t\.bilibili\.com/)(\d+)(?=\D|$)'
    ]
    
    for pattern in patterns:
        if match := re.search(pattern, url):
            return match.group(1)
    data_extractor_logger.debug(f"正在提取id {url}")
    return None

def extract_video_bvid(url: str) -> Optional[str]:
    """提取BVID"""
    patterns = [
        r'(?:bilibili\.com/video/)(BV[a-zA-Z0-9]{10})'
    ]

    for pattern in patterns:
        if match := re.search(pattern, url):
            return match.group(1)

    data_extractor_logger.debug(f"正在提取BVID {url} ")
    data_extractor_logger.error(f"无法从URL中提取BVID: {url}")
    return None

def extract_topic_and_fixed_at(content: str) -> str:
    """提取话题文本和@用户"""
    content = re.sub(r'##(.*?)##\s*#', r'#\1##', content)
    topics = []
    patterns = [
        r'(?:带话题[：:\s]*|带话题词)\s*((?:#.*?#\s*)+)',
        r'【(?:带|加)话题】\s*((?:#.*?#\s*)+)',
        r'带上双话题\s*((?:#.*?#\s*)+)',
        r'(?:带|加上)\s*(#.*?#)\s*话题',
        r'带上话题[：:\s]*\s*((?:#.*?#\s*)+)',
        r'带\s*(#.*?#)\s*转评',
        r'(?:带话题|带话题词|带标签)\s*(#.*?#)',
        r'(?:带|加上)\s*(#.*?#)\s*，',
        r'带\s*(#.*?#)\s*转发'
    ]

    for pattern in patterns:
        matches = re.findall(pattern, content, re.MULTILINE)
        for match in matches:
            sub_topics = re.findall(r'#.*?#', match)
            cleaned_topics = [topic.strip() for topic in sub_topics]
            topics.extend(cleaned_topics)
            
    unique_topics = []
    seen_topics = set()
    for topic in topics:
        if topic not in seen_topics:
            unique_topics.append(topic)
            seen_topics.add(topic)

    mentions = []
    mention_pattern = r'并@([\w\u4e00-\u9fa5]+)'
    found_mentions = re.findall(mention_pattern, content)
    for mention in found_mentions:
        mentions.append(f" @{mention}")

    result_list = unique_topics + mentions
    result = " ".join(result_list)
    
    print(f"提取到话题和@文本：{result_list}")
    return result

def check_at(config, content: str) -> int:
    """检查是否需要@好友"""
    at_words = ["TA","@谁","好友", "艾特", "搭子", "队友", "开黑", "拍档"]
    deepseek_config = config["deepseek"]

    for at_word in at_words:
        if at_word in content:
            need_to_at, at_count = check_at_requirement(
                prompt=f"请分析以下内容:\n\n{content}",
                api_key=deepseek_config.get("deepseek_api_key"),
                model=deepseek_config.get("deepseek_model"),
                temperature=deepseek_config.get("temperature")
            )
            if need_to_at:
                return at_count
            else:
                return 0
    return 0

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
