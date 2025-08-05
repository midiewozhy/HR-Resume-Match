from flask import Blueprint, request, jsonify, logging
from services.input_services import (
    validate_resume_pdf_file,
    read_pdf,
    validate_paper_url,
    InvalidFileTypeError,  # Service层定义的自定义异常
    FileTooLargeError,
    FileSaveError,
    PDFReadError,
    InvalidURLError,
    URLUnreachableError,
)
from services.analysis_services import analyze_candidate, LLMContentEmptyError, APIEmptyError
from services.output_services import clean_output
import logging
import os


single_analysis_bp = Blueprint('resources', __name__, url_prefix='/api')


@single_analysis_bp.route('/llm/single/cdd/analysis', methods=['POST'])
def llm_cdd_analysis() -> tuple[dict,int]:
    """
    这是HR上传简历的接口函数，如果文件接收成功，会返回成功信息；若失败，则会返回错误类型。
    """
    # 初始化一些数据，防止为空
    pdf_content = ""
    url = ""
    analysis_result = ""

    # 1. 检查前端代码是否有误
    if 'pdfContent' not in request.files or 'paperUrl' not in request.form:
        return jsonify({
            "status": "fail",
            "message": "程序出错啦，请联系技术同学哟~"
        }), 400 
    
    file = request.files.get('pdfContent', None)
    url = request.form.get('paperUrl', '')
    
    # 2. 检查是否真的选了文件（避免“空上传”）
    if file.filename == '' and not url:
        return jsonify({
            "status": "fail",
            "message": "好像没有上传文件呢，请重新选择一下吧~"
        }), 400
    

    # 3. 调用Service层进行文件的基础校验（包括文件类型、大小等）
    if file and file.filename:
        try:
            file_temp_path = validate_resume_pdf_file(file)
        except InvalidFileTypeError:
            return jsonify({
                "status": "fail",
                "message": str(e)
            }), 400
        except FileTooLargeError as e:
            return jsonify({
                "status": "fail",
                "message": str(e)
            }), 400
        except FileSaveError as e:
            logging.error(str(e), exc_info=True)
            return jsonify({
                "status": "fail",
                "message": f"{str(e)}，请重试一下吧~ 若多次失败可以联系技术同学哦~"
            }), 500
        except Exception as e:
            logging.error(f"PDF上传失败: {str(e)}", exc_info=True)
            return jsonify({
                "status": "fail",
                "message": str(e)
            }), 500
    
        # 4. 进行pdf文件的内容提取
        try:
            # 5. 调用read_pdf函数读取内容
            pdf_content = read_pdf(file_temp_path)
            # 6. 提取成功，保存内容并返回内容
            os.remove(file_temp_path)  # 解析完就删，避免占用磁盘
        except PDFReadError as e:
            # 解析失败也删除临时文件，避免残留
            if os.path.exists(file_temp_path):
                os.remove(file_temp_path)
            return jsonify({
                "status": "fail",
                "message": str(e)
            }), 400
        except Exception as e:
            if os.path.exists(file_temp_path):
                os.remove(file_temp_path)
            logging.error(f"PDF提取失败: {str(e)}", exc_info=True)
            return jsonify({
                "status": "fail",
                "message": "提取内容时出了点小问题，请重试~"
            }), 500
        
    if url:
        # 7. 进行论文链接的校验
        try:
            validate_paper_url(url)
        except InvalidURLError as e:
            return jsonify({
                "status": "fail",
                "message": str(e)
            }), 400
        except URLUnreachableError as e:
            return jsonify({
                "status": "fail",
                "message": str(e)
            }), 400
        except Exception as e:
            logging.error(f"论文链接验证失败: {str(e)}", exc_info=True)
            return jsonify({
                "status": "fail",
                "message": "链接验证时出了点小问题，请重试~"
            }), 500

    # 8. 进行分析
    try:
        analysis_result = analyze_candidate(pdf_content, url)
        if not analysis_result:
            raise LLMContentEmptyError("大模型返回的内容为空，请稍后再试~")
        #result = clean_output(analysis_result)  # 清理输出格式
        return jsonify({
            "status": "success",
            "message": "简历分析成功！",
            "data": analysis_result,
        }), 200
    except LLMContentEmptyError as e:
        logging.error(f"大模型分析失败: {str(e)}", exc_info=True)
        return jsonify({
            "status": "fail",
            "message": str(e)
        }), 500
    except APIEmptyError as e:
        logging.error(f"API返回内容为空: {str(e)}", exc_info=True)
        return jsonify({
            "status": "fail",
            "message": str(e)
        }), 503
    except Exception as e:
        logging.error(f"大模型分析时发生错误: {str(e)}", exc_info=True)
        return jsonify({
            "status": "fail",
            "message": "分析过程中发生错误，请稍后再试~"
        }), 500