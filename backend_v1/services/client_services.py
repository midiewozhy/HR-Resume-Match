from openai import OpenAI
from config import Config
from volcenginesdkarkruntime import Ark
import lark_oapi as lark


llm_client = OpenAI(
    base_url = "https://ark.cn-beijing.volces.com/api/v3/bots",
    api_key = Config.API_KEY
)

embedding_client = Ark(
    api_key=Config.API_KEY,
)

dowei_client = (lark.Client.builder() 
        .app_id(Config.APP_ID) 
        .app_secret(Config.APP_SECRET) 
        .log_level(lark.LogLevel.DEBUG) 
        .build())

doc_client = (
        lark.Client.builder()
        .enable_set_token(True)
        .log_level(lark.LogLevel.DEBUG)
        .build()
    )