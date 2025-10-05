import json
import logging
import os
import random
import sys
import time
from typing import List, Dict, Any, Tuple, Callable, Optional
import urllib3
from api.bilibili_client import BilibiliClient, DynamicContent
from services.deepseek_ai import generate_comment
from services.repost_video import handle_video_reposting
from services.telegram_notifier import send_task_report_notification, FailureItem
from utils.data_extractors import extract_dynamic_id, check_follow_status, extract_topic_and_fixed_at, check_at, \
    extract_video_bvid
from utils.load_url import load_origin_urls_from_file
from utils import database_operations
from utils.logger_setup import setup_logger as custom_setup_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger("Bilibili.Main")


def load_config(config_path: str = "config.json", accounts_path: str = "accounts.json") -> Dict[str, Any]:
    """加载配置"""
    # 加载主配置
    config_full_path = os.path.join(PROJECT_ROOT, config_path)
    if not os.path.exists(config_full_path):
        raise FileNotFoundError(f"未找到主配置文件 {config_full_path}")

    try:
        with open(config_full_path, 'r', encoding='utf-8') as j:
            config = json.load(j)
    except json.JSONDecodeError as e:
        raise ValueError(f"主配置文件格式错误: {e}") from e

    # 加载账号
    accounts = []
    accounts_full_path = os.path.join(PROJECT_ROOT, accounts_path)
    if not os.path.exists(accounts_full_path):
        logger.warning(f"未找到账号配置文件 {accounts_full_path} ")
    else:
        try:
            with open(accounts_full_path, 'r', encoding='utf-8') as j:
                accounts = json.load(j)
        except json.JSONDecodeError as e:
            raise ValueError(f"账号配置文件格式错误: {e}") from e

    config["accounts"] = accounts
    # 过滤禁用账号
    config["accounts"] = [acc for acc in config.get("accounts", []) if acc.get("enabled", True)]
    return config


def get_comment_content(client: BilibiliClient, config: Dict[str, Any], dynamic_text: str, oid: int,
                        comment_type: int) -> str:
    """生成或选择评论内容"""
    acc_config = client.account_config
    deepseek_config = config.get("deepseek", {})
    comment_content = ""

    # 优先使用AI生成评论
    if acc_config.get("ai_comment"):
        reference_comment = client.get_some_comment(oid, comment_type)
        prompt = f"请根据以下动态内容生成一条评论:\n\n{dynamic_text}\n可以参考以下评论生成:{reference_comment}"
        generated_comment, _ = generate_comment(
            config,
            name=client.remark,
            prompt=prompt,
            api_key=deepseek_config.get("deepseek_api_key"),
            model=deepseek_config.get("deepseek_model"),
            temperature=deepseek_config.get("temperature")
        )
        if generated_comment:
            comment_content = generated_comment
        else:
            logger.warning("评论生成失败，将尝试使用固定评论")

    # 如果AI生成失败或未启用，则回退到固定评论
    fixed_comments = acc_config.get("fixed_comments")
    if not comment_content and acc_config.get("use_fixed_comment") and fixed_comments:
        comment_content = random.choice(fixed_comments)

    if not comment_content:
        return ""

    # 添加话题、艾特和表情
    text_for_extract = f"{dynamic_text}\n{comment_content}"
    topic = extract_topic_and_fixed_at(text_for_extract)
    at_num = check_at(config, text_for_extract)
    at_list = config.get("at_list", [])
    selected_ats = " ".join(random.sample(at_list, min(at_num, 4))) if at_num > 0 else ""
    emoticons = acc_config.get("emoticons", [])
    emoticon = random.choice(emoticons) if emoticons else ""

    # 构建评论
    return f"{topic} {selected_ats} {comment_content}{emoticon}"

def _get_item_content(client: BilibiliClient, item_type: str, item_id: str) -> Tuple[
    bool, str, Optional[Dict[str, Any]]]:
    """获取动态或视频内容"""
    if item_type == "dynamic":
        success, message, content = client.fetch_dynamic_content(item_id)
        if not success:
            return False, message, None

        if content.is_video:
            bvid = content.video_info.get("bvid")
            video_success, _, video_details = client.fetch_video_detail(bvid)
            if not video_success:
                return False, "获取视频详情失败", None

            combined_text = f"动态内容: {content.text}\n视频内容: {video_details.get('text', '')}"
            video_details['text'] = combined_text
            return True, "成功获取视频和动态内容", video_details
        return success, message, content

    if item_type == "video":
        return client.fetch_video_detail(item_id)

    return False, "不支持的 item_type", None


