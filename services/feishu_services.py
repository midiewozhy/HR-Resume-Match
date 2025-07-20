import requests
import lark_oapi as lark
from lark_oapi.api.docs.v1 import *
import time
import json
import hashlib
import logging
from threading import Lock
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# 初始化调度器
scheduler = BackgroundScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# 从resources获取相应数据

# 缓存与锁机制
_token_cache = None
_content_cache = {
    "_pre_content_cache": "",
    "_paper_content_cache": "",
    "_tag_content_cache": ""
}
# 新增哈希缓存（存储各内容的哈希值）
_content_hash_cache = {
    "_pre_content_hash": "",
    "_paper_content_hash": "",
    "_tag_content_hash": ""
}
_system_prompt_cache = [
        {"role": "system", "content": ''},
    ]
_cache_lock = Lock()



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

def calculate_content_hash(content: str) -> str:
    # 计算文档hash值
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def get_system_prompt(pre_score_content: str, tag_content: str, paper_score_content: str) -> list:

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



    return [
        {"role": "system", "content": system_prompt}
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
    content_cache_key = f"_{content_type}_content_cache"
    hash_cache_key = f"_{content_type}_content_hash"
    def _fetch_content():
        global _token_cache, _content_cache, _content_hash_cache
        with _cache_lock:
            if not _token_cache:
                logging.error("token缓存为空，无法获取文档内容")
                return
            # 直接使用缓存的token_info，无需重复调用get_access_token
            content = get_feishu_doc_content(doc_token, _token_cache["access_token"])
            content_hash = calculate_content_hash(content)
            if content:
                if content_hash != _content_hash_cache[hash_cache_key]:
                    _content_cache[content_cache_key] = content
                    _content_hash_cache[hash_cache_key] = content_hash
                    return 1
                else:
                    logging.info("文档未更新")
                    return 0
            else:
                logging.error("文档获取为空")
            logging.info("使用缓存token获取文档内容成功")
    # 定时任务配置（滞后token更新10分钟）
    scheduler.add_job(_fetch_content, 'interval', hours=interval_hours, next_run_time=datetime.now() + timedelta(minutes=10))

def start_feishu_schedule(app_id: str, app_secret: str, doc_token: str, resume_content: str, paper_urls: list):
    """启动所有定时任务（按依赖顺序初始化）"""
    global _system_prompt_cache
    # 1. 优先启动token定时更新（基础依赖）
    schedule_access_token(app_id, app_secret, interval_hours=2)
    
    # 2. 启动文档内容定时获取（依赖token）
    first_update = schedule_doc_content(doc_token, 'pre', interval_hours=2)
    second_update = schedule_doc_content(doc_token, 'paper', interval_hours=2)
    third_update = schedule_doc_content(doc_token, 'tag', interval_hours=2)

    # 3. 判断文档是否更新，如果更新则重新构建prompt，如果未更新则不执行任务
    if first_update + second_update + third_update != 0:
        _system_prompt_cache = get_system_prompt(_content_cache["_pre_content_cache"], _content_cache["_tag_content_cache"], _content_cache["_paper_content_cache"])
    
    
    logging.info("飞书服务定时任务已启动，依赖关系：token→文档内容→prompt")