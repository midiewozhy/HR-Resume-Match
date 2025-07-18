# main.py
from flask import Flask
from config import Config  # 导入config.py中的Config类

# 创建Flask应用实例
app = Flask(__name__)

# 将Config类中的配置加载到app.config中
app.config.from_object(Config)