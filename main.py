# main.py
from flask import Flask
from config import Config
from services.feishu_services import start_feishu_schedule
from multiprocessing import Process
import atexit

# 创建Flask应用实例
app = Flask(__name__)

# 将Config类中的配置加载到app.config中
app.config.from_object(Config)

# 导入蓝图
from api.resources import resources_bp
from api.output import output_bp

# 注册蓝图
app.register_blueprint(resources_bp)
app.register_blueprint(output_bp)

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

    app.run(debug=True)