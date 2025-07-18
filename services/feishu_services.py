import requests
import lark_oapi as lark
from lark_oapi.api.docs.v1 import *
import time
import json
import apscheduler as scheduler
import atexit
import logging
from threading import Lock
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler


# 替换原导入方式，创建实际调度器实例
scheduler = BackgroundScheduler()
scheduler.start()  # 启动调度器
atexit.register(lambda: scheduler.shutdown())  # 程序退出时关闭

# 缓存定时更新的token_info（全局变量，供后续任务复用）
_token_cache = None
_content_cache={"_pre_content_cache":"","_paper_content_cache":"","_tag_content_cache":""}
_prompt_cache = ""
_cache_lock = Lock()  # 确保并发安全



def get_access_token(app_id, app_secret):
    """
    获取自定义应用的app_access_token
    :param app_id: 应用的唯一标识符
    :param app_secret: 应用的密钥
    :return: 包含app_access_token和过期时间的字典，失败时返回None
    """
    # 定义API请求的URL
    url = "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal"

    # 设置请求头
    headers = {"Content-Type": "application/json; charset=utf-8"}

    # 构建请求体
    payload = {"app_id": app_id, "app_secret": app_secret}

    try:
        # 发送POST请求
        response = requests.post(url, headers=headers, data=json.dumps(payload))

        # 解析响应内容
        result = response.json()

        # 检查请求是否成功（code为0表示成功）
        if result.get("code") == 0:
            # 提取app_access_token和过期时间
            access_token = result.get("app_access_token")
            expire = result.get("expire")
            lark.logger.info(result)

            # 返回包含访问令牌和过期时间的字典
            return {
                "access_token": access_token,
                "expire": expire,
                "timestamp": int(time.time()),  # 添加获取时间戳
            }
        else:
            # 打印错误信息
            lark.logger.error(
                f"获取access_token失败，错误码：{result.get('code')}，错误信息：{result.get('msg')}"
            )
            return None
    except requests.exceptions.RequestException as e:
        # 处理请求异常
        lark.logger.error(f"请求异常：{e}")
        return None
    except json.JSONDecodeError as e:
        # 处理响应解析异常
        lark.logger.error(f"响应解析异常：{e}")
        return None


def get_feishu_doc_content(doc_token: str, access_token: str) -> str:
    """获取飞书文档内容

    Args:
        doc_token (str): 文档的 token
        access_token (str): 访问令牌

    Returns:
        str: 文档内容
    """
    # 创建client
    client = (
        lark.Client.builder()
        .enable_set_token(True)
        .log_level(lark.LogLevel.DEBUG)
        .build()
    )

    # 构造请求对象
    request: GetContentRequest = (
        GetContentRequest.builder()
        .doc_token(doc_token)
        .doc_type("docx")
        .content_type("markdown")
        .build()
    )

    # 发起请求
    option = lark.RequestOption.builder().user_access_token(access_token).build()
    response: GetContentResponse = client.docs.v1.content.get(request, option)

    # 处理失败返回
    if not response.success():
        error_msg = f"client.docs.v1.content.get failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}"
        raise Exception(error_msg)

    # 返回文档内容
    return response.data.content


