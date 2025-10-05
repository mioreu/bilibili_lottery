import logging
import os
import sys
from typing import List
from utils.logger_setup import setup_logger as custom_setup_logger
from api.bilibili_client import BilibiliClient
from run import load_config
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
logger = logging.getLogger("Bilibili.FollowLottery")

def follow_and_forward():
    """跟随转发抽奖"""
    config = load_config()
    custom_setup_logger(
        log_level=config['log_level'],
        log_file=config['file_paths']['main_log'],
        error_file=config['file_paths']['error_log']
    )
    acc_config = config["accounts"][0]
    client = BilibiliClient(acc_config["cookie"], acc_config["remark"])

    followed_users_mids: List[int] = config.get("followed_user", [])
    if not followed_users_mids:
        logger.error("配置文件中 'followed_user' 列表为空，无法执行")
        return

    all_urls: List[str] = []

    for mid in followed_users_mids:
        success, msg, urls = client.fetch_user_forwarded_dynamic_url(mid)

        if success and urls:
            logger.info(f"成功获取用户 {mid} 的 {len(urls)} 条转发动态链接")
            all_urls.extend(urls)
        else:
            logger.error(f"获取用户 {mid} 的转发动态失败: {msg}")

    if all_urls:
        logger.debug("\n所有被跟随用户的所有转发动态原始链接如下:")
        for url in set(all_urls):
            logger.debug(url)
    else:
        logger.warning("未找到任何转发动态链接")

    return all_urls