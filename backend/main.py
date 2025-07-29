from flask import Flask, send_from_directory
from flask_cors import CORS
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
# 启用CORS支持
CORS(app, origins=["http://localhost:5501", "http://1207.0.0.1:5501"], methods=['GET','POST']) # 允许前端访问的域名

# 将Config类中的配置加载到app.config中
app.config.from_object(Config)

# 导入蓝图
from api.resources import resources_bp
from api.output import output_bp

# 注册蓝图
app.register_blueprint(resources_bp)
app.register_blueprint(output_bp)

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