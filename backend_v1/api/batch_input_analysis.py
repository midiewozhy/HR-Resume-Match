import csv
from flask import Blueprint, request, jsonify, logging
from services.input_services import (
    validate_batch_csv_file, 
    InvalidFileTypeError,
    FileTooLargeError,
    FileSaveError,
    )


batch_input_analysis_bp = Blueprint('batch_input_analysis', __name__, url_prefix='/api/batch')

@batch_input_analysis_bp.route('/llm/batch/input/analysis', methods=['POST'])
def llm_batch_input_analysis():
    """
    批量输入分析接口，接收CSV文件，进行批量分析。
    """
    if 'file' not in request.files:
        return jsonify({
            "status": "fail",
            "message": "程序出错啦，请联系技术同学哟~"
        }), 400 

    file = request.files['file']
    
    if file.filename == '':
        return jsonify({
            "status": "fail",
            "message": "好像没有上传文件呢，请重新选择一下吧~"
        }), 400
    
    if file and file.filename:
        try:
            file_temp_path = validate_batch_csv_file(file)
        except InvalidFileTypeError as e:
            return jsonify({"status": "fail", "message": str(e)}), 400  
        except FileTooLargeError as e:
            return jsonify({"status": "fail", "message": str(e)}), 400
        except FileSaveError as e:
            return jsonify({"status": "fail", "message": str(e)}), 500
        except Exception as e:
            logging.error(f"文件处理错误: {str(e)}")
            return jsonify({"status": "fail", "message": "上传文件时出了点小问题，请重试或联系技术同学。"}), 500
        
        try:
            pass
        except Exception as e:
            logging.error(f"批量分析失败: {str(e)}", exc_info=True)
            return jsonify({
                "status": "fail",
                "message": "批量分析时出了点小问题，请重试或联系技术同学。"
            }), 500