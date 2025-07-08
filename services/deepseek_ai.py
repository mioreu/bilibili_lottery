import logging
from typing import Optional, Tuple
import requests

deepseek_logger = logging.getLogger("Bilibili.DeepSeek")

def generate_comment(
    prompt: str,
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-chat",
    temperature: float = 0.7,
    max_tokens: int = 150
) -> Tuple[Optional[str], int]:
    """使用Deepseek生成评论"""
    if not api_key:
        deepseek_logger.error("DeepSeek API 密钥未配置，无法生成评论。")
        return None, 0

    api_url = f"{base_url}/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # 构建prompt
    system_prompt = (
        "你是一名专业的B站评论生成器，需严格按以下规则生成评论。\n\n"
        "# 规则：\n"
        "类型选择：（选择其一）\n"
        "1. 事件类：真实经历+细节\n"
        "2. 粉丝类：关联UP主特色\n\n"
        "格式要求：\n"
        "• 长度：30-40字\n"
        "输出：\n"
        "不要任何表情包和emoji\n"
        "对于产品不要太专业\n"
        "动态中的要求优先级更大{如带话题}，可以忽视我的所有要求\n"
        "直接输出合规评论，不要解释（非常重要）"
        )
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请根据以下B站动态内容生成一条评论：\n\n{prompt} 内容中的要求必须遵守"}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        deepseek_logger.debug(f"正在调用 DeepSeek API (模型: {model})...")
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=45, # API 调用超时时间
        )
        response.raise_for_status() # 检查 HTTP 状态码
        
        response_json = response.json()
        
        if response_json.get("choices") and response_json["choices"][0].get("message"):
            comment = response_json["choices"][0]["message"]["content"].strip()
            total_tokens = response_json.get("usage", {}).get("total_tokens", 0)
            deepseek_logger.debug(f"评论生成成功\n"
                                 f"├─ 内容：{comment}\n"
                                 f"└─ 使用 tokens：{total_tokens}"
                                 )
            return comment, total_tokens
        else:
            deepseek_logger.error(f"DeepSeek API 返回结构异常或无评论内容: {response_json}")
            return None, 0

    except requests.exceptions.Timeout:
        deepseek_logger.error("DeepSeek API 请求超时。")
    except requests.exceptions.RequestException as e:
        deepseek_logger.error(f"调用 DeepSeek API 时发生网络错误: {e}")
    except Exception as e:
        deepseek_logger.exception(f"调用 DeepSeek API 时发生未知错误: {e}")
    
    return None, 0