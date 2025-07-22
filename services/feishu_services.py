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
from config import Config

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
_system_prompt_cache = [{"role": "system", "content": ""}]
_cache_lock = Lock()

# 新增：文档更新标记（记录哪些文档需要更新prompt）
_docs_need_update = set()  # 存储需要更新prompt的文档类型
_update_doc_lock = Lock()  # 保护_doc_need_update更新的锁
_update_prompt_lock = Lock() # 保护prompt更新的锁


def wait_for_cache_ready(timeout_seconds: int = 10) -> bool:
    """等待核心文档缓存就绪"""
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        with _cache_lock:
            if _content_cache["_pre_content_cache"] and _content_cache["_tag_content_cache"] and _content_cache["_paper_content_cache"]:
                with _update_doc_lock:
                    _docs_need_update.update(("pre","tag","paper"))
                logging.info("核心文档缓存已就绪")
                return True
        time.sleep(0.5)  # 避免CPU占用过高
    logging.warning(f"等待{timeout_seconds}秒后，核心文档缓存仍未就绪")
    return False

def get_access_token():
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
    payload = {"app_id": Config.APP_ID, "app_secret": Config.APP_SECRET}

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
    # 构造飞书client
    feishu_client = (
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
    response: GetContentResponse = feishu_client.docs.v1.content.get(request, option)

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
    你是专业人才分析专家，需严格执行以下流程：  

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


def update_system_prompt():
    """统一更新system prompt（合并多次文档更新的结果）"""
    global _system_prompt_cache, _docs_need_update
    
    # 检查是否真的需要更新（避免重复执行）
    with _update_doc_lock:
        if not _docs_need_update:
            logging.info("没有需要更新的文档，跳过prompt重建")
            return
        
    logging.info(f"开始重建system prompt，触发源：{_docs_need_update}")

    # 检查文档内容是否为空（避免首次更新失败）
    with _cache_lock:
        if not all([_content_cache["_pre_content_cache"], _content_cache["_tag_content_cache"], _content_cache["_paper_content_cache"]]):
            logging.warning("部分文档内容为空，跳过prompt重建（可能是首次获取失败）")
            return
    
    # 重建prompt
    with _update_prompt_lock:
        _system_prompt_cache = get_system_prompt(
            _content_cache["_pre_content_cache"],
            _content_cache["_tag_content_cache"],
            _content_cache["_paper_content_cache"]
        )
    logging.info(f"重建的prompt如下：{_system_prompt_cache}")
    
    # 重置更新标记
    with _update_doc_lock:
        _docs_need_update.clear()
    logging.info("system prompt重建完成")


def schedule_access_token(interval_hours: int):
    def _update_token():
        global _token_cache
        with _cache_lock:
            token_info = get_access_token()
            if token_info:
                _token_cache = token_info  # 更新缓存
                logging.info(f"token缓存更新，有效期至{token_info['timestamp'] + token_info['expire']}")
    # 定时任务配置（同上）
    scheduler.add_job(_update_token, 'interval', hours=interval_hours, next_run_time=datetime.now(), id = "update_token", replace_existing=True)

def schedule_doc_content(doc_token: str, content_type: str, interval_hours: int):
    """调度文档内容更新任务（优化：仅标记更新，延迟合并更新prompt）"""
    content_cache_key = f"_{content_type}_content_cache"
    hash_cache_key = f"_{content_type}_content_hash"
    
    def _fetch_content():
        global _token_cache, _content_cache, _content_hash_cache, _docs_need_update
        with _cache_lock:
            if not _token_cache:
                logging.error("token缓存为空，无法获取文档内容")
                return
                
            try:
                # 获取文档内容并检查更新
                content = get_feishu_doc_content(doc_token, _token_cache["access_token"])
                content_hash = calculate_content_hash(content)
                
                if content and content_hash != _content_hash_cache[hash_cache_key]:
                    # 更新文档缓存
                    _content_cache[content_cache_key] = content
                    _content_hash_cache[hash_cache_key] = content_hash
                    logging.info(f"{content_type}文档内容已更新，标记需要更新prompt")
                    
                    # 标记该文档需要更新prompt
                    with _update_doc_lock:
                        _docs_need_update.add(content_type)
                    
                else:
                    logging.info(f"{content_type}文档未更新")
            except Exception as e:
                logging.error(f"{content_type}文档更新失败：{e}")
    
    scheduler.add_job(_fetch_content, 'interval', hours=interval_hours, next_run_time=datetime.now() + timedelta(minutes=1), id=f"fetch_content_{content_type}", replace_existing=True)

def schedule_prompt_update(interval_hours: int):
    scheduler.add_job(update_system_prompt, 'interval', hours = interval_hours, next_run_time=datetime.now() + timedelta(minutes=2), id = "update_prompt", replace_existing=True)

def start_feishu_schedule():
    """启动所有任务（含首次触发），优化首次同步逻辑"""
    # 初始化日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    # 1. 启动token更新（立即执行）
    schedule_access_token(interval_hours=2)
    
    # 等待token初始化（增加重试机制）
    token_ready = False
    for attempt in range(3):  # 最多重试3次
        time.sleep(1)  # 等待1秒
        with _cache_lock:
            if _token_cache:
                token_ready = True
                logging.info("Token缓存已就绪")
                break
        logging.warning(f"尝试 {attempt+1}/3: Token缓存未就绪")
    
    if not token_ready:
        logging.error("Token初始化失败，无法继续启动服务")
        return
    
    # 2. 启动文档更新（1分钟后首次自动执行）
    schedule_doc_content(Config.PRE_SCORE_TOKEN, 'pre', interval_hours=2)
    schedule_doc_content(Config.PAPER_SCORE_TOKEN, 'paper', interval_hours=2)
    schedule_doc_content(Config.TAG_DOC_TOKEN, 'tag', interval_hours=2)
    
    # 3. 启动prompt更新（2分钟后首次自动执行）
    schedule_prompt_update(interval_hours=0.5)
    
    # 4. 首次手动触发：确保文档和prompt初始化成功
    logging.info("开始首次手动触发文档获取...")
    
    # 手动触发文档任务并记录结果
    logging.info("开始首次手动触发文档获取...")
    doc_types = ["pre", "paper", "tag"]
    for doc_type in doc_types:
        job_id = f"fetch_content_{doc_type}"
        job = scheduler.get_job(job_id)
        if job:
            try:
                job.func()
                logging.info(f"手动触发{doc_type}文档获取成功")
            except Exception as e:
                logging.error(f"手动触发{doc_type}文档获取失败：{e}")
        else:
            logging.warning(f"未找到{doc_type}文档更新任务")
    
    
    # 5. 等待核心文档缓存就绪
    cache_ready = wait_for_cache_ready(timeout_seconds=15)
    
    # 6. 手动触发首次prompt更新（仅当缓存就绪时）
    if cache_ready:
        logging.info("开始首次手动触发prompt更新...")
        update_system_prompt()
        # 检查prompt是否成功更新
        with _update_prompt_lock:
            if _system_prompt_cache and _system_prompt_cache[0]["content"].strip():
                logging.info("首次prompt构建成功")
            else:
                logging.warning("首次prompt构建失败，内容为空")
    else:
        logging.warning("核心文档缓存未就绪，跳过首次prompt构建，等待定时任务更新")
    
    logging.info("飞书服务启动完成，调度任务已运行")