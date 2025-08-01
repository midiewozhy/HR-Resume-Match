import json
import time
import requests
import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *
from lark_oapi.api.docs.v1 import *
from config import Config

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

def construct_system_prompt():

    access_token = get_access_token(Config.APP_ID, Config.APP_SECRET)['access_token']
    paper_score_content = get_feishu_doc_content(Config.PAPER_SCORE_TOKEN, access_token)
    pre_score_content = get_feishu_doc_content(Config.PRE_SCORE_TOKEN, access_token)
    tag_content = get_feishu_doc_content(Config.TAG_DOC_TOKEN, access_token)
    
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
    - 有岗位时完整输出示例：
    {{
        "cdd_score": 3.5,
        "job_match_1": LLM-Posttrain ,
        "job_match_1_contact": 严林,
        "reason_1": 候选人主要研究方向涉及后训练优化与数据精炼,
        "job_match_2": 前沿研究（Edge）-持续学习（continual learning）,
        "job_match_2_contact": 蔡天乐,
        "reason_2": 候选人有些文章涉及“可塑性-稳定性”平衡与表示分解
    }}
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