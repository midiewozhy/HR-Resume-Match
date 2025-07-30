from flask import Blueprint, request, jsonify, session
from werkzeug.utils import secure_filename
from services.resources_services import (
    save_temp_file, 
    read_pdf,
    validate_paper_url,
    InvalidFileTypeError,  # Service层定义的自定义异常
    FileTooLargeError,
    FileSaveError,
    PDFReadError,
    InvalidURLError,
    URLUnreachableError,
)
import logging
import os
from services.general_services import get_session_id
from services.user_data_manager import UserDataManager
import uuid
import tempfile

# 创建数据储存类
user_data_manager = UserDataManager()

resources_bp = Blueprint('resources', __name__, url_prefix='/api/resources')


@resources_bp.route('/upload/pdf', methods=['POST'])
def upload_pdf() -> tuple[dict,int]:
    """
    这是HR上传简历的接口函数，如果文件接收成功，会返回成功信息；若失败，则会返回错误类型。
    """

    # 1. 检查前端代码是否有误
    if 'file' not in request.files:
        return jsonify({
            "status": "fail",
            "message": "程序出错啦，请联系技术同学哟~"  # 明确引导操作
        }), 400  # 后台仍需正确状态码，前端可基于此做交互（如高亮上传按钮）
    
    file = request.files['file']
    
    # 2. 检查是否真的选了文件（避免“空上传”）
    if file.filename == '':
        return jsonify({
            "status": "fail",
            "message": "好像没选到文件呢，请重新选择一下吧~"
        }), 400
    
    # 3. 安全处理文件名（防止技术漏洞，不影响用户体验）
    secure_name = secure_filename(file.filename)
    
    try:
        # 4. 保存临时文件（调用Service层）
        temp_path = save_temp_file(file)
        
        # 5. 上传成功，返回友好提示
        return jsonify({
            "status": "success",
            "message": f"简历《{secure_name}》上传成功啦！正在准备解析...",  # 包含文件名，增强确认感
            "file_temp_path": temp_path  # 后台用的临时路径，不展示给HR
        }), 200
    
    # 捕获“文件类型错误”
    except InvalidFileTypeError:
        return jsonify({
            "status": "fail",
            "message": "请上传PDF格式的文件哦，当前文件不是PDF呢~"  # 明确指出问题+解决方案
        }), 400
    
    # 捕获“文件过大”
    except FileTooLargeError as e:
        # 假设Service层的错误信息包含最大限制，如“超过10MB”
        return jsonify({
            "status": "fail",
            "message": f"文件有点大哦，{str(e)}~ 可以试试压缩后再上传~"  # 提供解决方案
        }), 400
    
    # 捕获“临时文件保存错误”
    except FileSaveError as e:
        logging.error(str(e), exc_info=True)
        # 这里不暴露技术细节，给出安抚信息
        return jsonify({
            "status": "fail",
            "message": f"上传后验证文件出错啦，请重试一下吧~ 若多次失败可以联系技术同学哦~"  # 包含错误详情，便于排查
        }), 500
    
    # 捕获其他未知错误
    except Exception as e:
        # 未知错误时，避免技术细节，给安抚信息
        logging.error(f"PDF上传失败: {str(e)}", exc_info=True)
        return jsonify({
            "status": "fail",
            "message": "上传时出了点小问题，请重试一下吧~ 若多次失败可以联系技术同学哦~"
        }), 500

