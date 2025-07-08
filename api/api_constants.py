
BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Origin": "https://www.bilibili.com",
    }
API_QR_GEN = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate" # 生成登录二维码
API_QR_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll" # 查询扫码状态
QR_CODE_API = "https://devtool.tech/api/qrcode" # 第三方二维码生成
URL_NAV_INFO = "https://api.bilibili.com/x/web-interface/nav" # 账号信息
URL_LIKE_THUMB = "https://api.vc.bilibili.com/dynamic_like/v1/dynamic_like/thumb"  # 点赞
URL_REPOST = "https://api.vc.bilibili.com/dynamic_repost/v1/dynamic_repost/repost"  # 转发
URL_COMMENT = "https://api.bilibili.com/x/v2/reply/add"  # 评论
URL_FOLLOW = "https://api.bilibili.com/x/relation/modify" # 关注/取关
URL_DYNAMIC_DETAIL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail" # 获取动态详情
URL_DYNAMIC_CONTENT = "https://api.bilibili.com/x/polymer/web-dynamic/desktop/v1/detail" # 获取动态内容
URL_CHECK_FOLLOW = "https://api.bilibili.com/x/relation" # 检查关注状态
URL_CHECK_AT = "https://api.bilibili.com/x/msgfeed/at" # 检查@详情