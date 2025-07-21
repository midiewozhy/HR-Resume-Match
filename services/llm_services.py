import logging
import json
from general_services import get_session_id
from feishu_services import _content_cache, _system_prompt_cache
from api.resources import _user_data
from client import llm_client
from config import Config
import re
from flask import jsonify

# 静态数据
# 获取飞书文档内容
pre_score_content = _content_cache["_pre_content_cache"]
paper_score_content = _content_cache["_paper_content_cache"]
tag_content = _content_cache["_tag_content_cache"]
# 获取system prompt
system_prompt = _system_prompt_cache

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

def analyze_candidate():
    """分析候选人，内部实时获取动态数据，复用静态数据"""
    # 1. 实时获取当前请求的动态数据（依赖session_id，每次请求可能不同）
    session_id = get_session_id()  # 实时获取当前会话ID
    resume = _user_data[session_id]["resume"]  # 当前会话的简历
    pdf_urls = _user_data[session_id]["pdf_desc"]  # 当前会话的论文链接

    # 2. 构造prompt（复用静态数据和动态数据）
    user_prompt = get_user_prompt(resume, pdf_urls)  # 传入动态数据，内部引用静态数据
    whole_prompt = construct_prompt(user_prompt)  # 内部引用静态的system_prompt
    logging.info(f"收到候选人分析请求 | session_id: {session_id} | prompt: {whole_prompt}")

    # 3. 调用大模型
    completion = llm_client.chat.completions.create(
        model=Config.BOT_ID,
        messages=whole_prompt,
        temperature=0,
        seed=42,
    )

    # 4. 校验响应
    if not completion.choices or not completion.choices[0].message.content:
        raise ValueError("API响应为空")  # 抛出异常，由API层处理

    # 5. 处理返回结果
    ai_ret = completion.choices[0].message.content.strip()
    ai_ret = re.sub(r'^(<\|FunctionCallEnd\|>|```json\n?|```\n?)', '', ai_ret, flags=re.IGNORECASE)
    ai_ret = re.sub(r'```\s*$', '', ai_ret)

    if not ai_ret:
        raise ValueError("大模型返回内容为空")  # 抛出异常

    # 6. 解析JSON并返回（异常由API层捕获）
    return json.loads(ai_ret)