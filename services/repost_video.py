import logging
import random
import time
from typing import Dict, Any, List
from api.bilibili_client import BilibiliClient
from services.telegram_notifier import FailureItem

logger = logging.getLogger("Bilibili.VideoReposter")

def handle_video_reposting(
    client: BilibiliClient,
    config: Dict[str, Any],
    global_failures: List[FailureItem]
) -> None:
    """转发视频"""
    logger.info(f"[{client.remark}]已处理3条动态，开始转发热门视频...")
    success, video_list = client.fetch_popular_video()
    if success and video_list:
        num_videos_to_repost = min(config.get("max_repost_videos", 1), len(video_list))
        videos_to_repost = random.sample(video_list, num_videos_to_repost)

        for video in videos_to_repost:
            video_aid = video.get("aid")
            title = video.get("title")
            if video_aid:
                repost_success, repost_message = client.repost_video(video_aid, title)
                if repost_success:
                    logger.debug(f"{repost_message}")
                else:
                    logger.error(f"{repost_message}")
                    global_failures.append({
                        "type": "转发视频",
                        "reason": "转发视频失败",
                        "url": video.get("url", "N/A"),
                        "detail": repost_message,
                        "account_remark": client.remark
                    })
                time.sleep(
                    random.uniform(config['action_delay_min_seconds'], config['action_delay_max_seconds']))
    else:
        logger.warning(f"账号 [{client.remark}] 无法获取热门视频，跳过转发")