import logging
import os
import re
from typing import List

from utils.data_extractors import extract_dynamic_id

file_logger = logging.getLogger("Bilibili.file")


def load_origin_urls_from_file(file_path: str) -> List[str]:
    """加载URL"""
    urls: List[str] = []
    bili_url_pattern = re.compile(
        r'https?://(?:www\.|m\.)?bilibili\.com/(?:opus/\d+|dynamic/\d+)\S*|'
        r'https?://t\.bilibili\.com/\d+(?=\D|$)'
    )

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        found_urls = bili_url_pattern.findall(content)

        # 添加url并去重
        for full_url in found_urls:
            if full_url not in urls:
                urls.append(full_url)
            else:
                file_logger.debug(f"URL '{full_url}' 已存在，跳过。")
        return urls

    except Exception as e:
        file_logger.error(f"读取或解析源文件 '{file_path}' 失败: {e}", exc_info=True)
        return urls

def read_history_from_file(file_path: str) -> set:
    """加载已处理的动态ID"""
    history_ids = set()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                dynamic_id = extract_dynamic_id(url)
                if dynamic_id:
                    history_ids.add(dynamic_id)
        file_logger.debug(f"加载 {len(history_ids)} 个已完成操作的动态ID")
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
            file_logger.debug(f"文件 '{file_path}' 不存在，返回空集合。")
            return at_id_set

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                at_id = line.strip()
                if at_id:
                    at_id_set.add(at_id)
        file_logger.debug(f"从 '{file_path}' 加载了 {len(at_id_set)} 个 @ 消息 ID。")
        return at_id_set

    except Exception as e:
        file_logger.error(f"读取文件 '{file_path}' 失败: {e}", exc_info=True)
        return at_id_set

def save_at_id_to_file(file_path: str, at_id: str):
    """保存at_id"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(str(at_id) + '\n')
    file_logger.debug(f"@ 消息 ID 已保存到历史记录: {at_id}")
