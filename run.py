import json
import logging
import os
import random
import sys
import time
from typing import List, Dict, Any, Tuple
import urllib3
from api.bilibili_client import BilibiliClient
from services.deepseek_ai import generate_comment
from services.telegram_notifier import send_telegram_notification, FailureItem
from utils.data_extractors import extract_dynamic_id, get_dynamic_type_for_comment, get_author_mid, check_follow_status, \
    get_comment_oid_str
from utils.file_operations import load_origin_urls_from_file, read_history_from_file, save_to_history_file
from utils.logger_setup import setup_logger as custom_setup_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

logger = logging.getLogger("Bilibili.Main")

def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """加载配置文件"""
    config_full_path = os.path.join(project_root, config_path)
    if not os.path.exists(config_full_path):
        raise FileNotFoundError(f"配置文件 {config_full_path} 不存在。请确保文件在项目根目录下。")

    try:
        with open(config_full_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件格式错误，不是有效的 JSON: {e}") from None

    accounts = config.get("accounts", [])
    validated_accounts = []

    for num, account in enumerate(accounts):
        if not isinstance(account, dict):
            logger.warning(f"accounts[{num}] 不是字典类型，已跳过。")
            continue
        validated_accounts.append(account)
    config["accounts"] = validated_accounts
    return config


def fetch_dynamics(config: Dict[str, Any]) -> Tuple[List[Dict[str, str]], Dict[str, int], List[FailureItem]]:
    """爬取动态内容"""
    logger.info('-' * 10 + '开始爬取动态内容' + '-' * 10)
    parsed_dynamics_data: List[Dict[str, str]] = []
    failures: List[FailureItem] = []
    origin_urls = load_origin_urls_from_file(config['file_paths']['origin_urls'])
    history_ids = read_history_from_file(config['file_paths']['history_urls'])
    temp_client = BilibiliClient(cookie=config['accounts'][0]['cookie'], remark=config['accounts'][0]['remark'])
    new_urls_to_process = []
    success_count = 0
    skipped_count = 0

    for url in origin_urls:
        dynamic_id = extract_dynamic_id(url)
        if not dynamic_id:
            logger.error(f"无效或无法解析的 URL，已跳过: {url}")
            skipped_count += 1
            continue
        if dynamic_id in history_ids:
            logger.debug(f"动态 {dynamic_id} 已在历史记录中，跳过: {url}")
            skipped_count += 1
            continue
        new_urls_to_process.append({"url": url, "dynamic_id": dynamic_id})
    total_new_urls = len(new_urls_to_process)

    if not total_new_urls:
        logger.warning(f"已跳过 {skipped_count} 条已处理的动态, 没有新的动态需要爬取")
        stats = {"parse_success": 0, "parse_failures": len(failures), "total_failures": len(failures)}
        return [], stats, failures
    logger.info(f"已跳过 {skipped_count} 条已处理的动态\n开始爬取 {total_new_urls} 个新动态内容...\n请耐心等待...")

    for index, item in enumerate(new_urls_to_process, 1):
        url = item["url"]
        dynamic_id = item["dynamic_id"]
        if not temp_client:
            raise RuntimeError("BilibiliClient 不可用")

        success, text = temp_client.fetch_dynamic_content(dynamic_id)
        if success:
            logger.debug(f"[{index}/{total_new_urls}] 成功爬取动态内容: {dynamic_id}")
            parsed_dynamics_data.append({
                "dynamic_id": dynamic_id,
                "content": text,
                "original_url": url
            })
            save_to_history_file(config['file_paths']['history_urls'], url)
            success_count += 1
        else:
            failures.append({
                "type": "爬取",
                "reason": "动态内容爬取失败",
                "url": url,
                "detail": text,
                "account_remark": "解析"
            })
    time.sleep(random.uniform(config['parse_delay_min_seconds'], config['parse_delay_max_seconds']))

    parse_failures = total_new_urls - success_count
    stats = {
        "parse_success": success_count,
        "parse_failures": parse_failures,
        "total_failures": len(failures)
    }
    logger.info(f"阶段1 爬取完成\n├─ 成功: {success_count}\n├─ 失败: {parse_failures}")
    return parsed_dynamics_data, stats, failures

def dyn_actions(config: Dict[str, Any], parsed_dynamics: List[Dict[str, str]]) -> Tuple[
    Dict[str, int], List[FailureItem]]:
    """关注，点赞，评论，转发"""
    logger.info("------ 开始执行操作 ------")
    action_stats = {
        "like_success": 0,
        "repost_success": 0,
        "follow_success": 0,
        "comment_success": 0,
        "total_failures": 0
    }
    failures: List[FailureItem] = []
    bili_clients: List[BilibiliClient] = []
    total_dynamics = len(parsed_dynamics)

    # 添加账号
    for acc_config in config["accounts"]:
        if acc_config.get("enabled", True):
            client = BilibiliClient(acc_config["cookie"], acc_config["remark"])
            client.account_config = acc_config
            if client.is_valid:
                bili_clients.append(client)
        else:
            logger.info(f"账号 [{acc_config.get('remark', '未知账号')}] 已禁用，跳过初始化。")
    total_accounts = len(bili_clients)
    logger.info(f"开始处理 {total_dynamics} 个动态，使用 {total_accounts} 个账号...")

    # 执行操作
    for dynamic_index, dynamic_data in enumerate(parsed_dynamics, 1):
        dynamic_id = dynamic_data["dynamic_id"]
        dynamic_content = dynamic_data["content"]
        original_url = dynamic_data["original_url"]
        author_mid = get_author_mid(bili_clients[0], dynamic_id)
        logger.info(f"[动态 {dynamic_index}/{total_dynamics}] 正在处理动态 {original_url}")

        for account_index, client in enumerate(bili_clients, 1):
            remark = client.remark
            acc_config = client.account_config
            logger.info(f"[账号 {account_index}/{total_accounts}] {remark} 正在执行操作...")

            # 关注
            if acc_config.get("follow_enabled"):
                code, message = check_follow_status(client, author_mid) # 检查状态
                if code == 128:
                    action_stats["follow_success"] += 1
                    logger.info(f"{message}")
                    continue # 跳过该动态
                elif code in [2, 6]:
                    action_stats["follow_success"] += 1
                    logger.info(f"{message}")
                elif code == 0:
                    success, message = client.follow_user(author_mid)
                    if success:
                        action_stats["follow_success"] += 1
                        logger.info(f"{message}")
                    else:
                        failures.append({
                            "type": "关注",
                            "reason": f"关注UID {author_mid}失败",
                            "url": original_url,
                            "detail": f"{message}",
                            "account_remark": remark
                        })
                        action_stats["total_failures"] += 1

                time.sleep(random.uniform(config['action_delay_min_seconds'], config['action_delay_max_seconds']))

            # 点赞
            if acc_config.get("like_enabled"):
                success, message = client.like_dynamic(dynamic_id)
                if success:
                    action_stats["like_success"] += 1
                    logger.info(f"{message}")
                else:
                    failures.append({
                        "type": "点赞",
                        "reason": "点赞失败",
                        "url": original_url,
                        "detail": message,
                        "account_remark": remark
                    })
                    action_stats["total_failures"] += 1
                time.sleep(random.uniform(config['action_delay_min_seconds'], config['action_delay_max_seconds']))

            # 评论
            comment_content = ""
            if acc_config.get("comment_enabled"):
                deepseek_config = config["deepseek"]

                # 优先使用 Deepseek 生成评论
                if deepseek_config.get("deepseek_api_key") and acc_config.get("ai_comment"):
                    logger.debug(f"账号 [{remark}] 使用 Deepseek 为动态 {dynamic_id} 生成评论...")

                    generated_comment, _ = generate_comment(
                        prompt=dynamic_content,
                        api_key=deepseek_config["deepseek_api_key"],
                        base_url=deepseek_config["deepseek_base_url"],
                        model=deepseek_config["deepseek_model"],
                        temperature=deepseek_config["temperature"]
                    )
                    if generated_comment:
                        comment_content = generated_comment
                    else:
                        logger.warning(f"账号 [{remark}] 评论生成失败，尝试回退到固定评论。")
                        comment_content = random.choice(acc_config["fixed_comments"])
                else:
                    comment_content = random.choice(acc_config["fixed_comments"])
                    logger.debug(f"账号 [{remark}] 使用账号配置中的固定评论: {comment_content}")

                if comment_content:
                    emoticon = random.choice(acc_config["emoticons"])
                    comment_content = f"{comment_content}{emoticon}"
                    comment_type = get_dynamic_type_for_comment(client, dynamic_id, original_url)
                    oid = get_comment_oid_str(client, dynamic_id)

                    success, message = client.comment_dynamic(dynamic_id, comment_content, comment_type, oid)
                    if success:
                        action_stats["comment_success"] += 1
                        logger.info(f"{message}")
                    else:
                        failures.append({
                            "type": "评论",
                            "reason": "评论失败",
                            "url": original_url,
                            "detail": message,
                            "account_remark": remark
                        })
                        action_stats["total_failures"] += 1
                    action_stats["total_failures"] += 1

                time.sleep(random.uniform(config['action_delay_min_seconds'], config['action_delay_max_seconds']))

            # 转发
            if acc_config.get("repost_enabled"):
                repost_content = ""
                if comment_content:
                    repost_content = comment_content
                elif acc_config.get("use_fixed_repost") and acc_config.get("fixed_reposts"):
                    repost_content = random.choice(acc_config["fixed_reposts"])
                    logger.debug(f"账号 [{remark}] 使用固定转发语: {repost_content}")
                else:
                    repost_content = "转发动态"

                if repost_content:
                    success, message = client.repost_dynamic(dynamic_id, repost_content, original_url)
                    if success:
                        action_stats["repost_success"] += 1
                        logger.info(f"{message}")
                    else:
                        failures.append({
                            "type": "转发",
                            "reason": "转发失败",
                            "url": original_url,
                            "detail": message,
                            "account_remark": remark
                        })
                        action_stats["total_failures"] += 1
                time.sleep(random.uniform(config['action_delay_min_seconds'], config['action_delay_max_seconds']))

    return action_stats, failures

def main():
    start_time = time.time()
    global_failures: List[FailureItem] = []
    config = load_config()
    log_file_abs = config['file_paths']['main_log']
    error_log_abs = config['file_paths']['error_log']
    custom_setup_logger(
        log_level=config['log_level'],
        log_file=log_file_abs,
        error_file=error_log_abs
    )
    logger.info('-' * 10 + '哔哩哔哩动态抽奖' + '-' * 10)

    parsed_dynamics, phase1_stats, phase1_failures = fetch_dynamics(config)
    global_failures.extend(phase1_failures)

    if not parsed_dynamics:
        return

    action_stats, phase2_failures = dyn_actions(config, parsed_dynamics)
    global_failures.extend(phase2_failures)

    final_stats = {
        "like_success": action_stats["like_success"],
        "repost_success": action_stats["repost_success"],
        "follow_success": action_stats["follow_success"],
        "comment_success": action_stats["comment_success"],
        "total_failures": len(global_failures)
    }

    end_time = time.time()
    final_duration = end_time - start_time

    logger.info(
        f"------ 所有动态执行完成 ------ \n"
        f"总耗时: {final_duration:.2f} 秒 \n"
        f"最终统计:\n "
        f"成功点赞: {final_stats['like_success']} \n"
        f"转发: {final_stats['repost_success']} \n"
        f"关注: {final_stats['follow_success']} \n"
        f"评论: {final_stats['comment_success']} \n"
        f"失败总数: {final_stats['total_failures']}"
    )
    send_telegram_notification(config, final_stats, start_time, global_failures)

if __name__ == "__main__":
    from services.check import check_lottery
    i = int(input("0: 运行抽奖程序\n"
          "1: 检查是否中奖\n"
          "请输入数字: "
          ))
    if i == 0:
        main()

    elif i == 1:
        check_lottery()

    else:
        logger.warning("请输入上述数字")