def _get_repost_content(config: Dict, account_config: Dict, comment_content: str, item_type: str,
                        is_forward: bool) -> str:
    """获取转发文本"""
    if is_forward:
        if config.get("use_comment_content") and comment_content:
            return comment_content
        if account_config.get("use_fixed_repost") and account_config.get("fixed_reposts"):
            return random.choice(account_config["fixed_reposts"])
        return ""

    if config.get("use_comment_content") and comment_content:
        return comment_content
    if account_config.get("use_fixed_repost") and account_config.get("fixed_reposts"):
        return random.choice(account_config["fixed_reposts"])
    return "转发动态" if item_type == "dynamic" else "转发视频"


def _execute_action(action_name: str, action_func: Callable, *args) -> Tuple[bool, str]:
    """执行指定操作并记录日志"""
    try:
        success, message = action_func(*args)
        if not success:
            logger.error(f"{action_name} 操作失败 | 原因: {message}")
        else:
            logger.info(message)
        return success, message
    except Exception as e:
        logger.error(f"{action_name} 操作发生异常: {e}")
        return False, f"操作发生异常: {e}"


def handle_failure(failures: List[Dict], stats: Dict, failure_type: str, reason: str, urls: str, detail: str,
                   client: BilibiliClient):
    """统一处理失败情况并记录"""
    failures.append({
        "type": failure_type,
        "reason": reason,
        "url": urls,
        "detail": detail,
        "account_remark": client.remark
    })
    stats["failures"] += 1

