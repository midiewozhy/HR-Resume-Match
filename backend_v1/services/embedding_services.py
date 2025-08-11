import json
import time

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *

import torch
from typing import Optional, List
import threading

from config import Config

from services.general_services import calculate_content_hash as hash

_jd_hash_cache = dict()


def get_dowei_record(client, page_token):
    request: SearchAppTableRecordRequest = (SearchAppTableRecordRequest.builder() 
            .app_token(Config.CHUNK_APP_TOKEN) 
            .table_id(Config.CHUNK_TABLE_ID) 
            .user_id_type("open_id") 
            .page_token(page_token) 
            .page_size(10) 
            .request_body(SearchAppTableRecordRequestBody.builder().view_id("vewVpwpAVp").field_names(["岗位介绍"]).build())
            .build())

    # 发起请求
    response: SearchAppTableRecordResponse = client.bitable.v1.app_table_record.search(request)    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app_table_record.search failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
        return

    # 处理业务结果，更新业务状态
    data = lark.JSON.marshal(response.data, indent=4)
    data_dict = json.loads(data)
    has_more = data_dict['has_more']
    page_token = data_dict['page_token'] if 'page_token' in data_dict.keys() else ''
    data_need = data_dict['items']
    return has_more, data_need, page_token

def encode(
    client, inputs: List[str], is_query: bool = False, mrl_dim: Optional[int] = None
):
    if is_query:
        # use instruction for optimal performance, feel free to tune this instruction for different tasks
        # to reproduce MTEB results, refer to https://github.com/embeddings-benchmark/mteb/blob/main/mteb/models/seed_models.py for detailed instructions per task)
        inputs = [
            f"Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: {i}".format(
                i
            )
            for i in inputs
        ]
    resp = client.embeddings.create(
        model="doubao-embedding-large-text-250515",
        input=inputs,
        encoding_format="float",
    )
    embedding = torch.tensor([d.embedding for d in resp.data], dtype=torch.bfloat16)
    if mrl_dim is not None:
        assert mrl_dim in [2048, 1024, 512, 256]
        embedding = embedding[:, :mrl_dim]
    # normalize to compute cosine sim
    embedding = torch.nn.functional.normalize(embedding, dim=1, p=2).float().numpy()
    return embedding

def embedding_update(client ,record_list: list, data_list: list):

    # 构造请求对象
    request: BatchUpdateAppTableRecordRequest = (BatchUpdateAppTableRecordRequest.builder() 
        .app_token(Config.CHUNK_APP_TOKEN) 
        .table_id(Config.CHUNK_TABLE_ID) 
        .user_id_type("open_id") 
        .ignore_consistency_check(True) 
        .request_body(BatchUpdateAppTableRecordRequestBody.builder()
            .records([AppTableRecord.builder()
                .fields({"向量":json.dumps(data_list[i])})
                .record_id(record_list[i])
                .build()
                for i in range(len(data_list))])
            .build()) 
        .build())

    # 发起请求
    response: BatchUpdateAppTableRecordResponse = client.bitable.v1.app_table_record.batch_update(request)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app_table_record.batch_update failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))

def feishu_dowei_embedding(dowei_client, embedding_client):

    # 初始化数据
    page_token = ''
    has_more = True
    middle_list = []
    _record_recalculate = []
    _txt_update = []

    while has_more:
        # 构造请求对象
        has_more, data_need, page_token = get_dowei_record(dowei_client, page_token)
        middle_list += data_need

    # 清洗数据结构，保存record_id
    for chunk in middle_list:
        txt = ''.join(piece_data['text'] for piece_data in chunk['fields']['岗位介绍'])
        record = chunk['record_id']
        _hash_cache = hash(txt)
        if record in _jd_hash_cache.keys():
            if _jd_hash_cache[record] != _hash_cache:
                _jd_hash_cache[record] = _hash_cache
                _record_recalculate.append(record)
                _txt_update.append(txt)
        else:
            _jd_hash_cache[record] = _hash_cache
            _record_recalculate.append(record)
            _txt_update.append(txt)


    # 进行语义编码
    embedding_data = encode(embedding_client, _txt_update)
    embedding_list = [item.tolist() for item in embedding_data]
    embedding_update(dowei_client, _record_recalculate, embedding_list)

def embedding_scheduler(dowei_client,embedding_client,interval=21600): 
    """后台定时任务：循环获取文档并休眠指定时间"""
    # 启动时先执行一次
    feishu_dowei_embedding(dowei_client, embedding_client)
    
    while True:
        try:
            # 休眠指定时间（单位：秒）
            time.sleep(interval)
            # 执行更新
            feishu_dowei_embedding(dowei_client, embedding_client)
        except Exception as e:
            lark.logger.error(f"定时任务异常: {str(e)}", exc_info=True)
            # 异常后短暂休眠再重试，避免频繁报错
            time.sleep(60)

def start_embedding_thread(dowei_client,embedding_client,interval=21600):
    """启动飞书文档获取线程"""
    # 创建后台线程（daemon=True：主程序退出时自动结束线程）
    feishu_thread = threading.Thread(
        target=embedding_scheduler,
        args=(dowei_client,embedding_client,interval),
        daemon=True
    )
    feishu_thread.start()
    lark.logger.info(f"飞书文档定时获取线程已启动，更新间隔 {interval} 秒")
    return feishu_thread