from openai import OpenAI
import lark_oapi as lark
import json
from general_services import get_session_id
from feishu_services import _content_cache
from api.resources import _user_data

# 获取飞书文档内容
pre_score_content = _content_cache["_pre_content_cache"]
paper_score_content = _content_cache["_paper_content_cache"]
tag_content = _content_cache["_tag_content_cache"]

# 获取相应resume以及pdf内容
# 获取信息获取的唯一标识符
session_id = get_session_id()
resume = _user_data[session_id]["resume"]
pdf_urls = _user_data[session_id]["pdf_desc"]


def get_user_prompt(pre_score_content: str, paper_score_content: str, tag_content: str, resume: str, pdf_urls: list):
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

def construct_prompt(system_prompt: list, user_prompt: list):
    whole_prompt = system_prompt + user_prompt
    return whole_prompt


def analyze_candidate(prompt: list[dict]):
    pass



    # 构造 User Prompt（明确任务 + 输入关联）