def get_rating_prompt(pre_score_content: str, tag_content: str, paper_score_content: str, resume_content: str, paper_urls: list) -> list:

    # 提取可能的论文链接
    urls_desc = "、".join(paper_urls) if paper_urls else "没有可供参考论文链接"

    # 给大模型的系统prompt
    system_prompt = f"""
    你是专业人才分析专家，需严格执行以下 MVP 流程：  

    ### 核心规则（必须100%遵守）  
    1. 仅用输入的简历、论文（若有）、评分标准、岗位画像分析，不引入外部知识。  
    2. 论文链接为“没有可供参考论文链接”时，跳过论文分析，仅用简历。  


    ### 任务步骤（按顺序执行）  
    1. 简历提取：技术栈、研究方向（看 publications/projects 标题）、引用量/H-index（忽略软技能）。  
    2. 论文分析（有论文时，没有则跳过）：用 {paper_score_content} 分析研究方向、创新点、优劣势。  
    3. 预打分：结合简历（+论文），用 {pre_score_content} 生成分数（浮点型）。  
    4. 岗位匹配：用 {tag_content} 匹配1-2个岗位，并匹配对应的岗位联系人。无匹配时，`job_match_1` 填“无适合岗位推荐”。  


    ### 输出强制要求（必须严格执行）  
    - 直接输出 JSON，**不加任何前缀/后缀/解释文字**（如“结果如下：”）。  
    - 字段：`cdd_score`（必选，float）、`job_match_1`（无匹配填“无适合岗位推荐”）、`job_match_1_contact`（无则 null）、`reason_1`（无则 null）、`job_match_2`（无则 null）、`job_match_2_contact`（无则 null）、`reason_2`（无则 null）。  
     - 无岗位时完整输出示例：
    {{
        "cdd_score": 2.5,
        "job_match_1": "无适合岗位推荐",
        "job_match_1_contact": null,
        "reason_1": null,
        "job_match_2": null,
        "job_match_2_contact": null,
        "reason_2": null
    }}
    """

    # 构造 User Prompt（明确任务 + 输入关联）
    user_prompt = f"""
    分析素材：  
    - 简历内容：{resume_content}  
    - 论文链接：{urls_desc}  
    - 评分标准（预打分用）：{pre_score_content}  
    - 岗位画像（匹配岗位用）：{tag_content}  
    - 论文打分方针（有论文时用）：{paper_score_content} 
    请严格按 system prompt 输出 JSON。  
    """

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def schedule_access_token(app_id: str, app_secret: str, interval_hours: int = 1):
    def _update_token():
        global _token_cache
        with _cache_lock:
            token_info = get_access_token(app_id, app_secret)
            if token_info:
                _token_cache = token_info  # 更新缓存
                logging.info(f"token缓存更新，有效期至{token_info['timestamp'] + token_info['expire']}")
    # 定时任务配置（同上）
    scheduler.add_job(_update_token, 'interval', hours=interval_hours, next_run_time=datetime.now())

def schedule_doc_content(doc_token: str, content_type: str, interval_hours: int = 1):
    cache_key = f"_{content_type}_content_cache"
    def _fetch_content():
        global _token_cache, _content_cache
        with _cache_lock:
            if not _token_cache:
                logging.error("token缓存为空，无法获取文档内容")
                return
            # 直接使用缓存的token_info，无需重复调用get_access_token
            content = get_feishu_doc_content(doc_token, _token_cache["access_token"])
            if content:
                _content_cache[cache_key] = content
            else:
                logging.error("文档获取为空")
            logging.info("使用缓存token获取文档内容成功")
    # 定时任务配置（滞后token更新10分钟）
    scheduler.add_job(_fetch_content, 'interval', hours=interval_hours, next_run_time=datetime.now() + timedelta(minutes=10))

def schedule_rating_prompt(resume_content: str, paper_urls: list, interval_hours: int = 1):
    def _update_prompt():
        global _prompt_cache
        with _cache_lock:
            contents = _content_cache.values()
            for content in contents:
                if not content:
                    logging.error("content缓存为空，没有可获取的文档内容")
                    return
            prompt = get_rating_prompt(_content_cache['_pre_content_cache'], _content_cache["_tag_content_cache"], _content_cache["_paper_content_cache"],resume_content, paper_urls)
            if prompt:
                _prompt_cache = prompt
            else:
                logging.error("prompt update为空")
            logging.info("prompt缓存更新成功")
    # 定时任务配置（滞后content更新10分钟）
    scheduler.add_job(_update_prompt, 'interval', hours=interval_hours, next_run_time=datetime.now() + timedelta(minutes=20))

def start_feishu_schedule(app_id: str, app_secret: str, doc_token: str, resume_content: str, paper_urls: list):
    """启动所有定时任务（按依赖顺序初始化）"""
    # 1. 优先启动token定时更新（基础依赖）
    schedule_access_token(app_id, app_secret, interval_hours=1)
    
    # 2. 启动文档内容定时获取（依赖token）
    schedule_doc_content(doc_token, 'pre', interval_hours=1)
    schedule_doc_content(doc_token, 'paper', interval_hours=1)
    schedule_doc_content(doc_token, 'tag', interval_hours=1)
    
    # 3. 启动prompt定时生成（依赖token和文档内容）
    schedule_rating_prompt(resume_content, paper_urls, interval_hours=1)
    
    logging.info("飞书服务定时任务已启动，依赖关系：token→文档内容→prompt")