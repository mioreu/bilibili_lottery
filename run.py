import json
import logging
import os
import random
import sys
import time
from typing import List, Dict, Any, Tuple, Optional

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from api.bilibili_client import BilibiliClient
from utils.file_operations import load_origin_urls_from_file, read_history_from_file, save_to_history_file, save_parsed_content
from utils.data_extractors import extract_dynamic_id, get_dynamic_type_for_comment, get_author_mid, check_follow_status
from services.deepseek_ai import generate_comment
from services.telegram_notifier import send_telegram_notification, send_telegram_files, FailureItem
from utils.logger_setup import setup_logger as custom_setup_logger

logger = logging.getLogger("Bilibili.Main")


# 配置加载
def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """加载并验证配置文件"""
    config_full_path = os.path.join(project_root, config_path)
    if not os.path.exists(config_full_path):
        raise FileNotFoundError(f"配置文件 {config_full_path} 不存在。请确保文件在项目根目录下。")

    try:
        with open(config_full_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件 {config_full_path} 格式错误，不是有效的 JSON: {e}")

    # 验证配置
    return validate_config(config)

def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """验证配置文件"""
    logger.info("开始验证配置文件...")
    accounts = config.get("accounts", [])
    if not isinstance(accounts, list) or not accounts:
        logger.warning("配置中没有找到有效的 'accounts' 列表。")
        config["accounts"] = []
    
    validated_accounts = []
    for i, account in enumerate(accounts):
        if not isinstance(account, dict):
            logger.warning(f"accounts[{i}] 不是字典类型，已跳过。")
            continue
        
        remark = account.get("remark", f"账号_{i+1}")
        if not isinstance(remark, str) or not remark:
            logger.warning(f"accounts[{i}] 的 'remark' 无效，使用默认值 '{remark}'。")
            account["remark"] = remark
        
        # 验证 'enabled' 字段
        if not isinstance(account.get("enabled"), bool):
            logger.warning(f"账号 [{remark}] 的 'enabled' 设置无效，使用默认值 False")
            account["enabled"] = False
        
        for key in ["like_enabled", "comment_enabled", "repost_enabled", "follow_enabled", "use_fixed_comment", "use_fixed_repost"]:
            if not isinstance(account.get(key), bool):
                logger.warning(f"账号 [{remark}] 的 '{key}' 设置无效，使用默认值 False。")
                account[key] = False
        
        for key in ["fixed_comments", "fixed_reposts", "emoticons"]:
            if not isinstance(account.get(key), list):
                logger.warning(f"账号 [{remark}] 的 '{key}' 不是列表，使用空列表。")
                account[key] = []
            else:
                account[key] = [str(item) for item in account[key] if isinstance(item, (str, int, float))]
                if not account[key]:
                    logger.debug(f"账号 [{remark}] 的 '{key}' 为空或不包含有效字符串。")
        
        validated_accounts.append(account)
        
    config["accounts"] = validated_accounts

    # DeepSeek 配置验证
    deepseek_config = config.get("deepseek", {})
    if not isinstance(deepseek_config, dict):
        logger.warning("deepseek 配置无效，使用默认空配置")
        deepseek_config = {}
    config["deepseek"] = deepseek_config

    if not isinstance(deepseek_config.get("temperature"), (int, float)):
        logger.warning("DeepSeek 'temperature' 设置无效，使用默认值 0.7。")
        deepseek_config["temperature"] = 0.7

    # 文件路径验证
    file_paths = config.get("file_paths", {})
    if not isinstance(file_paths, dict):
        file_paths = {}
    config["file_paths"] = file_paths

    default_file_paths = {
        "origin_urls": "origin.txt",
        "history_urls": "cache/history_url_list.txt",
        "parsed_dynamics": "output/parsed_dynamics.txt",
        "main_log": "bili.log",
        "error_log": "output/error.log"
    }
    for key, default_path in default_file_paths.items():
        if not isinstance(file_paths.get(key), str) or not file_paths.get(key):
            file_paths[key] = os.path.join(project_root, default_path)
        else:
            file_paths[key] = os.path.join(project_root, file_paths[key])
        os.makedirs(os.path.dirname(file_paths[key]), exist_ok=True)

    logger.info("配置文件验证完成。")
    return config


# 主流程
def phase_1_fetch_dynamics(config: Dict[str, Any]) -> None | tuple[list[Any], dict[str, int], list[FailureItem]] | \
                                                      tuple[list[dict[str, str]], dict[str, int | Any], list[
                                                          FailureItem]]:
    """阶段1: 获取动态内容"""
    logger.info('-' * 10 + '开始爬取动态内容' + '-' * 10)
    start_time = time.time()
    parsed_dynamics_data: List[Dict[str, str]] = []
    failures: List[FailureItem] = []

    origin_urls_with_comments = load_origin_urls_from_file(config['file_paths']['origin_urls'])
    history_ids = read_history_from_file(config['file_paths']['history_urls'])
    
    new_urls_to_process = []
    for url, comment in origin_urls_with_comments:
        dynamic_id = extract_dynamic_id(url)
        if not dynamic_id:
            logger.error(f"无效或无法解析的 URL，已跳过: {url}")
            failures.append({"type": "解析", "reason": "URL无效或无法解析动态ID", "url": url, "detail": "无法从URL中提取有效动态ID", "account_remark": "N/A"})
            continue
        if dynamic_id in history_ids:
            logger.debug(f"动态 {dynamic_id} 已在历史记录中，跳过: {url}")
            continue
        new_urls_to_process.append({"url": url, "dynamic_id": dynamic_id, "fixed_comment": comment})
    
    total_new_urls = len(new_urls_to_process)
    if not total_new_urls:
        logger.info("没有新的动态需要爬取")
        stats = {"parse_success": 0, "parse_failures": len(failures), "total_failures": len(failures)}
        return [], stats, failures
        
    logger.info(f"开始爬取 {total_new_urls} 个新动态...")
    
    temp_client = None
    if config.get('accounts'):
        client = BilibiliClient(cookie=config['accounts'][0]['cookie'], remark="解析", proxy_config=config['proxy'])
        if client.is_valid:
            temp_client = client
        else:
            logger.warning("BilibiliClient初始化失败")

    success_count = 0
    for index, item in enumerate(new_urls_to_process, 1):
        url, dynamic_id, fixed_comment = item["url"], item["dynamic_id"], item["fixed_comment"]
        logger.info(f" [进度 {index}/{total_new_urls}]  正在爬取动态: {dynamic_id}")

        try:
            if not temp_client:
                raise RuntimeError("BilibiliClient 不可用")

            dynamic_content = temp_client.fetch_dynamic_content_from_api(
                dynamic_id=dynamic_id,
                retry_times=config['parser']['parser_retry_times'],
                timeout=config['parser']['parser_timeout'],
                headers=config['parser']['parser_headers']
            )

            if dynamic_content:
                logger.info("成功爬取动态内容")
                parsed_dynamics_data.append({
                    "dynamic_id": dynamic_id,
                    "content": dynamic_content,
                    "original_url": url,
                    "fixed_comment": fixed_comment
                })
                save_parsed_content(config['file_paths']['parsed_dynamics'], dynamic_id, dynamic_content, url)
                save_to_history_file(config['file_paths']['history_urls'], url)
                success_count += 1
            else:
                raise ValueError("客户端未能获取到动态内容 (详情请见API日志)")

        except (ValueError, RuntimeError, Exception) as e:
            # 此处的失败记录是主流程层面的，具体API失败原因由客户端日志体现
            logger.error(f"处理动态 {dynamic_id} 失败: {e}", exc_info=(not isinstance(e, (ValueError, RuntimeError))))
            failures.append({
                "type": "爬取",
                "reason": "动态内容爬取失败",
                "url": url,
                "detail": str(e),
                "account_remark": "N/A"
            })
        
        finally:
            time.sleep(random.uniform(config['parse_delay_min_seconds'], config['parse_delay_max_seconds']))

    duration = time.time() - start_time
    parse_failures = total_new_urls - success_count
    stats = {
        "parse_success": success_count,
        "parse_failures": parse_failures,
        "total_failures": len(failures)
    }
    logger.info(f"阶段1 爬取完成\n├─ 成功: {success_count}\n├─ 失败: {parse_failures}\n└─ 用时: {duration:.2f} 秒")
    
    return parsed_dynamics_data, stats, failures

def phase_2_bili_actions(config: Dict[str, Any], parsed_dynamics: List[Dict[str, str]]) -> Tuple[Dict[str, int], List[FailureItem]]:
    """阶段2: 执行点赞，评论，转发，关注"""
    logger.info("------ 开始执行 Bilibili 操作 ------")
    start_time = time.time()

    action_stats = {
        "like_success": 0,
        "repost_success": 0,
        "follow_success": 0,
        "comment_success": 0,
        "total_failures": 0
    }
    failures: List[FailureItem] = []

    if not config["accounts"]:
        logger.warning("配置中没有可用的 Bilibili 账号，跳过阶段2。")
        return action_stats, failures

    bili_clients: List[BilibiliClient] = []
    for acc_config in config["accounts"]:
        if acc_config.get("enabled", True): # 检查账号是否启用
            client = BilibiliClient(acc_config["cookie"], acc_config["remark"], config["proxy"])
            client.account_config = acc_config 
            if client.is_valid:
                bili_clients.append(client)
            else:
                logger.error(f"账号 [{acc_config['remark']}] 初始化失败或Cookie无效，将跳过此账号的所有操作。")
                failures.append({
                    "type": "账号初始化",
                    "reason": "Cookie无效或登录失败",
                    "url": "N/A",
                    "detail": f"账号 [{acc_config['remark']}] 的Cookie可能已过期或不正确。",
                    "account_remark": acc_config['remark']
                })
                action_stats["total_failures"] += 1
        else:
            logger.info(f"账号 [{acc_config.get('remark', '未知账号')}] 已禁用，跳过初始化。")


    total_dynamics = len(parsed_dynamics)
    total_accounts = len(bili_clients)
    if total_dynamics > 0 and total_accounts > 0:
        logger.info(f"开始处理 {total_dynamics} 个动态，使用 {total_accounts} 个账号...")
    elif total_dynamics == 0:
        logger.warning("没有需要处理的动态数据")
        return action_stats, failures

    # 为每个动态和每个账号执行操作
    for dynamic_index, dynamic_data in enumerate(parsed_dynamics, 1):
        dynamic_id = dynamic_data["dynamic_id"]
        dynamic_content = dynamic_data["content"]
        original_url = dynamic_data["original_url"]
        fixed_comment_from_origin = dynamic_data.get("fixed_comment")

        logger.info(f"[动态进度 {dynamic_index}/{total_dynamics}] 正在处理动态 {original_url}")

        # 获取作者UID
        author_mid: Optional[int] = None
        # 使用单账号获取
        if bili_clients:
            author_mid = get_author_mid(bili_clients[0], dynamic_id)
            if not author_mid:
                logger.warning(f"无法获取动态 {dynamic_id} 的作者UID，跳过关注操作。")

        for account_index, client in enumerate(bili_clients, 1):
            remark = client.remark
            acc_config = client.account_config # 获取此账号的配置
            
            logger.info(f"[动态 {dynamic_index}/{total_dynamics}] [账号 {account_index}/{total_accounts}] {remark} 正在执行操作...")

            # 点赞
            if acc_config.get("like_enabled"):
                if client.like_dynamic(dynamic_id):
                    action_stats["like_success"] += 1
                    logger.info(f"[动态 {dynamic_index}/{total_dynamics}] [账号 {account_index}/{total_accounts}] 点赞成功")
                else:
                    failures.append({
                        "type": "点赞",
                        "reason": "点赞失败",
                        "url": original_url,
                        "detail": f"账号 [{remark}] 点赞动态 {dynamic_id} 失败。",
                        "account_remark": remark
                    })
                    action_stats["total_failures"] += 1
                time.sleep(random.uniform(config['action_delay_min_seconds'], config['action_delay_max_seconds']))
            
            # 关注
            # 先检查关注状态
            status = check_follow_status(client, author_mid)
            
            if status == "is_follow":
                # 已关注状态
                action_stats["follow_success"] += 1
                logger.info(f"[动态 {dynamic_index}/{total_dynamics}] [账号 {account_index}/{total_accounts}] 已关注 UID {author_mid}，无需操作")
            elif status == "black_user":
                # 已拉黑状态
                action_stats["follow_success"] += 1
                logger.info(f"[动态 {dynamic_index}/{total_dynamics}] [账号 {account_index}/{total_accounts}] 已拉黑 UID {author_mid}，跳过关注")
            elif status == "unfollow":
                # 未关注状态，执行关注操作
                if client.follow_user(author_mid):
                    action_stats["follow_success"] += 1
                    logger.info(f"[动态 {dynamic_index}/{total_dynamics}] [账号 {account_index}/{total_accounts}] 关注成功")
                else:
                    action_stats["total_failures"] += 1
                    logger.error(f"[动态 {dynamic_index}/{total_dynamics}] [账号 {account_index}/{total_accounts}] 关注失败")
            else:  # 错误状态
                action_stats["total_failures"] += 1
                logger.error(f"[动态 {dynamic_index}/{total_dynamics}] [账号 {account_index}/{total_accounts}] 检查关注状态出错")
            
            # 检查是否缺少作者UID
            if acc_config.get("follow_enabled") and not author_mid:
                logger.warning(f"账号 [{remark}] 启用了关注但未能获取到作者UID，跳过关注。")
                action_stats["total_failures"] += 1
            
            time.sleep(random.uniform(config['action_delay_min_seconds'], config['action_delay_max_seconds']))


            # 评论
            comment_content = ""
            if acc_config.get("comment_enabled"):
                deepseek_config = config["deepseek"]
                
                # 尝试 DeepSeek 生成评论
                if deepseek_config.get("deepseek_api_key") and deepseek_config.get("deepseek_model"):
                    logger.info(f"账号 [{remark}] 正在为动态 {dynamic_id} 生成评论...")
                    
                    try:
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
                    except Exception as e:
                        logger.error(f"账号 [{remark}] 调用 DeepSeek API 生成评论时出错: {e}", exc_info=True)
                        failures.append({
                            "type": "评论",
                            "reason": "评论生成失败",
                            "url": original_url,
                            "detail": str(e),
                            "account_remark": remark
                        })
                        action_stats["total_failures"] += 1
                        
                # 使用origin.txt中的fixed_comment
                elif fixed_comment_from_origin:
                    comment_content = fixed_comment_from_origin
                    logger.info(f"账号 [{remark}] 优先使用 origin.txt 中的固定评论: {comment_content}")
                    
                # 尝试使用账号配置中的固定评论
                if not comment_content and acc_config.get("use_fixed_comment") and acc_config.get("fixed_comments"):
                    comment_content = random.choice(acc_config["fixed_comments"])
                    logger.info(f"账号 [{remark}] Deepseek 生成评论失败，使用账号配置中的固定评论: {comment_content}")
                
                # 为评论添加随机表情
                if comment_content and acc_config.get("emoticons"):
                    emoticon = random.choice(acc_config["emoticons"])
                    comment_content = f"{comment_content}{emoticon}"
            
                if comment_content:
                    comment_type = get_dynamic_type_for_comment(client, dynamic_id, original_url)
                    if comment_type is not None:
                        if client.comment_dynamic(dynamic_id, comment_content, comment_type):
                            action_stats["comment_success"] += 1
                            logger.info(f"[动态 {dynamic_index}/{total_dynamics}] [账号 {account_index}/{total_accounts}] 评论成功")
                        else:
                            failures.append({
                                "type": "评论",
                                "reason": "评论失败",
                                "url": original_url,
                                "detail": f"账号 [{remark}] 评论动态 {dynamic_id} 失败。",
                                "account_remark": remark
                            })
                            action_stats["total_failures"] += 1
                    else:
                        logger.warning(f"账号 [{remark}] 无法确定动态 {dynamic_id} 的评论类型，跳过评论。")
                        failures.append({
                            "type": "评论",
                            "reason": "无法确定评论类型",
                            "url": original_url,
                            "detail": f"账号 [{remark}] 评论动态 {dynamic_id} 失败。",
                            "account_remark": remark
                        })
                        action_stats["total_failures"] += 1
                else:
                    logger.warning(f"账号 [{remark}] 未能为动态 {dynamic_id} 找到可用的评论内容，跳过评论。")
            
                time.sleep(random.uniform(config['action_delay_min_seconds'], config['action_delay_max_seconds']))
            
            # 转发
            if acc_config.get("repost_enabled"):
                repost_content = ""
                
                # 优先使用评论内容作为转发内容
                if comment_content:
                    repost_content = comment_content
                # 如果评论内容为空，则使用固定转发语
                elif acc_config.get("use_fixed_repost") and acc_config.get("fixed_reposts"):
                    repost_content = random.choice(acc_config["fixed_reposts"])
                    logger.info(f"账号 [{remark}] 使用固定转发语: {repost_content}")
                else:
                    repost_content = "转发动态！" # 默认转发语
            
                if repost_content:
                    if client.repost_dynamic(dynamic_id, repost_content, original_url):
                        action_stats["repost_success"] += 1
                        logger.info(f"[动态 {dynamic_index}/{total_dynamics}] [账号 {account_index}/{total_accounts}] 转发成功")
                    else:
                        failures.append({
                            "type": "转发",
                            "reason": "转发失败",
                            "url": original_url,
                            "detail": f"账号 [{remark}] 转发动态 {dynamic_id} 失败。",
                            "account_remark": remark
                        })
                        action_stats["total_failures"] += 1
                time.sleep(random.uniform(config['action_delay_min_seconds'], config['action_delay_max_seconds']))                
    end_time = time.time()
    duration = end_time - start_time
    logger.info(
                f"阶段2 操作完成\n"
                f"└─ 用时: {duration:.2f} 秒"
    )
    return action_stats, failures

# 主函数
def main():
    start_time = time.time()
    global_failures: List[FailureItem] = []
    config = load_config()

    # 2. 设置日志
    log_file_abs = config['file_paths']['main_log']
    error_log_abs = config['file_paths']['error_log']
    custom_setup_logger(
        log_level=config['log_level'],
        log_file=log_file_abs,
        error_file=error_log_abs
    )
    logger.info('-' * 10 +  '哔哩哔哩动态抽奖' + '-' * 10)

    # 3. 爬取动态
    parsed_dynamics, phase1_stats, phase1_failures = phase_1_fetch_dynamics(config)
    global_failures.extend(phase1_failures)

    if not parsed_dynamics:
        logger.warning("没有新的动态需要处理，程序将退出。")
        end_time = time.time()
        final_duration = end_time - start_time
        final_stats = {
            "like_success": 0, "repost_success": 0, "follow_success": 0, "comment_success": 0,
            "total_failures": len(global_failures)
        }
        send_telegram_notification(config, final_stats, start_time, global_failures, message_type="summary")
        send_telegram_files(config)
        return

    # 4. 执行操作
    action_stats, phase2_failures = phase_2_bili_actions(config, parsed_dynamics)
    global_failures.extend(phase2_failures)

    # 汇总最终统计
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
                f"------ 所有阶段完成 ------ \n"
                f"总耗时: {final_duration:.2f} 秒 \n"
                f"最终统计:\n "
                f"成功点赞: {final_stats['like_success']} \n"
                f"转发: {final_stats['repost_success']} \n"
                f"关注: {final_stats['follow_success']} \n"
                f"评论: {final_stats['comment_success']} \n"
                f"失败总数: {final_stats['total_failures']}"
    )

    # 5. 发送最终报告和文件
    send_telegram_notification(config, final_stats, start_time, global_failures, message_type="summary")
    send_telegram_files(config)

if __name__ == "__main__":
    main()
