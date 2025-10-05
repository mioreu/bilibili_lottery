import logging
from pathlib import Path
import re
from typing import List, Tuple, Set
from utils.data_extractors import extract_dynamic_id, extract_video_bvid

file_logger = logging.getLogger("Bilibili.file")

def load_origin_urls_from_file(file_path: str) -> Tuple[List[str], List[str]]:
    """从文件加载并清洗URL"""
    try:
        content = Path(file_path).read_text(encoding='utf-8')
    except FileNotFoundError:
        file_logger.error(f"文件未找到: {file_path}")
        return [], []

    URL_PATTERN = re.compile(
        r'https?://(?:www\.|m\.)?bilibili\.com/'
        r'(?:video/(?:BV\w+|av\d+)|opus/\d+|dynamic/\d+)\S*|'
        r'https?://t\.bilibili\.com/\d+(?=\D|$)'
    )

    seen_ids = set()
    video_urls, dynamic_urls = [], []
    
    for url in URL_PATTERN.findall(content):
        cleaned_url = url.split('?')[0].split('#')[0]
        
        if '/video/' in cleaned_url:
            if (bvid := extract_video_bvid(cleaned_url)) and bvid not in seen_ids:
                seen_ids.add(bvid)
                video_urls.append(cleaned_url)
        elif (d_id := extract_dynamic_id(cleaned_url)) and d_id not in seen_ids:
            seen_ids.add(d_id)
            dynamic_urls.append(cleaned_url)
    
    return dynamic_urls, video_urls