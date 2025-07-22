from openai import OpenAI
from config import Config

llm_client = OpenAI(
    base_url = "https://ark.cn-beijing.volces.com/api/v3/bots",
    api_key = Config.API_KEY
)