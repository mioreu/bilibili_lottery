import logging
import os
import random
import sys
import time
from typing import List
from api.bilibili_client import BilibiliClient
from run import load_config
from utils.logger_setup import setup_logger as custom_setup_logger
from utils import database_operations
from services.telegram_notifier import send_win_notification, WinItem

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
logger = logging.getLogger("Bilibili.Check")

def check_lottery():
    """检查中奖"""
    config = load_config()
    db_cache_path = config['file_paths']['database_cache']
    custom_setup_logger(
        log_level=config['log_level'],
        log_file=config['file_paths']['main_log'],
        error_file=config['file_paths']['error_log']
    )

    logger.info("=" * 20 + "开始检查中奖" + "=" * 20)
    accounts = config.get("accounts", [])
    win_keywords = config.get("win_keywords")
    logger.info(f"将使用以下关键词进行检测: {win_keywords}")

    all_wins: List[WinItem] = []

    for acc_config in accounts:
        all_messages = []
        remark = acc_config.get('remark', '未知账号')

        logger.info("=" * 15 + f"正在检查账号 [{remark}]" + "=" * 15)
        time.sleep(random.uniform(1, 2))
        client = BilibiliClient(cookie=acc_config["cookie"], remark=remark)
        if not client.is_valid:
            logger.warning(f"账号 [{remark}] 的 Cookie 无效或已过期，无法检查")
            continue

        client.db_path = os.path.join(db_cache_path, f"uid{client.mid}.db")
        database_operations.init_db(client.db_path)

        # 获取消息
        success_reply, result_reply = client.get_reply_message()
        success_at, result_at = client.get_at_message()
        success_session, result_session = client.get_session_messages()

        # 处理回复消息
        if success_reply:
            for msg in result_reply:
                msg['type'] = '回复'
            all_messages.extend(result_reply)
        else:
            logger.error(f"获取账号 [{remark}] 的回复消息失败: {result_reply}")

        # 处理@消息
        if success_at:
            for msg in result_at:
                msg['type'] = '艾特'
            all_messages.extend(result_at)
        else:
            logger.error(f"获取账号 [{remark}] 的@消息失败: {result_at}")

        # 处理私信
        if success_session:
            for msg in result_session:
                msg['type'] = '未读私信'
            all_messages.extend(result_session)
        else:
            logger.error(f"获取账号 [{remark}] 的私信失败: {result_session}")

        if not all_messages:
            logger.info(f"账号 [{remark}] 没有发现新消息（包括私信、@和回复）")
            continue

        found_win_for_account = False
        for msg in all_messages:
            content = msg.get('content', '')
            source = msg.get('type', '未知来源')
            nickname = msg.get('nickname', '未知')
            uid = msg.get('uid') or msg.get('sender_uid')
            url = msg.get('url',
                          f"https://message.bilibili.com/#/whisper/mid{msg.get('talker_id')}" if 'talker_id' in msg else '无直达链接')

            for keyword in win_keywords:
                if keyword in content:
                    logger.warning("=" * 20 + "\n"
                                              f"恭喜！账号 [{remark}] 可能中奖了！\n"
                                              f"来源: {source}\n"
                                              f"用户名: {nickname}\n"
                                              f"UID: {uid}\n"
                                              f"消息内容: {content}\n"
                                              f"链接: {url}"
                                   )

                    all_wins.append({
                        'account_remark': remark,
                        'source': source,
                        'nickname': nickname,
                        'uid': str(uid),
                        'content': content,
                        'url': url
                    })

                    found_win_for_account = True
                    break

        if not found_win_for_account:
            logger.info(f"账号 [{remark}] 未检测到明确的中奖信息")

        time.sleep(random.uniform(2, 5))
    if not all_wins:
        logger.info("所有账号均未检测到新的中奖信息")
    send_win_notification(config, all_wins)