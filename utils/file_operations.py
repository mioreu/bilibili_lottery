import logging
import os
import re
from typing import List, Tuple, Set
from utils.data_extractors import extract_dynamic_id, extract_video_bvid

file_logger = logging.getLogger("Bilibili.file")


def load_origin_urls_from_file(file_path: str) -> Tuple[List[str], List[str]]:
    """加载URl"""
    video_urls: List[str] = []
    dynamic_urls: List[str] = []
    seen_ids: Set[str] = set()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        file_logger.error(f"文件未找到: {file_path}")
        return [], []

    bili_url_pattern = re.compile(
        r'https?://(?:www\.|m\.)?bilibili\.com/video/(?:BV[a-zA-Z0-9]+|av\d+)\S*|'
        r'https?://(?:www\.|m\.)?bilibili\.com/(?:opus/\d+|dynamic/\d+)\S*|'
        r'https?://t\.bilibili\.com/\d+(?=\D|$)'
    )
    found_urls = bili_url_pattern.findall(content)

    for url in found_urls:
        if '/video/' in url:
            bvid = extract_video_bvid(url)
            if bvid and bvid not in seen_ids:
                seen_ids.add(bvid)
                video_urls.append(url)
        else:
            d_id = extract_dynamic_id(url)
            if d_id and d_id not in seen_ids:
                seen_ids.add(d_id)
                dynamic_urls.append(url)

    return dynamic_urls, video_urls

def read_history_from_file(file_path: str) -> set:
    """加载已处理的动态ID和视频BVID"""
    history_ids = set()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                if not url:
                    continue

                extracted_id = extract_dynamic_id(url)
                if not extracted_id:
                    extracted_id = extract_video_bvid(url)

                if extracted_id:
                    history_ids.add(extracted_id)

        file_logger.debug(f"加载 {len(history_ids)} 个已处理的动态和视频ID")
        return history_ids

    except Exception as e:
        file_logger.error(f"读取历史记录文件 {file_path} 失败: {e}")
        return set()

def save_to_history_file(file_path: str, url: str):
    """将已处理的URL保存到历史记录文件"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(url + '\n')
        file_logger.debug(f"URL已保存到历史记录: {url}")
    except Exception as e:
        file_logger.error(f"保存URL到历史记录文件 {file_path} 失败: {e}")

def load_at_id(file_path: str) -> set[str]:
    """加载已知at_id"""
    at_id_set: set[str] = set()
    try:
        if not os.path.exists(file_path):
            file_logger.debug(f"文件 '{file_path}' 不存在")
            return at_id_set

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                at_id = line.strip()
                if at_id:
                    at_id_set.add(at_id)
        file_logger.debug(f"从 '{file_path}' 加载了 {len(at_id_set)} 个 @ 消息 ID")
        return at_id_set

    except Exception as e:
        file_logger.error(f"读取文件 '{file_path}' 失败: {e}", exc_info=True)
        return at_id_set

def save_at_id_to_file(file_path: str, at_id: str):
    """保存at_id"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(str(at_id) + '\n')

def load_reply_id(file_path: str) -> set[str]:
    """加载已知reply_id"""
    reply_id_set: set[str] = set()
    try:
        if not os.path.exists(file_path):
            file_logger.debug(f"文件 '{file_path}' 不存在")
            return reply_id_set

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                reply_id = line.strip()
                if reply_id:
                    reply_id_set.add(reply_id)
        file_logger.debug(f"从 '{file_path}' 加载了 {len(reply_id_set)} 个 回复消息 ID")
        return reply_id_set

    except Exception as e:
        file_logger.error(f"读取文件 '{file_path}' 失败: {e}", exc_info=True)
        return reply_id_set

def save_reply_id_to_file(file_path: str, reply_id: str):
    """保存reply_id"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(str(reply_id) + '\n')

def load_message_id(file_path: str):
    """加载已知msg_seqno_id"""
    msg_id_set: set[str] = set()
    try:
        if not os.path.exists(file_path):
            file_logger.debug(f"文件 '{file_path}' 不存在")
            return msg_id_set

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                reply_id = line.strip()
                if reply_id:
                    msg_id_set.add(reply_id)
        file_logger.debug(f"从 '{file_path}' 加载了 {len(msg_id_set)} 个 私信消息 ID")
        return msg_id_set
    except Exception as e:
        file_logger.error(f"读取文件 '{file_path}' 失败: {e}", exc_info=True)
        return msg_id_set

def save_msg_id_to_file(file_path: str, msg_id: str):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(str(msg_id) + '\n')