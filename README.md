# 哔哩哔哩自动抽奖（半自动）

一个智能、全自动的 Bilibili 互动抽奖助手。用户只需提供包含抽奖动态的链接，程序即可为多个账号自动完成关注、点赞、评论、转发等一系列操作。

## 主要功能

  * **👥 多账号管理**: 支持同时管理多个B站账号，并通过扫码方式轻松登录。
  * **⚙️ 全自动化操作**: 自动完成关注UP主、点赞、评论、转发动态或视频的完整流程。
  * **🤖 AI 智能评论**: 可集成 DeepSeek API，根据动态内容智能生成自然、高质量的评论。
  * **📝 自定义评论**: 支持配置固定的评论列表，在不使用 AI 的情况下随机选择发送。
  * **📱 扫码登录**: 无需手动获取 Cookie，通过运行脚本生成二维码，使用B站手机客户端扫码即可安全登录。
  * **🔔 Telegram Bot 通知**: 任务完成后，可通过 Telegram Bot 推送详细的任务报告，包括成功、失败统计和日志。
  * **🏆 中奖检查**: 内置独立的检查脚本，可自动扫描所有账号的私信、@和回复，检测中奖信息。

## 环境准备

1.  确保您的系统中已安装 **Python 3.8** 或更高版本。
2.  安装项目所需的依赖库：
    ```bash
    pip install requests qrcode
    ```

## 配置流程

### 1\. 登录B站账号 (获取 Cookie)

#### 方法一：扫码登录 (推荐)

项目支持通过扫码自动完成登录和配置。在命令行中运行：

```bash
python qr.py
```

程序会生成一个登录二维码，请使用Bilibili手机客户端扫描该二维码并确认登录。成功后，您的账号 Cookie 和一个默认的配置模板将自动保存到 `config.json` 文件中。

#### 方法二：手动获取 Cookie

1.  在浏览器中访问 [bilibili.com](https://www.bilibili.com/) 并登录您的账号。
2.  按 `F12` 键打开浏览器开发者工具。
3.  切换到 `Network` (或 `网络`) 标签页。
4.  刷新页面，在请求列表中找到任意一个发往 `api.bilibili.com` 的请求（如 `nav`）。
5.  在请求的 `Headers` (或 `标头`) 部分，找到 `Cookie` 字段，并复制其完整的字符串值。
6.  将复制的 Cookie 值粘贴到 `config.json` 文件中对应账号的 `cookie` 字段。

### 2\. 账号配置示例

每通过扫码登录一个新账号，`config.json` 的 `accounts` 列表中就会新增一个配置对象。您可以根据需求修改其中的参数：

```json
"accounts": [
    {
      "remark": "憨憨",
      "cookie": "SESSDATA=......",
      "enabled": true,
      "video_like_enabled": false,
      "ai_comment": true,
      "use_fixed_comment": true,
      "fixed_comments": [
        "许愿喵",
        "来当分母啦！",
        "好好好，支持一下"
      ],
      "use_fixed_repost": false,
      "fixed_reposts": [],
      "emoticons": [
        "[星星眼]",
        "[给心心]",
        "[点赞]",
        "_(≧∇≦」∠)_"
      ]
    }
]
```

  * `remark`: 账号备注，用于日志和通知中区分账号。
  * `enabled`: `true` 表示启用该账号，`false` 则跳过。
  * `video_like_enabled`: `true` 表示启用该账号进行视频点赞，`false` 则跳过。
  * `ai_comment`: `true` 优先使用 DeepSeek 生成评论。
  * `use_fixed_comment`: 当 AI 评论未启用或生成失败时，是否使用 `fixed_comments` 列表中的固定评论。
  * `fixed_comments`: 固定的评论内容列表，程序会从中随机选择一条。
  * `emoticons`: 评论末尾附加的表情列表，程序会随机选择一个。

### 3\. DeepSeek API (可选)

为了让评论内容更智能、更贴合动态本身，您可以配置 DeepSeek API。

编辑 `config.json`，填入您的 API Key：

```json
"deepseek": {
  "deepseek_api_key": "sk-xxxxxxxxxxxxxxxxxxxx",
  "deepseek_base_url": "https://api.deepseek.com/v1",
  "deepseek_model": "deepseek-chat",
  "temperature": 1.3
}
```

### 4\. Telegram 通知 (可选)

配置后，程序每次运行结束都会通过 Telegram Bot 发送一份任务报告。

编辑 `config.json`，填入您的 Bot Token 和 Chat ID：

```json
"telegram": {
  "enable": true,
  "bot_token": "YOUR_BOT_TOKEN",
  "chat_id": "YOUR_CHAT_ID"
}
```

**通知示例:**

```
博士，这里是澄闪的任务报告~

📊 操作统计：
• 爬取成功：15次
• 点赞成功：28次
• 转发成功：28次
• 关注成功：28次
• 评论成功：28次
• 失败总数：0次

• 用时：34分41秒

所有操作都顺利完成啦！澄闪有好好完成任务哦~

博士要记得检查日志文件呢，澄闪会继续努力的！
```

## 如何运行

### 1\. 添加抽奖链接

编辑项目根目录下的 `origin.txt` 文件。您可以将包含多个抽奖动态的页面内容直接复制并粘贴进去，程序会自动提取其中的B站链接，无需手动整理成每行一条。

**推荐的抽奖信息来源UP主：**

  * [你的抽奖工具人](https://space.bilibili.com/100680137)
  * [*大锦鲤*](https://space.bilibili.com/226257459)
  * [互动抽奖娘](https://www.google.com/search?q=https://space.bilibili.com/3546776042736296)

### 2\. 运行程序

在命令行中执行 `run.py` 脚本：

```bash
python run.py
```

程序会显示一个菜单，您可以选择：

  * **`0: 运行抽奖程序`**: 开始处理 `origin.txt` 中的抽奖任务。
  * **`1: 检查是否中奖`**: 扫描所有已配置账号的消息，检查中奖情况。

### 3\. 执行流程说明

1.  **链接提取与过滤**: 程序首先读取 `origin.txt` 的全部内容，使用正则表达式提取所有B站动态和视频链接。然后，它会与 `cache/history_url_list.txt` 中的历史记录进行比对，自动过滤掉已经处理过的链接。
2.  **任务执行**: 对每个未处理的链接，程序会为 `config.json` 中所有启用的账号，依次执行关注、点赞、评论、转发等操作。
3.  **结果记录**: 完成处理的链接会被添加到历史记录文件中，以避免下次重复执行。

## 注意事项

  * **评论内容优先级**:

    1.  如果 `ai_comment` 为 `true` 且 API Key 有效，优先使用 **DeepSeek 生成**的评论。
    2.  如果 AI 生成失败或未启用，且 `use_fixed_comment` 为 `true`，则使用账号配置的**固定评论**。
    3.  如果以上两者都不可用，则不发表评论。

  * **操作延迟配置**:
    为了模拟真人行为，避免账号被风控，请务必设置合理的延迟时间。**延迟不要设置得太短！**

    在 `config.json` 中调整：

    ```json
    "action_delay_min_seconds": 20,
    "action_delay_max_seconds": 30
    ```

    这表示每两次操作（如点赞和评论之间）会有 20 到 30 秒的随机等待时间。
  
- 详细日志查看 `bili.log`
  
- 错误信息记录在 `output/error.log`
