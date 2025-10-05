import logging
import time
import requests
import urllib.parse
from functools import reduce
from hashlib import md5

api_logger = logging.getLogger("Bilibili.WbiSign")

mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]


def get_mixin_key(orig: str):
    """对 imgKey 和 subKey 进行字符顺序打乱编码"""
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, '')[:32]


def enc_wbi(params: dict, img_key: str, sub_key: str):
    """为请求参数进行 wbi 签名"""
    mixin_key = get_mixin_key(img_key + sub_key)
    curr_time = round(time.time())

    all_params = params.copy()
    all_params['wts'] = curr_time

    all_params = {
        k: ''.join(filter(lambda chr: chr not in "'()*", str(v)))
        for k, v in all_params.items()
    }

    sorted_params = dict(sorted(all_params.items()))
    query = urllib.parse.urlencode(sorted_params)
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()

    sorted_params['w_rid'] = wbi_sign

    return sorted_params

def get_wbi_keys(session: requests.Session) -> tuple[str, str]:
    """获取 img_key 和 sub_key"""
    try:
        resp = session.get('https://api.bilibili.com/x/web-interface/nav')
        resp.raise_for_status()
        json_content = resp.json()

        # 获取wbi_img
        if json_content.get("code") == 0 and json_content["data"].get("wbi_img"):
            img_url: str = json_content['data']['wbi_img']['img_url']
            sub_url: str = json_content['data']['wbi_img']['sub_url']
            img_key = img_url.rsplit('/', 1)[1].split('.')[0]
            sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
            api_logger.debug("WBI Keys retrieved successfully.")
            return img_key, sub_key
        else:
            api_logger.error(f"Failed to get WBI keys from /nav API: {json_content.get('message', 'Unknown error')}")
            return "", ""
    except Exception as e:
        api_logger.exception(f"An error occurred while fetching WBI keys: {e}")
        return "", ""