@resources_bp.route('/extract', methods=['POST'])
def extract_pdf_content():
    """
    从已经上传的pdf文件中提取文本内容的接口
    """

    # 1. 获取唯一session_id以作为数据存储的查询一句
    session_id = get_session_id()
    #logging.info(f"开始提取简历内容 | session_id: {session_id}")
    user_data_manager.initialize_user_data(session_id)
    #print("Session data:", dict(session))  # 查看session内容
    #print("Request cookies:", request.cookies)  # 查看传入cookies

    # 2. 获取请求中的JSON数据
    data = request.get_json()
    # 判断data是否为空或者是否储存了temp_path参数
    if not data or 'file_temp_path' not in data:
        return jsonify({
            "status": "fail",
            "message": "上传好像出了点问题，请重新上传试试呢？"
        }), 400
    
    # data非空且存在temp_path键时，获取对应内容
    temp_path = data.get('file_temp_path')

    # 3. 验证文件是否存在
    if not os.path.exists(temp_path):
        return jsonify({
            "status": "fail",
            "message": "文件似乎不存在了呢，能再上传一次吗？"
        }), 404

    try:
        # 4. 调用read_pdf函数读取内容
        pdf_content = read_pdf(temp_path)

        # 5. 提取成功，保存内容并返回内容
        os.remove(temp_path)  # 解析完就删，避免占用磁盘
        user_data_manager.set_user_data(session_id,{"resume": pdf_content})

        return jsonify({
            "status": "success",
            "message": f"简历解析成功，我们现在开始提取链接咯~...",
            "resume_content": pdf_content  # 提取到的文本内容，供后续大模型调用
        }), 200
    
    # 处理read_pdf抛出的异常
    except PDFReadError as e:
        # 解析失败也删除临时文件，避免残留
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({
            "status": "fail",
            "message": str(e)
        }), 400
    
     # 6. 处理其他未知错误
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        logging.error(f"PDF提取失败: {str(e)}", exc_info=True)
        return jsonify({
            "status": "fail",
            "message": "提取内容时出了点小问题，请重试~"
        }), 500
    
@resources_bp.route('/upload/paper_url', methods = ['POST'])
def upload_paper_url():
    """
    可选任务：处理HR上传的论文链接
    """
    # 1. 获取唯一session_id以作为数据存储的查询一句
    session_id = get_session_id()

    # 1. 获取请求中的接送数据
    data = request.get_json()

    # 2. 基础校验：data是否为空
    if not data:
        return jsonify({
            "status": "fail",
            "message": "似乎没有上传信息呢，请上传后重试吧~"
        }), 400
    
    # 3. 获取url
    url_fields = ['paper_url_1','paper_url_2']
    paper_urls = [data.get(field) for field in url_fields if data.get(field)]
    
    # 4. 若未提供任何URL，返回提示

    if not paper_urls:
        user_data_manager.set_user_data(session_id, {"paper_urls": []})
        return jsonify({
            "status": "info",
            "message": "未检测到论文URL呢~ 我们会仅基于简历进行分析匹配~",
            "paper_urls": []
        }), 204  # 204表示无内容，但请求成功
    
    # 5. 验证每个url的有效性
    valid_urls = []
    error_messages = []
    for idx, url in enumerate(paper_urls, 1):
        try:
            validate_paper_url(url)  # 调用Service层验证函数
            # 简化URL显示（超长截断）
            valid_urls.append(url)
        except InvalidURLError as e:
            error_messages.append(f"第{idx}个{str(e)}")
        except URLUnreachableError as e:
            error_messages.append(f"第{idx}个{str(e)}")
        except Exception as e:
            logging.error(f"第{idx}个论文URL处理失败: {str(e)}")
            error_messages.append(f"第{idx}个链接处理时出了点小问题，请重试~")

    # 6. 处理验证结果
    if error_messages:
        # 保存数据
        user_data_manager.set_user_data(session_id,{"paper_urls": valid_urls})        
        # 存在无效URL时，返回错误信息（保留有效URL，便于用户修正）
        return jsonify({
            "status": "fail",
            "message": "；".join(error_messages),
            "paper_urls": valid_urls  # 返回有效的URL
        }), 400
    else:
        # 所有URL均有效
        user_data_manager.set_user_data(session_id,{"paper_urls": valid_urls})
        
        count = len(valid_urls)
        return jsonify({
            "status": "success",
            "message": f"{count}个论文链接已收到，并且处理成功啦！{session_id}",
            "paper_urls": valid_urls # 供后续调用的URL列表
        }), 200