
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
API_QR_CODE = "https://devtool.tech/api/qrcode" # 第三方二维码生成
API_BUVID_SPI =  "https://api.bilibili.com/x/frontend/finger/spi" #  获取buvid3/buvid4
URL_NAV_INFO = "https://api.bilibili.com/x/web-interface/nav" # 账号信息
URL_LIKE_THUMB = "https://api.vc.bilibili.com/dynamic_like/v1/dynamic_like/thumb"  # 点赞
URL_REPOST_DYNAMIC = "https://api.vc.bilibili.com/dynamic_repost/v1/dynamic_repost/repost"  # 转发动态
URL_COMMENT = "https://api.bilibili.com/x/v2/reply/add"  # 评论
URL_FOLLOW = "https://api.bilibili.com/x/relation/modify" # 关注/取关
URL_DYNAMIC_CONTENT = "https://api.bilibili.com/x/polymer/web-dynamic/desktop/v1/detail" # 获取动态详情
URL_CHECK_FOLLOW = "https://api.bilibili.com/x/relation" # 检查关注状态
URL_CHECK_AT = "https://api.bilibili.com/x/msgfeed/at" # 获取@详情
URL_CHECK_REPLY = "https://api.bilibili.com/x/msgfeed/reply" # 获取回复详情
URL_GET_SESSION_INFO = "https://api.vc.bilibili.com/session_svr/v1/session_svr/get_sessions" # 获取私信会话列表
URL_MESSAGE_DETAIL = "https://api.vc.bilibili.com/svr_sync/v1/svr_sync/fetch_session_msgs" # 获取私信详情
URL_REPOST_VIDEO = "https://api.bilibili.com/x/dynamic/feed/create/dyn" # 转发视频
URL_LIKE_VIDEO = "https://api.bilibili.com/x/web-interface/archive/like" # 点赞视频
URL_POPULAR_VIDEO = "https://api.bilibili.com/x/web-interface/wbi/index/top/feed/rcmd" # 获取热门视频
URL_VIDEO_DETAIL = "https://api.bilibili.com/x/web-interface/view" # 获取视频详情
URL_GET_COMMENT = "https://api.bilibili.com/x/v2/reply" # 获取评论区评论
URL_COMMENT_REPLY = "https://api.bilibili.com/x/v2/reply/reply" # # 评论状态检查
