import json
import logging
import re
from typing import Optional, Dict, Any, List, Tuple
import requests

deepseek_logger = logging.getLogger("Bilibili.DeepSeek")

# 定义函数工具
FUNCTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_comment",
            "description": "生成一条自然、真诚的B站评论，用于参与抽奖活动",
            "parameters": {
                "type": "object",
                "properties": {
                    "comment_content": {
                        "type": "string",
                        "description": "生成的评论内容"
                    }
                },
                "required": ["comment_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_at_requirement",
            "description": "分析抽奖动态是否需要艾特好友",
            "parameters": {
                "type": "object",
                "properties": {
                    "requires_at": {
                        "type": "boolean",
                        "description": "是否需要艾特好友"
                    },
                    "at_count": {
                        "type": "integer",
                        "description": "需要艾特的好友数量"
                    }
                },
                "required": ["requires_at", "at_count"]
            }
        }
    }
]

def deepseek_api(
    prompt: str, 
    system_prompt: str, 
    api_key: str, 
    model: str, 
    temperature: float,
    tools: Optional[List[Dict]] = None,
    tool_choice: Optional[str] = None
) -> Tuple[Optional[Dict], int]:
    """调用Deepseek API"""
    if not api_key:
        deepseek_logger.error("DeepSeek API 密钥未配置，无法调用")
        return None, 0

    api_url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": 500,
        "tools": tools,
        "tool_choice": tool_choice
    }
    
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        deepseek_logger.debug(f"正在调用 DeepSeek API (模型: {model})...")
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=180,
        )
        response.raise_for_status()
        response_json = response.json()
        deepseek_logger.debug(f"API 响应: {response_json}")
        
        message = response_json.get("choices", [{}])[0].get("message")
        total_tokens = response_json.get("usage", {}).get("total_tokens", 0)
        
        if tool_calls := message.get("tool_calls"):
            tool_call = tool_calls[0]
            function_name = tool_call["function"]["name"]
            function_args = tool_call["function"]["arguments"]
            deepseek_logger.debug(f"函数调用: {function_name} with args: {function_args}")
            return {
                "type": "function_call",
                "function_name": function_name,
                "arguments": function_args,
                "raw_message": message
            }, total_tokens
        else:
            content = message.get("content", "").strip()
            deepseek_logger.debug(f"文本: {content}")
            return {
                "type": "text",
                "content": content,
                "raw_message": message
            }, total_tokens

    except requests.exceptions.RequestException as e:
        deepseek_logger.error(f"调用 DeepSeek API 时发生网络错误: {e}")
    except Exception as e:
        deepseek_logger.exception(f"调用 DeepSeek API 时发生未知错误: {e}")
    
    return None, 0

def generate_comment(config: Dict[str, Any], name: str, prompt: str, api_key: str, model: str, temperature: float) -> Tuple[Optional[str], int]:
    """生成评论"""
    add_name_rule = f"   - 第一人称“我”,自然的在评论内容中带上我的昵称'{name}'\n" if config.get("enable_comment_add_name") else ""
    
    system_prompt = f"""
# 身份
你是一名B站用户，看到喜欢的UP主发起了抽奖动态，希望留言参与

# 核心目标
生成一条自然、真诚、不暴露抽奖目的的评论

# 规则清单
1.  最高优先级： 如果要求评论固定内容，则你的输出**只能**是该固定内容
2.  次优先级： 如果动态中明确要求评论特定内容或回答问题，则你的评论内容需围绕该要求展开
3.  评论焦点： 在没有明确评论要求或固定内容要求时，你的评论内容只能围绕“动态/视频内容本身“或“奖品本身“展开 例如，赞美祝贺UP主、讨论内容、或表达对奖品的喜爱
4.  绝对禁止：
    - 禁止使用"这个XX", "XX觉得"格式
    - 禁止描述自己的任何行为，例如“我关注了“这是最重要的一条禁令，因为这听起来像机器人
    - 禁止提及“抽奖“、“中奖“、“分子“等任何与抽奖行为相关的词语
    - 禁止出现emoji、表情包
    - 禁止与参考评论无区别
5.  风格要求：
{add_name_rule}
    - 字数在 15-40 字之间
    - 结尾可自然地加上一个可爱语气词，如喵, 哦, 呢, 啦, 叭, 呀
"""
    
    response, tokens = deepseek_api(
        prompt=prompt,
        system_prompt=system_prompt,
        api_key=api_key,
        model=model,
        temperature=temperature,
        tools=FUNCTION_TOOLS[:1],
        tool_choice={"type": "function", "function": {"name": "generate_comment"}}
    )
    
    if not response or response["type"] != "function_call" or response["function_name"] != "generate_comment":
        return None, tokens

    try:
        args = json.loads(response["arguments"])
        comment_content = args["comment_content"]
        
        patterns_to_remove = [r'[（(][^（）)]*?[)）]', r'@\w+', r'#\w+#?', r'\[[^\[\]]*?\]']
        for pattern in patterns_to_remove:
            comment_content = re.sub(pattern, '', comment_content)
        
        return comment_content, tokens
    except (json.JSONDecodeError, KeyError) as e:
        deepseek_logger.error(f"解析参数失败: {e}")
        return None, tokens


def check_at_requirement(prompt: str, api_key: str, model: str, temperature: float) -> Tuple[bool, int]:
    """检查艾特要求"""
    system_prompt = """
你是一名抽奖活动参与者
请分析是否有艾特好友的要求以符合抽奖参与的条件
请注意:
1. 艾特好友的要求指的是需要参与者自行选择好友艾特的情况，而不是指定账号
2. 艾特好友不是关注特定用户
3. 你的输出格式必须是一个 tuple[bool, int]
 - bool: 是否需要艾特好友（True/False）
 - int: 需要艾特的好友数量。如果未明确数量，则为 1
你只能返回这个元组，不要有任何其他文字或解释
"""
    
    response, tokens = deepseek_api(
        prompt=prompt,
        system_prompt=system_prompt,
        api_key=api_key,
        model=model,
        temperature=temperature,
        tools=FUNCTION_TOOLS[1:],
        tool_choice={"type": "function", "function": {"name": "check_at_requirement"}}
    )
    
    if not response or response["type"] != "function_call" or response["function_name"] != "check_at_requirement":
        return False, tokens
    
    try:
        args = json.loads(response["arguments"])
        requires_at = args["requires_at"]
        at_count = args["at_count"]
        deepseek_logger.debug(f"艾特要求分析结果: requires_at={requires_at}, at_count={at_count}")
        return requires_at, at_count
    except (json.JSONDecodeError, KeyError) as e:
        deepseek_logger.error(f"解析参数失败: {e}")
        return False, tokens