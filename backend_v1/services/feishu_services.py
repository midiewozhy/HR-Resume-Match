import json
import time
import requests
import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *
from lark_oapi.api.docs.v1 import *
from config import Config
import threading
from functools import wraps
from services.client_services import doc_client
from services.general_services import calculate_content_hash as hash

# 合并缓存结构，用键值对统一管理
_cache = {
    # 内容缓存
    "content": {
        "pre": "",
        "paper": "",
        "tag": ""
    },
    # 哈希缓存
    "hash": {
        "pre": hash(""),  # 初始化空内容的hash
        "paper": hash(""),
        "tag": hash("")
    }
}

_cache_lock = threading.Lock()

def thread_safe(func):
    """线程安全装饰器，确保缓存更新时的原子性"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        with _cache_lock:
            return func(*args, **kwargs)
    return wrapper

@thread_safe
def get_cached_content():
    """获取缓存的文档内容副本"""
    return {k: v for k, v in _cache["content"].items()}

def fetch_feishu_docs():
    """单次获取所有飞书文档内容并更新缓存"""
    try:
        # 获取访问令牌
        token_info = get_access_token(Config.APP_ID, Config.APP_SECRET)
        if not token_info:
            raise Exception("获取access_token失败")
        access_token = token_info["access_token"]
        
        # 批量获取文档内容
        contents = {
            "pre": get_feishu_doc_content(doc_client, Config.PRE_SCORE_TOKEN, access_token),
            "paper": get_feishu_doc_content(doc_client, Config.PAPER_SCORE_TOKEN, access_token),
            "tag": get_feishu_doc_content(doc_client, Config.TAG_DOC_TOKEN, access_token)
        }

        # 计算新哈希并对比
        new_hashes = {k: hash(v) for k, v in contents.items()}
        has_changes = any(new_hashes[k] != _cache["hash"][k] for k in new_hashes)

        if has_changes:
            # 原子更新缓存（哈希和内容）
            with _cache_lock:
                _cache["hash"].update(new_hashes)
                _cache["content"].update(contents)
            lark.logger.info("飞书文档内容缓存更新成功")
        else:
            lark.logger.info("飞书文档内容无变化，无需更新缓存")

        return True
    except Exception as e:
        lark.logger.error(f"飞书文档获取失败: {str(e)}", exc_info=True)
        return False
    
def feishu_scheduler(interval=21600): 
    """后台定时任务：循环获取文档并休眠指定时间"""
    # 启动时先执行一次
    fetch_feishu_docs()
    
    while True:
        try:
            # 休眠指定时间（单位：秒）
            time.sleep(interval)
            # 执行更新
            fetch_feishu_docs()
        except Exception as e:
            lark.logger.error(f"定时任务异常: {str(e)}", exc_info=True)
            # 异常后短暂休眠再重试，避免频繁报错
            time.sleep(60)

def start_feishu_thread(interval=21600):
    """启动飞书文档获取线程"""
    # 创建后台线程（daemon=True：主程序退出时自动结束线程）
    feishu_thread = threading.Thread(
        target=feishu_scheduler,
        args=(interval,),
        daemon=True
    )
    feishu_thread.start()
    lark.logger.info(f"飞书文档定时获取线程已启动，更新间隔 {interval} 秒")
    return feishu_thread

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


def get_feishu_doc_content(client, doc_token: str, access_token: str) -> str:
    """获取飞书文档内容

    Args:
        doc_token (str): 文档的 token
        access_token (str): 访问令牌

    Returns:
        str: 文档内容
    """

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

def construct_single_system_prompt():

    cached_content = get_cached_content()
    pre_score_content = cached_content["pre"]
    paper_score_content = cached_content["paper"]
    tag_content = cached_content["tag"]

    system_prompt = f"""
    你是一个专业的评阅人。......严格按以下逻辑执行任务，并最终输出指定的JSON格式。

    处理逻辑：
    1. 

    2. 

    输出要求：
    - 

    关键规则：
    - 
    """
    return [
        {"role": "system", "content": system_prompt}
    ]

def get_batch_system_prompt():
    
    cached_content = get_cached_content()
    paper_score_content = cached_content["paper"]
    tag_content = cached_content["tag"]

    system_prompt = f"""
    你是一个专业的评阅人。......严格按以下逻辑执行任务，并最终输出指定的JSON格式。

    处理逻辑：
    1. 

    2. 

    输出要求：
    - 

    关键规则：
    - 
    """

    return [{"role": "system", "content": system_prompt}]