def process_lottery(
        item_type: str,
        item_id: str,
        urls: str,
        client: BilibiliClient,
        config: Dict[str, Any],
        comment_fail_counts: Dict[str, int],
        active_clients: List[BilibiliClient]
) -> Tuple[Dict[str, int], List[FailureItem], bool]:
    """统一处理抽奖动态和视频"""
    try:
        stats = {"like": 0, "repost": 0, "follow": 0, "comment": 0, "crawl": 0, "failures": 0}
        failures: List[FailureItem] = []
        should_record_to_db = True

        if not client.account_config.get('enabled'):
            logger.info(f"账号 [{client.remark}] 已被禁用，跳过本次任务")
            return stats, failures, False
        if database_operations.check_id_exists(client.db_path, item_id):
            logger.info("已处理过此任务，跳过")
            return stats, failures, False
        if item_type != "dynamic" and not config.get("enable_video_lottery"):
            logger.info("视频抽奖功能已禁用，跳过")
            return stats, failures, False

        # 获取内容
        success, message, content = _get_item_content(client, item_type, item_id)
        if not success:
            handle_failure(failures, stats, f"抓取{item_type}", "无法获取内容", urls, message, client)
            return stats, failures, True

        content_data = {}
        if isinstance(content, DynamicContent):
            content_data = {
                "mid": content.mid,
                "author_name": content.author_name,
                "text": content.text,
                "oid": content.oid,
                "comment_oid": content.comment_oid,
                "comment_type": content.comment_type,
                "is_lottery": content.is_lottery,
                "is_forward": content.is_forward,
                "is_video": content.is_video,
                "video_info": content.video_info,
                "video_aid": content.video_info.get("aid") if content.is_video else None
            }
        elif isinstance(content, dict):
            content_data = content
        else:
            handle_failure(failures, stats, f"抓取{item_type}", "内容格式错误", urls, str(type(content)), client)
            return stats, failures, True

        stats["crawl"] += 1

        if content_data.get("mid") in config.get("skip_user", []):
            logger.warning(f"动态作者为'{content_data.get('author_name')}'，跳过")
            return stats, failures, False
        if item_type == "dynamic" and not config.get("enable_interactive_lottery") and content_data.get("is_lottery"):
            logger.info("动态是互动抽奖，已跳过")
            return stats, failures, False

        action_delay = random.uniform(config['action_delay_min_seconds'], config['action_delay_max_seconds'])

        is_video_item = (item_type == "video" or content_data.get("is_video", False))

        # 关注
        code, msg = check_follow_status(client, content_data.get("mid"))
        logger.info(msg) if code in [2, 6, 128] else None
        if code == 128:
            return stats, failures, True
        if code == 0 and client.account_config["only_followed"]:
            logger.info(f"未关注 {content_data.get('author_name')} ,跳过")
            return stats, failures, True
        elif code == 0 and not _execute_action("关注", client.follow_user, content_data.get("mid"))[0]:
            handle_failure(failures, stats, "关注", "关注失败", urls, "", client)
        stats["follow"] += 1
        time.sleep(action_delay)

        # 点赞
        like_id = content_data.get("video_aid") if is_video_item else item_id
        like_func = client.like_video if is_video_item else client.like_dynamic

        if (is_video_item and client.account_config.get("video_like_enabled")) or not is_video_item:
            if not _execute_action("点赞", like_func, like_id)[0]:
                handle_failure(failures, stats, "点赞", "点赞失败", urls, "", client)
            stats["like"] += 1
        time.sleep(action_delay)

        # 评论
        comment_content = get_comment_content(client, config, content_data.get("text"), content_data.get("oid"),
                                              content_data.get("comment_type"))
        if comment_content:
            comment_func = client.comment_video if is_video_item else client.comment_dynamic
            if is_video_item:
                comment_args = [content_data.get("video_aid"), comment_content]
            else:
                comment_args = [item_id, comment_content, content_data.get("comment_type"), content_data.get("oid")]
                
            success, message, rpid, code = comment_func(*comment_args)

            if code == 12015:
                logger.error(f"账号 {client.remark} 评论时弹出验证码，已禁用")
                client.account_config["enabled"] = False
                if client in active_clients:
                    active_clients.remove(client)
                handle_failure(failures, stats, "评论", message, urls, comment_content, client)

            elif success:
                stats["comment"] += 1
                logger.info(message)
                logger.info("等待 6 秒后检查评论状态...")
                time.sleep(6)
                status_success, status_details = client.check_comment_status(content_data.get("oid"), int(rpid),
                                                                             content_data.get("comment_type"))
                logger.info(f"评论状态检查完成：{status_details.get('status', '未知')}")

                if not status_success or status_details.get("code") != 0:
                    should_record_to_db = False
                    comment_fail_counts[client.remark] = comment_fail_counts.get(client.remark, 0) + 1
                    handle_failure(failures, stats, "评论", status_details.get('status', '未知'), urls, comment_content,
                                   client)
                    if comment_fail_counts[client.remark] >= config.get("abnormal_comment_count", 5):
                        logger.error(f"账号 {client.remark} 评论仅自己可见次数过多，已禁用")
                        client.account_config["enabled"] = False
                        active_clients.remove(client)
            else:
                handle_failure(failures, stats, "评论", message, urls, comment_content, client)
        else:
            logger.error("无可用的评论内容")
        time.sleep(action_delay)

        # 转发
        is_forward = item_type == 'dynamic' and content_data.get('is_forward') and content_data.get('text')
        repost_content = _get_repost_content(config, client.account_config, comment_content, item_type, is_forward)

        if is_forward:
            repost_func = client.create_dyn
            repost_args = [item_id, content_data, repost_content]
        else:
            repost_func = client.repost_dynamic if item_type == "dynamic" else client.repost_video
            repost_id = item_id if item_type == "dynamic" else content_data.get("video_aid")
            repost_args = [repost_id, repost_content, urls] if item_type == "dynamic" else [repost_id, repost_content]

        if repost_func and not _execute_action("转发", repost_func, *repost_args)[0]:
            handle_failure(failures, stats, "转发", "转发失败", urls, repost_content, client)
        stats["repost"] += 1

        time.sleep(action_delay)
        return stats, failures, should_record_to_db

    except Exception as e:
        logger.error(f"处理任务时发生未知错误: {e}")
        return {"like": 0, "repost": 0, "follow": 0, "comment": 0, "crawl": 0, "failures": 1}, [{
            "type": "未知错误",
            "reason": str(e),
            "url": urls,
            "detail": "程序内部错误",
            "account_remark": client.remark
        }], False


