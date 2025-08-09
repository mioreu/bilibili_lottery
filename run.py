import json
import logging
import os
import random
import sys
import time
from typing import List, Dict, Any, Tuple, Callable
import urllib3
from api.bilibili_client import BilibiliClient
from services.deepseek_ai import generate_comment
from services.repost_video import handle_video_reposting
from services.telegram_notifier import send_telegram_notification, FailureItem
from utils.data_extractors import extract_dynamic_id, check_follow_status, extract_topic_and_fixed_at, check_at, \
    extract_video_bvid
from utils.file_operations import load_origin_urls_from_file, read_history_from_file, save_to_history_file
from utils.logger_setup import setup_logger as custom_setup_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger("Bilibili.Main")


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """加载配置"""
    config_full_path = os.path.join(PROJECT_ROOT, config_path)
    if not os.path.exists(config_full_path):
        raise FileNotFoundError(f"配置文件 {config_full_path} 未找到")

    try:
        with open(config_full_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        # 过滤掉禁用的账号
        config["accounts"] = [acc for acc in config.get("accounts", []) if acc.get("enabled", True)]
        return config
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件格式错误: {e}") from e


def _get_comment_content(client: BilibiliClient, config: Dict[str, Any], dynamic_text: str, oid: int, comment_type: int) -> str:
    """生成或选择评论内容"""
    acc_config = client.account_config
    deepseek_config = config["deepseek"]
    comment_content = ""

    reference_comment = client.get_two_comment(oid, comment_type)
    dyn_content = f"{dynamic_text}\n{reference_comment}"

    # 尝试生成评论
    if acc_config.get("ai_comment"):
        comment, _ = generate_comment(
            config,
            name=client.remark,
            prompt=f"请根据以下B站动态内容生成一条评论:\n\n{dynamic_text}\n可根据以下参考评论生成:{reference_comment}",
            api_key=deepseek_config.get("deepseek_api_key"),
            model=deepseek_config.get("deepseek_model"),
            temperature=deepseek_config.get("temperature")
        )
        if comment:
            comment_content = comment
        else:
            logger.warning("评论生成失败，将尝试使用固定评论")

    # 若评论生成失败，则回退到固定评论
    if not comment_content and acc_config.get("use_fixed_comment") and acc_config.get("fixed_comments"):
        comment_content = random.choice(acc_config["fixed_comments"])

    # 添加话题,at,表情
    if comment_content:
        topic = extract_topic_and_fixed_at(dyn_content)
        at_num = check_at(config, dyn_content)
        at_list = config.get("at_list", [])
        emoticons = acc_config.get("emoticons", [])
        if at_num > 4: at_num = 0
        selected_ats_list = random.sample(at_list, at_num)
        at = " ".join(selected_ats_list) if selected_ats_list else ""
        emoticon = random.choice(emoticons) if emoticons else ""
        if topic:
            comment_content = f"{topic} {comment_content}"
        return f"{at} {comment_content}{emoticon}"

    return ""

def _execute_action(
        action_func: Callable[..., Tuple[bool, str]],
        action_args: list,
        action_type: str,
) -> Tuple[bool, str]:
    success, message = action_func(*action_args)
    if not success:
        logger.error(f"{action_type} 操作失败 | 原因: {message}")
    else:
        logger.info(f"{message}")
    return success, message


def process_dynamic(config: Dict[str, Any], url: str, dynamic_id: str, bili_clients: List[BilibiliClient], comment_fail_counts: Dict[str, int]) -> \
        Tuple[Dict[str, int], List[FailureItem]]:
    """处理动态"""
    stats = {"like": 0, "repost": 0, "follow": 0, "comment": 0, "crawl": 0, "failures": 0}
    failures = []

    # 获取动态内容
    success, text, details = bili_clients[0].fetch_dynamic_content(dynamic_id)
    if not success:
        failures.append(
            {"type": "抓取", "reason": "无法获取动态内容", "url": url, "detail": text, "account_remark": "N/A"})
        stats["failures"] += 1
        return stats, failures

    stats["crawl"] += 1
    logger.debug(f"动态内容已获取:\n{text}")
    comment_type = details["comment_type"]
    oid = details["comment_oid"]
    mid = details["author_mid"]
    # 对每个账号执行操作
    for account_index, client in enumerate(bili_clients, 1):
        action_delay = random.uniform(config['action_delay_min_seconds'], config['action_delay_max_seconds'])
        acc_config = client.account_config
        remark = client.remark

        if not acc_config.get('enabled'):
            logger.info(f"[账号 {account_index}/{len(bili_clients)}] {remark} 已被禁用，跳过本次动态处理")
            continue

        if mid in [100680137, 280604312]:
            logger.warning("动态作者为“你的抽奖工具人”，跳过")
            continue
        if not config.get("enable_interactive_lottery"):
            if details["is_lottery"]:
                logger.info(f"动态是互动抽奖，已跳过")
                continue
        logger.info(f"[账号 {account_index}/{len(bili_clients)}] {remark} 正在执行操作...")

        # 关注
        code, msg = check_follow_status(client, mid)
        if code in [2, 6, 128]:
            logger.info(f"{msg}")
            stats["follow"] += 1
            if code == 128:
                continue
        elif code == 0:
            success, message = _execute_action(client.follow_user, [mid], "关注")
            if success:
                stats["follow"] += 1
            else:
                failures.append({"type": "关注", "reason": message, "url": url, "detail": "", "account_remark": remark})
                stats["failures"] += 1
        time.sleep(action_delay)

        # 点赞
        success, message = _execute_action(client.like_dynamic, [dynamic_id], "点赞")
        if success:
            stats["like"] += 1
        else:
            failures.append({"type": "点赞", "reason": message, "url": url, "detail": "", "account_remark": remark})
            stats["failures"] += 1
        time.sleep(action_delay)

        # 评论
        comment_content = _get_comment_content(client, config, text, oid, comment_type)
        if comment_content:
            comment_args = [dynamic_id, comment_content, comment_type, oid]
            success, message, rpid = client.comment_dynamic(*comment_args)
            if success:
                stats["comment"] += 1
                logger.info(message)
                logger.info("等待 8 秒后检查评论状态...")
                time.sleep(8)
                status_success, status_details = client.check_comment_status(oid, int(rpid), comment_type)
                if status_success:
                    status = status_details.get('status')
                    status_code = status_details.get('code')
                    logger.info(f"评论状态检查完成：{status}")
                    if status_code != 0:
                        comment_fail_counts[remark] += 1
                        failures.append({"type": "评论", "reason": status, "url": url, "detail": comment_content,
                                       "account_remark": remark})
                        if comment_fail_counts[remark] >= 3:
                            logger.error(f"账号 {remark} 评论仅自己可见次数超过3次，已禁用该账号")
                            client.account_config["enabled"] = False
                else:
                    logger.error(f"评论状态检查失败：{status_details.get('message', '未知错误')}")
            else:
                logger.error(f"评论操作失败 | 原因: {message}")
                failures.append({"type": "评论", "reason": message, "url": url, "detail": comment_content, "account_remark": remark})
                stats["failures"] += 1
        else:
            logger.error(f"无可用的评论内容")
        time.sleep(action_delay)

        # 转发
        if config.get("use_comment_content"):
            repost_content = comment_content
        elif acc_config.get("use_fixed_repost") and acc_config.get("fixed_reposts"):
            repost_content = random.choice(acc_config["fixed_reposts"])
        else:
            repost_content = "转发动态"
        # 加码抽奖
        if details['is_forward']:
            repost_content = f"{repost_content}//@{details['author_name']}:{text}"

        success, message = _execute_action(client.repost_dynamic, [dynamic_id, repost_content, url], "转发")
        if success:
            stats["repost"] += 1
        else:
            failures.append({"type": "转发", "reason": message, "url": url, "detail": repost_content, "account_remark": remark})
            stats["failures"] += 1
        time.sleep(action_delay)
    if config.get("enableDeduplication"):
        save_to_history_file(config['file_paths']['history_urls'], url)
    return stats, failures

def process_video(config: Dict[str, Any], url:str, bvid: str, bili_clients: List['BilibiliClient']) -> Tuple[Dict[str, int], List[FailureItem]]:
    """处理视频"""
    stats = {"like": 0, "repost": 0, "follow": 0, "comment": 0, "crawl": 0, "failures": 0}
    failures = []

    # 获取视频详情
    success, details = bili_clients[0].fetch_video_detail(bvid)
    if not success:
        logger.error(f"获取视频详情失败: {bvid}, 跳过处理")
        failures.append({"type": "抓取视频", "reason": "无法获取视频详情", "url": url, "detail": bvid, "account_remark": "N/A"})
        stats["failures"] += 1
        return stats, failures

    stats["crawl"] += 1
    content = details.get("video_content", "")
    logger.debug(f"视频内容已获取: {bvid}")
    aid = details["video_aid"]
    mid = details["mid"]

    # 对每个账号执行操作
    for account_index, client in enumerate(bili_clients, 1):
        action_delay = random.uniform(config['action_delay_min_seconds'], config['action_delay_max_seconds'])
        acc_config = client.account_config
        remark = client.remark

        if not acc_config.get('enabled'):
            logger.info(f"[账号 {account_index}/{len(bili_clients)}] {remark} 已被禁用，跳过本次视频处理")
            continue

        if mid in [100680137, 280604312]:
            logger.warning("视频为“你的抽奖工具人”，跳过")
            continue
        logger.info(f"账号 {account_index}/{len(bili_clients)}] {remark} 正在对 {bvid} 执行操作...")

        # 关注
        code, msg = check_follow_status(client, mid)
        if code in [2, 6, 128]:
            logger.info(f"{msg}")
            stats["follow"] += 1
            if code == 128:
                continue
        elif code == 0:
            success, message = _execute_action(client.follow_user, [mid], "关注")
            if success:
                stats["follow"] += 1
            else:
                failures.append({"type": "关注", "reason": message, "url": url, "detail": "", "account_remark": remark})
                stats["failures"] += 1
        time.sleep(action_delay)

        # 点赞
        if acc_config.get("video_like_enabled"):
            success, message = _execute_action(client.like_video, [details["video_aid"]], "点赞视频")
            if success:
                stats["like"] += 1
            else:
                failures.append({"type": "点赞视频", "reason": message, "url": url, "detail": "", "account_remark": remark})
                stats["failures"] += 1
            time.sleep(action_delay)

        # 评论
        comment_content = _get_comment_content(client, config, content, aid, 1)
        if comment_content:
            success, message, _ = client.comment_video(details["video_aid"], comment_content)
            if success:
                stats["comment"] += 1
                logger.info(f"评论视频 操作成功: {message}")
            else:
                logger.error(f"评论视频 操作失败 | 原因: {message}")
                failures.append({"type": "评论视频", "reason": message, "url": url, "detail": comment_content,
                                 "account_remark": remark})
                stats["failures"] += 1
        else:
            logger.error("无可用的评论内容")
        time.sleep(action_delay)

        # 转发
        if config.get("use_comment_content"):
            repost_content = comment_content
        elif acc_config.get("use_fixed_repost") and acc_config.get("fixed_reposts"):
            repost_content = random.choice(acc_config["fixed_reposts"])
        else:
            repost_content = "转发视频"
        success, message = _execute_action(client.repost_video, [details["video_aid"], repost_content], "转发视频")
        if success:
            stats["repost"] += 1
        else:
            failures.append({"type": "转发视频", "reason": message, "url": url, "detail": repost_content, "account_remark": remark})
            stats["failures"] += 1
        time.sleep(action_delay)
    if config.get("enableDeduplication"):
        save_to_history_file(config['file_paths']['history_urls'], url)
    return stats, failures

def main():
    start_time = time.time()
    config = load_config()
    custom_setup_logger(
        log_level=config.get('log_level', 'INFO'),
        log_file=config['file_paths']['main_log'],
        error_file=config['file_paths']['error_log']
    )

    logger.info('-' * 10 + ' 哔哩哔哩互动抽奖 ' + '-' * 10)

    # 初始化客户端
    bili_clients = []
    for acc_config in config["accounts"]:
        client = BilibiliClient(acc_config["cookie"], acc_config["remark"])
        if client.is_valid:
            client.account_config = acc_config
            bili_clients.append(client)

    if not bili_clients:
        logger.error("未找到有效的 Bilibili 账号，程序终止")
        return

    # 加载并过滤 URLs
    dyn_urls, video_urls = load_origin_urls_from_file(config['file_paths']['origin_urls'])
    history_ids = read_history_from_file(config['file_paths']['history_urls'])

    # 过滤动态
    dyn_urls_to_process = []
    for dyn_url in dyn_urls:
        dynamic_ids = extract_dynamic_id(dyn_url)
        if not dynamic_ids:
            logger.error(f"无效或无法解析的动态URL，已跳过: {dyn_url}")
        elif dynamic_ids in history_ids:
            logger.debug(f"动态 {dynamic_ids} 已处理过，跳过")
        else:
            dyn_urls_to_process.append({"url": dyn_url, "dynamic_id": dynamic_ids})

    # 过滤视频
    video_urls_to_process = []
    for video_url in video_urls:
        bvid = extract_video_bvid(video_url)
        if not bvid:
            logger.error(f"无效或无法解析的视频URL，已跳过: {video_url}")
        elif bvid in history_ids:
            logger.debug(f"视频 {bvid} 已处理过，跳过。")
        else:
            video_urls_to_process.append({"url": video_url, "bvid": bvid})

    # 处理动态
    global_failures = []
    final_stats = {"like": 0, "repost": 0, "follow": 0, "comment": 0, "crawl": 0, "failures": 0}
    client_dynamic_counters = {client.remark: 0 for client in bili_clients}
    comment_fail_counts = {client.remark: 0 for client in bili_clients}
    if dyn_urls_to_process:
        logger.info(f"已跳过 {len(dyn_urls) - len(dyn_urls_to_process)} 条已处理动态，开始处理 {len(dyn_urls_to_process)} 条新动态...")
        for i, item in enumerate(dyn_urls_to_process, 1):
            url, dynamic_ids = item["url"], item["dynamic_id"]
            logger.info(f"[动态 {i}/{len(dyn_urls_to_process)}] 正在处理: {url}")
            stats, failures = process_dynamic(config, url, dynamic_ids, bili_clients, comment_fail_counts)
            global_failures.extend(failures)
            for key in final_stats:
                final_stats[key] += stats.get(key, 0)
            # 转发视频
            for client in bili_clients:
                if not client.account_config.get('enabled'):
                    continue
                client_dynamic_counters[client.remark] += 1
                if config.get("repost_video_enabled") and client_dynamic_counters[client.remark] % 3 == 0:
                    handle_video_reposting(client, config, global_failures)
                    client_dynamic_counters[client.remark] = 0
    else:
        logger.info("没有新的动态需要处理")

    # 处理视频
    if config.get("enable_video_lottry"):
        if video_urls_to_process:
            logger.info(f"已跳过 {len(video_urls) - len(video_urls_to_process)} 条已处理视频，开始处理 {len(video_urls_to_process)} 条新视频...")
            for i, item in enumerate(video_urls_to_process, 1):
                url, bvid = item["url"], item["bvid"]
                logger.info(f"[视频 {i}/{len(video_urls_to_process)}] 正在处理: {url}")
                failures = process_video(config, url, bvid, bili_clients)
                global_failures.extend(failures)
                final_stats["failures"] += len(failures)
        else:
            logger.info("没有新的视频需要处理")

    logger.info("------ 所有任务处理完成 ------")
    for failure in global_failures:
        logger.warning(
            f"账号: {failure['account_remark']}\n"
            f"类型: {failure['type']}\n"
            f"错误: {failure['reason']}\n"
            f"链接: {failure['url']}\n"
            f"详情: {failure['detail']}\n"
            + '=' * 10
        )
    send_telegram_notification(config, final_stats, start_time, global_failures)

if __name__ == "__main__":
    from services.check import check_lottery

    choice = input("请选择操作:\n0: 运行抽奖程序\n1: 检查是否中奖\n请输入数字: ")
    if choice == "0":
        main()
    elif choice == "1":
        check_lottery()
    else:
        print("输入无效，请输入 0 或 1")