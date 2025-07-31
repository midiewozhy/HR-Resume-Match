import logging
import json
from services.general_services import get_session_id
from services.feishu_services import _content_cache, _system_prompt_cache
from services.client import llm_client
import re
import json
from config import Config

# 静态数据
# 获取飞书文档内容
pre_score_content = _content_cache["_pre_content_cache"]
paper_score_content = _content_cache["_paper_content_cache"]
tag_content = _content_cache["_tag_content_cache"]
# 获取system prompt
system_prompt = _system_prompt_cache

# 自定义Error类型
class APIEmptyError(Exception):
    def __init__(self):
        super().__init__("非常抱歉，服务暂时不可用哦~请稍后再试或联系技术支持哟！")

class LLMContentEmptyError(Exception):
    def __init__(self):
        super().__init__("评估结果生成失败啦~再给大模型一次机会吧！或者也可以联系技术支持哦！")

def get_user_prompt(resume: str, pdf_urls: list):
    user_info = f"""
    分析素材：  
    - 简历内容： {resume}
    - 论文链接：  {pdf_urls}
    - 评分标准（预打分用）：{pre_score_content}  
    - 岗位画像（匹配岗位用）：{tag_content}  
    - 论文打分方针（有论文时用）：{paper_score_content} 
    请严格按 system prompt 输出 JSON。  
    """

    user_prompt = [
        {"role": "user", "content": user_info},
    ]

    return user_prompt

def construct_prompt(user_prompt: list):
    whole_prompt = system_prompt + user_prompt
    return whole_prompt

def analyze_candidate(resume: str, pdf_urls: list):
    """分析候选人，内部实时获取动态数据，复用静态数据"""
    # 1. 构造prompt（复用静态数据和动态数据）
    user_prompt = get_user_prompt(resume, pdf_urls)  # 传入动态数据，内部引用静态数据
    whole_prompt = construct_prompt(user_prompt)  # 内部引用静态的system_prompt

    # 3. 调用大模型
    completion = llm_client.chat.completions.create(
        model=Config.BOT_ID,
        messages=whole_prompt,
        temperature=0,
        seed=42,
    )

    # 4. 校验响应
    if not completion.choices or not completion.choices[0].message.content:
        raise APIEmptyError # 抛出异常，由API层处理

    # 5. 处理返回结果
    ai_ret = completion.choices[0].message.content.strip()
    ai_ret = re.sub(r'^(<\|FunctionCallEnd\|>|```json\n?|```\n?)', '', ai_ret, flags=re.IGNORECASE)
    ai_ret = re.sub(r'```\s*$', '', ai_ret)

    if not ai_ret:
        raise LLMContentEmptyError # 抛出异常
    
    if ai_ret.startswith("{{"):
        ai_ret = ai_ret[1:]
    if ai_ret.endswith("}}"):
        ai_ret = ai_ret[:-1]

    # 6. 解析JSON并返回
    try:
        return json.loads(ai_ret)
    except json.JSONDecodeError as e:
        logging.error(f"JSON解析失败 | 内容: {ai_ret[:100]}... | 错误：{str(e)}")
        raise LLMContentEmptyError from e