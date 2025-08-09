import ast
import logging
import re
from typing import Optional, Tuple, Dict, Any
import requests

deepseek_logger = logging.getLogger("Bilibili.DeepSeek")

def deepseek_api(prompt: str,system_prompt:str,api_key: str, model: str,temperature: float) -> Tuple[Optional[str], int]:
    """调用Deepseek API"""
    if not api_key:
        deepseek_logger.error("DeepSeek API 密钥未配置，无法调用")
        return None, 0

    api_url = f"https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # 构建prompt
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": 150,
    }

    try:
        deepseek_logger.debug(f"正在调用 DeepSeek API (模型: {model})...")
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=180, # API 调用超时时间
        )
        response.raise_for_status() # 检查 HTTP 状态码
        
        response_json = response.json()
        
        if response_json.get("choices") and response_json["choices"][0].get("message"):
            content = response_json["choices"][0]["message"]["content"].strip()
            total_tokens = response_json.get("usage", {}).get("total_tokens", 0)
            deepseek_logger.debug(f"├─ 内容：{content}\n"
                                  f"└─ 使用 tokens：{total_tokens}\n{response_json}"
                                 )
            return content, total_tokens
        else:
            deepseek_logger.error(f"DeepSeek API 返回结构异常或无内容: {response_json}")
            return None, 0

    except requests.exceptions.Timeout:
        deepseek_logger.error("DeepSeek API 请求超时。")
    except requests.exceptions.RequestException as e:
        deepseek_logger.error(f"调用 DeepSeek API 时发生网络错误: {e}")
    except Exception as e:
        deepseek_logger.exception(f"调用 DeepSeek API 时发生未知错误: {e}")
    
    return None, 0

def generate_comment(config: Dict[str, Any], name: str, prompt: str, api_key: str, model: str, temperature: float):
    """生成评论"""
    add_name_rule = f"   - 第一人称“我”,自然的在评论内容中带上我的昵称'{name}'\n" if config.get("enable_comment_add_name") else ""

    system_prompt = (
"# 身份\n"
"你是一名B站用户，看到喜欢的UP主发起了抽奖动态，希望留言参与\n"

"# 核心目标\n"
"生成一条自然、真诚、不暴露抽奖目的的评论\n"

"# 规则清单\n"
"1.  最高优先级： 如果要求评论固定内容，则你的输出**只能**是该固定内容\n"
"2.  次优先级： 如果动态中明确要求评论特定内容或回答问题，则你的评论内容需围绕该要求展开\n"
"3.  评论焦点： 在没有明确评论要求或固定内容要求时，你的评论内容只能围绕“动态/视频内容本身”或“奖品本身”展开 例如，赞美祝贺UP主、讨论内容、或表达对奖品的喜爱\n"
"4.  绝对禁止：\n"
"    - 禁止描述自己的任何行为，例如“我关注了”、“我点赞了”、“已三连” 这是最重要的一条禁令，因为这听起来像机器人\n"
"    - 禁止提及“抽奖”、“中奖”、“分子”等任何与抽奖行为相关的词语\n"
"    - 禁止出现emoji、表情包\n"
"5.  风格要求：\n"
f"{add_name_rule}"
"    - 字数在 35-70 字之间\n"
"    - 结尾可自然地加上一个可爱语气词，如喵, 哦, 呢, 啦, 叭, 呀\n"
"# 输出\n"
"直接输出最终评论，无需任何解释(重要)"
    )
    content, token = deepseek_api(prompt, system_prompt, api_key, model,temperature)
    content = content.replace('"', '')
    content = re.sub(r'[（(].*?[)）]', '', content)
    content = re.sub(r'@\S+', '', content)
    content = re.sub(r'#.*?#', '', content)
    return content, token

def check_at_requirement(prompt: str, api_key: str, model: str, temperature: float) -> Tuple[bool, int]:
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
    content, _ = deepseek_api(prompt, system_prompt, api_key, model, temperature)

    result = ast.literal_eval(content)
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], bool) and isinstance(result[1],int):
        deepseek_logger.debug(f"{result}")
        return result

    else:
        deepseek_logger.error(f"API 返回的格式不符合预期: {content}")
        return False, 0