def main():
    start_time = time.time()
    config = load_config()
    custom_setup_logger(
        log_level=config.get('log_level', 'INFO'),
        log_file=config['file_paths']['main_log'],
        error_file=config['file_paths']['error_log']
    )

    logger.info('-' * 10 + ' 哔哩哔哩互动抽奖 ' + '-' * 10)

    # 客户端初始化
    all_clients = [BilibiliClient(acc["cookie"], acc["remark"]) for acc in config["accounts"]]
    for client in all_clients:
        client.db_path = os.path.join(config['file_paths']['database_cache'], f"uid{client.mid}.db")
        database_operations.init_db(client.db_path)
        client.account_config = next((acc for acc in config["accounts"] if acc["remark"] == client.remark), {})

    active_clients = [c for c in all_clients if c.account_config.get("enabled", True) and c.is_valid]
    if not active_clients:
        logger.error("未找到有效的 Bilibili 账号，程序终止")
        return

    # 加载URL
    dynamic_urls, video_urls = load_origin_urls_from_file(config['file_paths']['origin_urls'])
    account_queues = {client: [] for client in active_clients}
    processed_ids_by_client = {}
    for client in active_clients:
        processed_ids_by_client[client] = database_operations.get_all_ids(client.db_path)

    all_tasks = []
    for url_list, item_type, id_extractor in [
        (dynamic_urls, "dynamic", extract_dynamic_id),
        (video_urls, "video", extract_video_bvid)
    ]:
        for url in url_list:
            item_id = id_extractor(url)
            if item_id:
                all_tasks.append({"type": item_type, "id": item_id, "url": url})

    for task in all_tasks:
        item_id = task["id"]
        for client in active_clients:
            if item_id not in processed_ids_by_client[client]:
                account_queues[client].append(task)

    # 打乱顺序
    for client in active_clients:
        random.shuffle(account_queues[client])

    total_unique_tasks = len(all_tasks)
    total_tasks = sum(len(tasks) for tasks in account_queues.values())

    logger.info(
        f"共有 {len(active_clients)} 个启用账号， {total_unique_tasks} 条抽奖，总计 {total_tasks} 条待处理任务")

    client_task_counts = {client.remark: len(tasks) for client, tasks in account_queues.items()}
    for remark, count in client_task_counts.items():
        logger.info(f"账号 [{remark}] 有 {count} 条待处理任务")

    global_failures = []
    final_stats = {"like": 0, "repost": 0, "follow": 0, "comment": 0, "crawl": 0, "failures": 0}
    comment_fail_counts: Dict[str, int] = {}
    client_processed_counts = {client.remark: 0 for client in active_clients}

    try:
        while active_clients:
            client = random.choice(active_clients)
            remark = client.remark

            if not account_queues[client]:
                logger.info(f"账号 [{remark}] 已完成所有任务")
                active_clients.remove(client)
                continue

            task = account_queues[client].pop(0)
            client_processed_counts[remark] += 1

            logger.info(
                f"[{remark}] [{client_processed_counts[remark]}/{client_task_counts[remark]}] 正在处理 {task['type']}: {task['url']}")

            stats, failures, should_record = process_lottery(task['type'], task['id'], task['url'], client, config,
                                                             comment_fail_counts, active_clients)
            # 转发热门视频
            if client.account_config.get("enabled", True) and config.get("enableDeduplication", True) and should_record:
                database_operations.add_id(client.db_path, task['id'], task['type'])
                if task['type'] == "dynamic" and stats.get("crawl", 0) > 0 and config.get(
                        "repost_popular_video_enabled"):
                    if client_processed_counts[remark] % config.get("repost_after_processing", 3) == 0:
                        handle_video_reposting(client, config, global_failures)

            global_failures.extend(failures)
            for key in final_stats:
                final_stats[key] += stats.get(key, 0)
            time.sleep(random.uniform(0.5, 1.0))

    except KeyboardInterrupt:
        logger.warning("\n程序被中止，正在处理失败任务并发送通知...")

    logger.info("------ 任务处理完成 ------")
    for failure in global_failures:
        logger.warning(
            f"账号: {failure['account_remark']}\n"
            f"类型: {failure['type']}\n"
            f"错误: {failure['reason']}\n"
            f"链接: {failure['url']}\n"
            f"详情: {failure['detail']}\n"
            + '=' * 10
        )
    send_task_report_notification(config, final_stats, start_time, global_failures)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        choice = sys.argv[1]
        print(f"检测到命令行参数 '{choice}'，正在执行对应操作...")
    else:
        choice = input("请选择操作:\n0: 运行抽奖程序\n1: 检查是否中奖\n2: 跟随用户获取抽奖动态\n请输入数字: ")

    if choice == "0":
        main()
    elif choice == "1":
        from services.check import check_lottery

        check_lottery()
    elif choice == "2":
        from services.follow_forward import follow_and_forward

        new_urls = follow_and_forward()
        config_i = load_config()
        origin_file_path = config_i['file_paths']['origin_urls']

        with open(origin_file_path, 'r', encoding='utf-8') as f:
            existing_urls = set(line.strip() for line in f if line.strip())

        urls_to_add = list(set(new_urls) - existing_urls)

        if not urls_to_add:
            print("无新链接")
        else:
            with open(origin_file_path, 'a', encoding='utf-8') as f:
                for url in urls_to_add:
                    f.write(url + '\n')
            print(f"成功添加 {len(urls_to_add)} 条新链接至 '{origin_file_path}'")
    else:
        print("输入无效，请输入 0, 1, 或 2")