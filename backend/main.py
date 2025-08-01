from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_session import Session
from config import Config
from services.feishu_services import start_feishu_schedule
from multiprocessing import Process
import atexit
import os

# 获取项目根目录路径
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, '../frontend')  # 前端目录路径

# 创建Flask应用实例
app = Flask(__name__, static_folder=FRONTEND_DIR)

# 配置应用
app.config.from_object(Config)

# 初始化Session
#Session(app)  # 初始化服务器端session存储

# 启用CORS支持
CORS(app, 
     origins=["http://127.0.0.1:5501"],  # 仅保留实际使用的域名
     supports_credentials=True,  # 允许携带凭证
     methods=['GET', 'POST', 'OPTIONS'],
     expose_headers=['Set-Cookie'],  # 允许前端访问Set-Cookie头
     allow_headers=['Set-Cookie', 'Content-Type']
)

# 导入蓝图
from api.resources import resources_bp

# 注册蓝图
app.register_blueprint(resources_bp)

# 添加服务前端文件的路由
@app.route('/')
def serve_frontend():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(FRONTEND_DIR, path)

def start_feishu_process():
    start_feishu_schedule()

if __name__ == '__main__':
    # 创建一个新的进程来运行飞书服务调度
    feishu_process = Process(target=start_feishu_process)
    feishu_process.daemon = False  # 设置为非守护进程
    feishu_process.start()

    # 注册一个退出处理函数，在主程序退出时不终止飞书服务进程
    def cleanup():
        pass
    atexit.register(cleanup)

    # 确保前端目录存在
    if not os.path.exists(FRONTEND_DIR):
        os.makedirs(FRONTEND_DIR)
        print(f"创建前端目录: {FRONTEND_DIR}")

    app.run(debug=True, port=5000)