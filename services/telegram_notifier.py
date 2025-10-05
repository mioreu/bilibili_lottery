import logging
import os
import urllib3
import re
from datetime import datetime
from typing import Dict, Any, List, TypedDict
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
telegram_logger = logging.getLogger("Bilibili.TelegramBot")

TELEGRAM_BOT_API = "https://api.telegram.org/bot"


class FailureItem(TypedDict):
    type: str
    reason: str
    url: str
    detail: str
    account_remark: str


class WinItem(TypedDict):
    """中奖详情结构"""
    account_remark: str
    source: str
    nickname: str
    uid: str
    content: str
    url: str


def escape_markdown_v2(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    text = text.replace('\\', '\\\\')
    return re.sub(r'([_*[\]()~`>#+={}.!-])', r'\\\1', text)


def notification_message(stats: Dict[str, int], duration: float, failures: List[FailureItem]) -> str:
    """构建Telegram通知"""
    m, s = divmod(int(duration), 60)

    message = [
        escape_markdown_v2("博士，这里是澄闪的任务报告~") + "\n\n",
        "*📊 操作统计：*\n",
        f"• 爬取成功：{stats.get('crawl', 0)}次\n",
        f"• 点赞成功：{stats.get('like', 0)}次\n",
        f"• 转发成功：{stats.get('repost', 0)}次\n",
        f"• 关注成功：{stats.get('follow', 0)}次\n",
        f"• 评论成功：{stats.get('comment', 0)}次\n",
        f"• 失败总数：{stats.get('failures', 0)}次\n\n",
        f"• 用时：{m}分{s}秒\n\n"
    ]

    if failures:
        message.append("*需要关注的异常详情：*\n")
        # 只显示前10条失败详情
        for i, failure in enumerate(failures[:10], 1):
            processed_reason = escape_markdown_v2(str(failure.get('reason', '未知原因')))
            processed_url_text = escape_markdown_v2(str(failure.get('url', '无链接'))[:80])
            processed_detail = escape_markdown_v2(str(failure.get('detail', '无详情'))[:150])
            account_remark = escape_markdown_v2(str(failure.get('account_remark', '未知账号')))

            raw_url = str(failure.get('url', '#'))

            message.append(
                f"{i}\\.[{failure.get('type', '未知类型')}] 账号[{account_remark}] {processed_reason}\n"
                f"   ➤ 动态：[{processed_url_text}]({raw_url})\n"
                f"   ➤ 详情：{processed_detail}\n\n"
            )
        if len(failures) > 10:
            message.append(
                escape_markdown_v2(f"... 还有 {len(failures) - 10} 条更多失败详情，请查看日志文件哦。") + "\n\n")
    else:
        message.append(escape_markdown_v2("所有操作都顺利完成啦！澄闪有好好完成任务哦~"))

    message.append("\n\n_博士要记得检查日志文件呢，澄闪会继续努力的！_")

    return "".join(message)


def win_notification_message(win_details: List[WinItem]) -> str:
    """中奖通知"""
    total_wins = len(win_details)

    if not win_details:
        return escape_markdown_v2("澄闪已完成中奖检查，未发现新的中奖信息")

    header = [
        f"*{escape_markdown_v2(f'🎉 澄闪发现 {total_wins} 条中奖信息！ 🎉')}*\n",
        f"*{escape_markdown_v2(' '*8 + '----- 详情列表 -----')}*\n"
    ]

    details = []
    for i, item in enumerate(win_details[:10], 1):
        remark = escape_markdown_v2(item.get('account_remark', '未知账号'))
        source = escape_markdown_v2(item.get('source', '未知来源'))
        nickname = escape_markdown_v2(item.get('nickname', '未知'))
        uid = escape_markdown_v2(item.get('uid', 'N/A'))
        content_raw = item.get('content', '无内容')
        content = escape_markdown_v2(str(content_raw)[:150] + ('...' if len(content_raw) > 150 else ''))

        raw_url = str(item.get('url', '#'))

        details.append(
            f"*{i}\\.\n账号：{remark}*\n"
            f"*来源：{source}*\n"
            f"*用户：{nickname} \\(UID: {uid}\\)*\n"
            f"*内容：{content}*\n"
            f"*链接：[点我跳转]({raw_url})*\n\n"
        )
    if total_wins > 10:
        details.append(escape_markdown_v2(f"... 还有 {total_wins - 10} 条中奖信息，请自行查看") + "\n\n")

    footer = [
        "\n",
        f"_{escape_markdown_v2('请尽快前往B站查看和兑奖哦！')}_"
    ]

    return "".join(header + details + footer)

def _send_telegram_request(config: Dict[str, Any], text_message: str, file_paths: List[str] = None):
    """发送通知"""
    telegram_config = config.get("telegram", {})
    token = telegram_config.get("bot_token")
    chat_id = telegram_config.get("chat_id")
    proxies = config.get("proxy")
    send_message = f"{TELEGRAM_BOT_API}{token}/sendMessage"
    send_document = f"{TELEGRAM_BOT_API}{token}/sendDocument"
    files_to_send = file_paths if file_paths else []

    if not telegram_config.get("enable"):
        telegram_logger.info("Telegram 通知已禁用。")
        return
    if not token or not chat_id:
        telegram_logger.warning("缺少Telegram配置参数 (bot_token 或 chat_id)，跳过发送通知")
        return
    telegram_logger.debug(f"准备发送的消息内容（MarkdownV2）：\n{text_message}")
    payload = {
        "chat_id": chat_id,
        "text": text_message,
        "parse_mode": "MarkdownV2",
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
        telegram_logger.info(f"Telegram 消息发送成功 | 消息ID: {message_id}")
    else:
        telegram_logger.error(
            f"Telegram API 返回错误 | Code: {response_json.get('error_code', 'N/A')} | Description: {response_json.get('description', '无描述')}")

    for file_path in files_to_send:
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            telegram_logger.info(f"跳过发送空文件或不存在的文件: {file_path}")
            continue

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

def send_task_report_notification(config: Dict[str, Any], stats: Dict[str, int], start_time: float,
                                  failures: List[FailureItem]):
    """构建任务报告消息并发送，附带日志文件"""
    duration = datetime.now().timestamp() - start_time
    text_message = notification_message(stats, duration, failures)

    files_to_send = [config['file_paths']['main_log']]
    if os.path.getsize(config['file_paths']['error_log']) > 0:
        files_to_send.append(config['file_paths']['error_log'])

    _send_telegram_request(config, text_message, files_to_send)

def send_win_notification(config: Dict[str, Any], win_details: List[WinItem]):
    """构建中奖消息并发送"""
    text_message = win_notification_message(win_details)
    _send_telegram_request(config, text_message)