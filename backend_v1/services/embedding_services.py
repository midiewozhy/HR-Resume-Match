import json

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *

import torch
from volcenginesdkarkruntime import Ark
from typing import Optional, List

embedding_client = Ark(
    api_key="86ab5469-0305-46df-9587-1c6d8a4d2661",
)

dowei_client = (lark.Client.builder() 
        .app_id("cli_a8c24cc4de61d00c") 
        .app_secret("I1iUQBmAbdlD1DtLvoh88m2EqP4G2fMH") 
        .log_level(lark.LogLevel.DEBUG) 
        .build())

def get_dowei_record(client, page_token):
    request: SearchAppTableRecordRequest = (SearchAppTableRecordRequest.builder() 
            .app_token("XD18bQYhraIp6fsNnu3cItRxnId") 
            .table_id("tblaUW9BFzuZ19Gh") 
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

def embedding_update(dowei_client ,record_list: list, data_list: list):

    # 构造请求对象
    request: BatchUpdateAppTableRecordRequest = (BatchUpdateAppTableRecordRequest.builder() 
        .app_token("XD18bQYhraIp6fsNnu3cItRxnId") 
        .table_id("tblaUW9BFzuZ19Gh") 
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
    response: BatchUpdateAppTableRecordResponse = dowei_client.bitable.v1.app_table_record.batch_update(request)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app_table_record.batch_update failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))

def feishu_dowei_embedding(dowei_client, embedding_client):
    # 创建client
    
    page_token = ''
    has_more = True
    middle_list = []
    final_list = []
    record_list = []

    while has_more:
        # 构造请求对象
        has_more, data_need, page_token = get_dowei_record(dowei_client, page_token)
        middle_list += data_need

    # 清洗数据结构，保存record_id
    for chunk in middle_list:
        txt = ''.join(piece_data['text'] for piece_data in chunk['fields']['岗位介绍'])
        record = chunk['record_id']
        final_list.append(txt)
        record_list.append(record)

    # 进行语义编码
    embedding_data = encode(embedding_client,final_list)
    embedding_list = [item.tolist() for item in embedding_data]
    embedding_update(dowei_client, record_list, embedding_list)