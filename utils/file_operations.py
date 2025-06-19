import os
import re
import logging
from datetime import datetime
from typing import List, Tuple, Optional
from utils.data_extractors import extract_dynamic_id
logger = logging.getLogger(__name__)


def load_origin_urls_from_file(file_path: str) -> List[Tuple[str, Optional[str]]]:
    """加载URL"""
    urls: List[Tuple[str, Optional[str]]] = []

    bili_url_pattern = re.compile(
        r'https?://(?:www\.|m\.)?bilibili\.com/(?:opus/\d+|dynamic/\d+)\S*|'
        r'https?://t\.bilibili\.com/\d+(?=[^\d]|$)'
    )
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        found_urls = bili_url_pattern.findall(content)

        for full_url in found_urls:
            # 检查URL是否已存在，避免重复
            if all(url_item[0] != full_url for url_item in urls):
                urls.append((full_url, None))
            else:
                logger.debug(f"URL '{full_url}' 已存在，跳过。")

        logger.info(f"成功从 '{file_path}' 中提取到 {len(urls)} 个有效动态URL。")
        return urls

    except Exception as e:
        logger.error(f"读取或解析源文件 '{file_path}' 失败: {e}", exc_info=True)
        return urls


def read_history_from_file(file_path: str) -> set:
    """加载已处理的动态ID"""
    history_ids = set()
    if not os.path.exists(file_path):
        return history_ids

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                dynamic_id = extract_dynamic_id(url)
                if dynamic_id:
                    history_ids.add(dynamic_id)
        logger.debug(f"成功加载 {len(history_ids)} 个已完成操作的动态ID")
        return history_ids
    except Exception as e:
        logger.error(f"读取历史记录文件 {file_path} 失败: {e}")
        return set()


def save_to_history_file(file_path: str, url: str):
    """将已处理的URL保存到历史记录文件"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)  # 确保目录存在
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(url + '\n')
        logger.debug(f"URL已保存到历史记录: {url}")
    except Exception as e:
        logger.error(f"保存URL到历史记录文件 {file_path} 失败: {e}")


def save_parsed_content(file_path: str, dynamic_id: str, content: str, original_url: str):
    """将解析后的动态内容保存到文件"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(f"Original URL: {original_url}\n")
            f.write(f"Content:\n{content}\n")
            f.write("-" * 50 + "\n\n")
        logger.debug(f"已保存动态 {dynamic_id} 的解析内容。")
    except Exception as e:
        logger.error(f"保存解析内容到文件 {file_path} 失败: {e}")