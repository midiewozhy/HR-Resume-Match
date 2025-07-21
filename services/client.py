from openai import OpenAI
from config import Config

client = OpenAI(
    base_url = "https://ark.cn-beijing.volces.com/api/v3/bots",
    api_key = Config.API_KEY
)