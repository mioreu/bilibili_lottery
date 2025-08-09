import logging
import time
import requests
import urllib.parse
from functools import reduce
from hashlib import md5

api_logger = logging.getLogger("Bilibili.Api")

# WBI签名用到的密钥重排映射表
mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]


def getMixinKey(orig: str):
    """对 imgKey 和 subKey 进行字符顺序打乱编码"""
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, '')[:32]


def encWbi(params: dict, img_key: str, sub_key: str):
    """为请求参数进行 wbi 签名"""
    mixin_key = getMixinKey(img_key + sub_key)
    curr_time = round(time.time())
    params['wts'] = curr_time
    params = dict(sorted(params.items()))

    # 过滤 value 中的 "!'()*" 字符
    params = {
        k: ''.join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v in params.items()
    }

    query = urllib.parse.urlencode(params)
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()
    params['w_rid'] = wbi_sign
    return params


def getWbiKeys(session: requests.Session) -> tuple[str, str]:
    """获取最新的 img_key 和 sub_key"""
    try:
        # 使用传入的session对象发送请求
        resp = session.get('https://api.bilibili.com/x/web-interface/nav')
        resp.raise_for_status()
        json_content = resp.json()

        # 检查是否成功获取wbi_img数据
        if json_content.get("code") == 0 and json_content["data"].get("wbi_img"):
            img_url: str = json_content['data']['wbi_img']['img_url']
            sub_url: str = json_content['data']['wbi_img']['sub_url']
            img_key = img_url.rsplit('/', 1)[1].split('.')[0]
            sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
            api_logger.debug("WBI Keys retrieved successfully.")
            return img_key, sub_key
        else:
            # 记录详细的错误信息
            api_logger.error(f"Failed to get WBI keys from /nav API: {json_content.get('message', 'Unknown error')}")
            return "", ""
    except Exception as e:
        api_logger.exception(f"An error occurred while fetching WBI keys: {e}")
        return "", ""