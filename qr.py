import json
import time
from typing import List
import requests
import qrcode
import webbrowser
import api.api_constants as api
from api.bilibili_client import BilibiliClient
from urllib.parse import quote
from pathlib import Path

class BiliQRLogin:
    def __init__(self, config_path: str = "accounts.json"):
        self.config_path = Path(config_path).absolute()
        self.session = requests.Session()
        self.session.headers.update(api.BASE_HEADERS)

    def _generate_qr(self) -> dict:
        """生成登录二维码"""
        resp = self.session.get(api.API_QR_GEN, timeout=10)
        resp.raise_for_status()
        return resp.json()["data"]

    def _poll_login(self, qrcode_key: str) -> dict:
        """查询扫码状态"""
        params = {"qrcode_key": qrcode_key}
        resp = self.session.get(api.API_QR_POLL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()["data"]

    def _get_cookies_str(self) -> str:
        """获取cookies"""
        cookie_dict = {}
        for cookie in self.session.cookies:
            cookie_dict[cookie.name] = cookie.value
        return "; ".join([f"{name}={value}" for name, value in cookie_dict.items()])

    def _save_to_config(self, cookies: str, remark: str):
        config: List[dict] = []
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded_content = json.load(f)
                    if isinstance(loaded_content, list):
                        config = loaded_content
                    else:
                        print(f"配置文件 {self.config_path} 格式错误，应为列表，已忽略旧配置")
            except Exception as e:
                print(f"读取配置文件时发生错误: {e}")

        replaced = False
        for idx, account in enumerate(config):
            if account.get("remark") == remark:
                config[idx]["cookie"] = cookies
                replaced = True
                break

        if not replaced:
            new_account = {
                "remark": remark,
                "cookie": cookies,
                "enabled": True,
                "video_like_enabled": True,
                "ai_comment": True,
                "only_followed": False,
                "use_fixed_comment": True,
                "fixed_comments": ["许愿喵"],
                "use_fixed_repost": False,
                "fixed_reposts": [],
                "emoticons": [
                    "[星星眼]",
                    "[给心心]",
                    "[点赞]",
                    "[脱单doge]",
                    "[鼓掌]",
                    "[热词系列_干杯]",
                    "[tv_doge]",
                    "[tv_色]",
                    "_(≧∇≦」∠)_",
                    "[打call]"
                ]
            }
            config.append(new_account)

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def _display_qr(self, url: str):
        encoded_url = quote(url)
        qr_image_url = f"{api.API_QR_CODE}?data={encoded_url}&width=300"

        print("\n二维码：")
        qr = qrcode.QRCode()
        qr.add_data(qr_image_url)
        qr.print_ascii()
        print(f"链接获取二维码图片进行登录：")
        print(f"➡ {qr_image_url}")
        try:
            webbrowser.open(qr_image_url)
            print("\n已尝试在浏览器中打开二维码图片，请检查您的浏览器。")
        except Exception as e:
            print(f"无法自动打开浏览器: {e}. 请手动访问上面的链接。")

    def _get_buvid(self):
        """获取 buvid3 和 buvid4"""
        try:
            resp = self.session.get(api.API_BUVID_SPI, timeout=5)
            resp.raise_for_status()
            data = resp.json()["data"]
            if "b_3" in data:
                self.session.cookies.set("buvid3", data["b_3"], domain=".bilibili.com")
                print(f"已获取并设置 buvid3: {data['b_3']}")
            if "b_4" in data:
                self.session.cookies.set("buvid4", data["b_4"], domain=".bilibili.com")
                print(f"已获取并设置 buvid4: {data['b_4']}")
        except Exception as e:
            print(f"获取 buvid3/buvid4 失败: {e}")

    def login(self, remark: str = "新账号") -> bool:
        try:
            self._get_buvid()

            qr_data = self._generate_qr()
            print("\n请选择以下任一种方式扫码登录：")
            self._display_qr(qr_data["url"])

            start_time = time.time()
            while time.time() - start_time < 180:
                poll_data = self._poll_login(qr_data["qrcode_key"])

                if poll_data["code"] == 0:
                    self.session.get(poll_data["url"])
                    cookies = self._get_cookies_str()
                    self._save_to_config(cookies, remark)
                    print(f"\n✅ 登录成功！账号已保存到 {self.config_path}")
                    return True
                elif poll_data["code"] == 86038:
                    print("\n❌ 二维码已过期，请重新运行程序")
                    return False
                elif poll_data["code"] == 86090:
                    print("\n已扫码，请在手机上确认登录...")

                time.sleep(2)

            print("\n登录超时（3分钟）")
            return False

        except Exception as e:
            print(f"\n发生未知错误: {str(e)}")
            return False


if __name__ == "__main__":
    bili_clients: List[BilibiliClient] = []
    i = int(len(bili_clients))
    num = i + 1
    print(" 账号登录 ".center(40, "="))
    remark = input("请输入账号备注（回车使用默认名称）：").strip() or f"账号_{num}"

    qr = BiliQRLogin()
    if qr.login(remark):
        print("\n账号添加完成")
    else:
        print("\n登录失败")