import logging
import os
import sys
import time
import random
from run import load_config
from api.bilibili_client import BilibiliClient
from utils.logger_setup import setup_logger as custom_setup_logger

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
logger = logging.getLogger("Bilibili.Check")

def check_lottery():
    """检查中奖"""
    config = load_config()
    custom_setup_logger(
        log_level=config.get('log_level', 'INFO'),
        log_file=config.get('file_paths', {}).get('main_log', 'bilibili.log'),
        error_file=config.get('file_paths', {}).get('error_log', 'error.log')
    )

    logger.info("=" * 20 + "开始检查中奖" + "=" * 20)
    accounts = config.get("accounts", [])
    win_keywords = config.get("win_keywords", ["中奖"])
    logger.debug(f"将使用以下关键词进行检测: {win_keywords}")
    found_any_wins = False

    for acc_config in accounts:
        remark = acc_config.get('remark', '未知账号')
        if not acc_config.get("enabled", True):
            logger.info(f"账号 [{remark}] 已在配置中禁用，跳过检查")
            continue

        logger.info("=" * 15 + f"正在检查账号 [{remark}]" + "=" * 15)
        time.sleep(random.uniform(1, 2))
        client = BilibiliClient(cookie=acc_config["cookie"], remark=remark)
        if not client.is_valid:
            logger.warning(f"账号 [{remark}] 的 Cookie 无效或已过期，无法检查")
            continue

        result = client.get_at_messages(config)
        if result is None:
            logger.error(
                f"账号 [{remark}] 获取 '@' 消息失败：get_at_messages() 返回 None\n" + "=" * 20)
            continue

        success, messages = result
        if not success:
            logger.error(f"账号 [{remark}] 获取 '@' 消息失败: {messages}\n" + "=" * 20)
            continue
        if not messages:
            logger.info(f"账号 [{remark}] 没有发现新的 '@' 消息")
            continue

        logger.debug(f"账号 [{remark}] 成功获取 {len(messages)} 条 '@' 消息")
        found_win_for_account = False
        for message_data in messages:
            content = message_data.get('content', '')
            nickname = message_data.get('nickname', '')
            uid = message_data.get('uid', '')
            url = message_data.get('url', '')

            for keyword in win_keywords:
                if keyword in content:
                    logger.warning("=" * 20 + "\n"
                                    f"恭喜！账号 [{remark}] 可能中奖了！\n"
                                    f"用户名: {nickname}\n"
                                    f"UID: {uid}\n"
                                    f"消息内容: {content}\n"
                                    f"链接: {url if url else '未提供链接'}"
                                )
                    found_win_for_account = True
                    found_any_wins = True
                    break

        if not found_win_for_account:
            logger.info(f"账号 [{remark}] 未检测到明确的中奖信息")

        time.sleep(random.uniform(2, 5))

    if not found_any_wins:
        logger.info("所有账号均未检测到新的中奖信息")