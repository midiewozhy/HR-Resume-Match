from openai import OpenAI
from config import Config
import lark_oapi as lark

llm_client = OpenAI(
    base_url = "https://ark.cn-beijing.volces.com/api/v3/bots",
    api_key = Config.API_KEY
)

feishu_client = (
    lark.Client.builder()
    .enable_set_token(True)
    .log_level(lark.LogLevel.DEBUG)
    .build()
)