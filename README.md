# 环境准备

1. 安装 Python 3.8+
2. 安装依赖库：
  
  ```bash
  pip install requests qrcode
  ```
  

# 配置流程

## 1. 获取B站Cookie

### 方法1：扫码登录（推荐）

```bash
python qr.py
```

扫描生成的二维码登录，将自动获取cookie并配置账号信息

### 方法2：手动获取

1. 访问 [bilibili.com](https://www.bilibili.com/) 并登录
2. 按 `F12` 打开开发者工具
3. 转到 `Network`或`网络` 标签页
4. 刷新页面，搜索 "nav" 请求
5. 复制请求头中的全部 Cookie 值

## 2. 账号

| 参数名 | 说明  | 必填  |
| --- | --- | --- |
| `remark` | 账号备注名（用于日志标识） | 是   |
| `cookie` | B站登录Cookie | 是   |
| `enabled` | 是否启用该账号 | 否   |
| `like_enabled` | 是否启用点赞功能 | 否   |
| `comment_enabled` | 是否启用评论功能 | 否   |
| `repost_enabled` | 是否启用转发功能 | 否   |
| `follow_enabled` | 是否启用关注UP主功能 | 否   |
| `use_fixed_comment` | 是否使用固定评论 | 否   |
| `fixed_comments` | 固定评论内容池 | 否   |
| `use_fixed_repost` | 是否使用固定转发语 | 否   |
| `fixed_reposts` | 固定转发内容池 | 否   |
| `emoticons` | 表情包集合 | 否   |

## 3. DeepSeek API (可选)

`config.json`
使用DeepSeek，生成与抽奖动态内容相关的评论
若填入key，则优先使用DeepSeek发送评论

```json
"deepseek": {
  "deepseek_api_key": "YOUR_DEEPSEEK_KEY",
  "deepseek_base_url": "https://api.deepseek.com/v1",
  "deepseek_model": "deepseek-chat",
  "temperature": 1.3
}
```

## Telegram 通知 (可选)

使用telegram bot 发送通知

```json
"telegram": {
  "enable": true,
  "bot_token": "YOUR_BOT_TOKEN",
  "chat_id": "YOUR_CHAT_ID"
}
```

通知示例:

```
哔哩哔哩动态抽奖
博士，这里是澄闪的任务报告~

📊 操作统计：
• 点赞成功：28次
• 转发成功：28次
• 关注成功：28次
• 评论成功：28次
• 失败总数：0次

• 用时：34分41秒

所有操作都顺利完成啦！澄闪有好好完成任务哦~

博士要记得检查日志文件呢，澄闪会继续努力的！
```

# 运行

## 添加动态链接

1. 编辑 `origin.txt` 文件，直接复制抽奖合集的全部内容
2. 抽奖合集up主：[你的抽奖工具人](https://bilibili.com/space/100680137),[_大锦鲤_](https://bilibili.com/space/226257459),[互动抽奖娘](https://bilibili.com/space/3546776042736296)

## 运行程序

```bash
python run.py
```

## 执行流程说明

### 阶段1：动态爬取

- 读取 `origin.txt` 中的链接
- 自动过滤已处理记录（保存在 `cache/history_url_list.txt`）
- 解析内容保存到 `output/parsed_dynamics.txt`

## 注意事项

- 评论内容优先级：

1. DeepSeek 生成
2. 账号配置的固定评论

- 评论等操作间隔时间配置：
  **延迟不要太短**，很可能账号异常
  
  ```json
  "action_delay_min_seconds": 20,    //最短延迟(s)
  "action_delay_max_seconds": 30,    //最长延迟(s)
  "parse_delay_min_seconds": 3,    //爬取动态内容最短延迟(s)
  "parse_delay_max_seconds": 5    //爬取动态内容最长延迟(s)
  ```
  
- 详细日志查看 `bili.log`
  
- 错误信息记录在 `output/error.log`
  ```
