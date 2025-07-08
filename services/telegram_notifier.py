import logging
import os
import urllib3
from datetime import datetime
from typing import Dict, Any, List, TypedDict
import requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
telegram_logger = logging.getLogger("Bilibili.TelegramBot")

class FailureItem(TypedDict):
    type: str
    reason: str
    url: str
    detail: str
    account_remark: str

TELEGRAM_BOT_API = "https://api.telegram.org/bot"

def notification_message(stats: Dict[str, int], duration: float, failures: List[FailureItem]) -> str:
    """构建Telegram通知消息"""
    m, s = divmod(int(duration), 60)
    message = [
        "<strong>博士，这里是澄闪的任务报告~</strong>\n\n",
        f"📊 <b>操作统计：</b>\n",
        f"• 点赞成功：{stats.get('like_success', 0)}次\n",
        f"• 转发成功：{stats.get('repost_success', 0)}次\n",
        f"• 关注成功：{stats.get('follow_success', 0)}次\n",
        f"• 评论成功：{stats.get('comment_success', 0)}次\n",
        f"• 失败总数：{stats.get('total_failures', 0)}次\n\n",
        f"• 用时：{m}分{s}秒\n\n"
    ]

    if failures:
        message.append("<b>需要关注的异常详情：</b>\n")
        # 只显示前10条失败详情
        for i, failure in enumerate(failures[:10], 1):
            processed_reason = str(failure.get('reason', '未知原因')).replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
            processed_url = str(failure.get('url', '无链接')).replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
            processed_detail = str(failure.get('detail', '无详情')).replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
            account_remark = str(failure.get('account_remark', '未知账号')).replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')

            message.append(
                f"{i}.[{failure.get('type', '未知类型')}] 账号[{account_remark}] {processed_reason}\n"
                f"   ➤ 动态：<a href='{failure.get('url', '#')}'>{processed_url[:80]}...</a>\n"
                f"   ➤ 详情：{processed_detail[:150]}...\n\n"
            )
        if len(failures) > 10:
            message.append(f"... 还有 {len(failures) - 10} 条更多失败详情，请查看日志文件哦。\n\n")
    else:
        message.append("所有操作都顺利完成啦！澄闪有好好完成任务哦~")
    message.append("\n\n<em>博士要记得检查日志文件呢，澄闪会继续努力的！</em>")
    
    return "".join(message)

def send_telegram_notification(config: Dict[str, Any],stats: Dict[str, int],start_time: float,failures: List[FailureItem]):
    """发送Telegram通知消息"""
    telegram_config = config.get("telegram", {})
    token = telegram_config.get("bot_token")
    chat_id = telegram_config.get("chat_id")
    proxies = config.get("proxy")
    send_message = f"{TELEGRAM_BOT_API}{token}/sendMessage"
    send_document = f"{TELEGRAM_BOT_API}{token}/sendDocument"
    files_to_send = [config['file_paths']['main_log']]

    if not telegram_config.get("enable"):
        telegram_logger.info("Telegram 通知已禁用。")
        return
    if not token or not chat_id:
        telegram_logger.warning("缺少Telegram配置参数 (bot_token 或 chat_id)，跳过发送通知。")
        return
    if os.path.getsize(config['file_paths']['error_log']) > 0:
        files_to_send.append(config['file_paths']['error_log'])

    # 构建消息内容
    text_message = notification_message(stats, datetime.now().timestamp() - start_time, failures)
    payload = {
        "chat_id": chat_id,
        "text": text_message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    response_message = requests.post(
        url=send_message,
        json=payload,
        proxies=proxies,
        verify=False,
        timeout=30
    )

    response_message.raise_for_status()
    response_json = response_message.json()

    if response_json.get("ok"):
        message_id = response_json.get("result", {}).get("message_id", "N/A")
        telegram_logger.info(f"Telegram 通知发送成功 | 消息ID: {message_id}")
    else:
        telegram_logger.error(f"Telegram API 返回错误 | Code: {response_json.get('error_code', 'N/A')} | Description: {response_json.get('description', '无描述')}")


    for file_path in files_to_send:
        try:
            with open(file_path, 'rb') as f:
                file_name = os.path.basename(file_path)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = f"{timestamp}_{file_name}"

                response_file = requests.post(
                    url=send_document,
                    proxies=proxies,
                    data={'chat_id': chat_id},
                    files={'document': (safe_name, f)},
                    timeout=30
                )
                response_file.raise_for_status()
                response_json = response_file.json()

                if response_json.get("ok"):
                    message_id = response_json.get("result", {}).get("message_id", "N/A")
                    telegram_logger.info(f"Telegram 文件 {file_name} 发送成功 | 消息ID: {message_id}")
                else:
                    telegram_logger.error(
                        f"Telegram API 返回错误 | Code: {response_json.get('error_code', 'N/A')} | Description: {response_json.get('description', '无描述')}")

        except Exception as e:
            telegram_logger.exception(f"[Telegram] 发送文件 {file_name} 时发生异常: {e}")