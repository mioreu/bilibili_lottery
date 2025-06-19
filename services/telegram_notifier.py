import requests
import logging
import os
import time
from typing import Dict, Any, List, Optional, TypedDict
from datetime import datetime

telegram_logger = logging.getLogger("Bilibili.TelegramBot")

class FailureItem(TypedDict):
    type: str
    reason: str
    url: str
    detail: str
    account_remark: str


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


def validate_proxy_config_telegram(proxy_config: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """验证代理配置"""
    if not proxy_config or not proxy_config.get("enable"):
        return None

    validated = {}
    allowed_schemes = {
        'http': ['http://', 'socks5://'],
        'https': ['https://', 'socks5://', 'http://']
    }

    for proto in ['http', 'https']:
        if url := proxy_config.get(proto):
            if any(url.startswith(p) for p in allowed_schemes.get(proto, [])):
                validated[proto] = url
                display_url = url.split('@')[-1] if '@' in url else url
                telegram_logger.debug(f"有效 {proto.upper()} 代理已配置 (Telegram): {display_url}")
            else:
                allowed_formats_str = ' 或 '.join(allowed_schemes.get(proto, []))
                telegram_logger.warning(f"Telegram代理中无效 {proto.upper()} 代理格式: {url[:30]}... (应以 {allowed_formats_str} 开头)")

    return validated or None


def send_telegram_notification(
    config: Dict[str, Any],
    stats: Dict[str, int],
    start_time: float,
    failures: List[FailureItem],
    message_type: str = "summary"
) -> None:
    """发送Telegram通知消息"""
    telegram_config = config.get("telegram", {})
    if not telegram_config.get("enable"):
        telegram_logger.info("Telegram 通知已禁用。")
        return

    token = telegram_config.get("bot_token")
    chat_id = telegram_config.get("chat_id")

    if not token or not chat_id:
        telegram_logger.warning("缺少Telegram配置参数 (bot_token 或 chat_id)，跳过发送通知。")
        return

    # 验证并获取代理配置
    proxies = validate_proxy_config_telegram(config.get("proxy"))

    try:
        telegram_api_url = f"https://api.telegram.org/bot{token}/sendMessage"
        
        # 构建消息内容
        text_message = notification_message(stats, datetime.now().timestamp() - start_time, failures)

        payload = {
            "chat_id": chat_id,
            "text": text_message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        telegram_logger.debug(f"正在发送 Telegram 通知到 chat_id: {chat_id}")

        response = requests.post(
            url=telegram_api_url,
            json=payload,
            proxies=proxies,
            verify=False,
            timeout=30
        )
        
        response.raise_for_status()

        response_json = response.json()
        if response_json.get("ok"):
            message_id = response_json.get("result", {}).get("message_id", "N/A")
            telegram_logger.info(f"Telegram 通知发送成功 | 消息ID: {message_id}")
             
        else:
            telegram_logger.error(f"Telegram API 返回错误 | Code: {response_json.get('error_code', 'N/A')} | Description: {response_json.get('description', '无描述')}")
            
    except requests.exceptions.Timeout:
        telegram_logger.error("发送 Telegram 通知请求超时。")
    except requests.exceptions.RequestException as e:
        telegram_logger.error(f"发送 Telegram 通知时发生网络错误: {e}")
    except Exception as e:
        telegram_logger.exception(f"发送 Telegram 通知时发生未知错误: {e}")


def send_telegram_files(config: Dict[str, Any]):
    """发送文件"""
    telegram_config = config.get("telegram", {})
    if not telegram_config.get("enable"):
        return
    
    bot_token = telegram_config.get('bot_token')
    chat_id = telegram_config.get('chat_id')
    proxy_config = config.get('proxy')
    
    files_to_send = []
    if os.path.exists(config['file_paths']['parsed_dynamics']) and os.path.getsize(config['file_paths']['parsed_dynamics']) > 0:
        files_to_send.append(config['file_paths']['parsed_dynamics'])
    if os.path.exists(config['file_paths']['error_log']) and os.path.getsize(config['file_paths']['error_log']) > 0:
        files_to_send.append(config['file_paths']['error_log'])
    
    if not files_to_send:
        telegram_logger.info("没有要发送的文件。")
        return

    # 配置代理
    proxies = validate_proxy_config_telegram(proxy_config)

    # 发送文件
    for file_path in files_to_send:
        try:
            with open(file_path, 'rb') as f:
                file_name = os.path.basename(file_path)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = f"{timestamp}_{file_name}"
                
                response = requests.post(
                    url=f"https://api.telegram.org/bot{bot_token}/sendDocument",
                    proxies=proxies,
                    data={'chat_id': chat_id},
                    files={'document': (safe_name, f)},
                    timeout=30
                )
                
                if response.status_code != 200:
                    telegram_logger.error(f"[Telegram] 文件发送失败: {file_name} | 响应: {response.text}")
                else:
                    telegram_logger.info(f"[Telegram] 已发送文件: {file_name}")
            
            time.sleep(3) # 每个文件发送后等待3秒
        
        except Exception as e:
            telegram_logger.exception(f"[Telegram] 发送文件 {file_name} 时发生异常: {e}")