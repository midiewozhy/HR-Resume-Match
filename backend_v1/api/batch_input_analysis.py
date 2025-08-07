import csv
import io
from flask import Blueprint, request, jsonify, logging, make_response
from services.input_services import (
    validate_batch_csv_file, 
    read_csv,
    InvalidFileTypeError,
    FileTooLargeError,
    FileSaveError,
    CSVReadError
    )
from services.analysis_services import batch_analysis
from urllib.parse import quote

batch_input_analysis_bp = Blueprint('batch_input_analysis', __name__, url_prefix='/api')

@batch_input_analysis_bp.route('/llm/batch/input/analysis', methods=['POST'])
def llm_batch_input_analysis():
    """
    批量输入分析接口，接收CSV文件，进行批量分析。
    """
    data = []
    result = {}

    if 'batchContent' not in request.files:
        return jsonify({
            "status": "fail",
            "message": "程序出错啦，请联系技术同学哟~"
        }), 400 

    file = request.files['batchContent']
    
    if file.filename == '':
        return jsonify({
            "status": "fail",
            "message": "好像没有上传文件呢，请重新选择一下吧~"
        }), 400
    
    if file and file.filename:
        try:
            file_temp_path = validate_batch_csv_file(file)
        except InvalidFileTypeError as e:
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
            return jsonify({
                "status": "fail", 
                "message": str(e)
            }), 500
        except Exception as e:
            logging.error(f"文件处理错误: {str(e)}")
            return jsonify({
                "status": "fail", 
                "message": "上传文件时出了点小问题，请重试或联系技术同学。"
            }), 500
        
        try:
            data = read_csv(file_temp_path)
        except CSVReadError as e:
            return jsonify({
                "status": "fail",
                "message": str(e)
            }), 400
        except Exception as e:
            logging.error(f"批量分析失败: {str(e)}", exc_info=True)
            return jsonify({
                "status": "fail",
                "message": "批量分析时出了点小问题，请重试或联系技术同学。"
            }), 500
        
    try:
        result = batch_analysis(data)
        # 检查分析结果是否有效
        if not result or not isinstance(result, dict):
            return jsonify({
                "status": "fail",
                "message": "分析结果为空或格式不正确，请重试。"
            }), 500
        
        # 准备CSV输出
        output = io.StringIO()
        # 定义CSV表头
        fieldnames = [
            'index', 'link', 'score', 'summary', 
            'tag_primary', 'contact_tag_primary',
            'tag_secondary', 'contact_tag_secondary'
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        # 写入分析结果
        for idx, item in result.items():
            # 确保每个条目都包含所有必要的字段
            row = {
                'index': idx,
                'link': item.get('link', ''),
                'score': item.get('score', ''),
                'summary': item.get('summary', ''),
                'tag_primary': item.get('tag_primary', ''),
                'contact_tag_primary': item.get('contact_tag_primary', ''),
                'tag_secondary': item.get('tag_secondary', ''),
                'contact_tag_secondary': item.get('contact_tag_secondary', '')
            }
            writer.writerow(row)
        
        # 创建响应
        response = make_response(output.getvalue())
        
        # 处理文件名
        filename = "analysis_results.csv"
        encoded_filename = quote(filename)

        # 设置响应头，指定为CSV文件并提示下载
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
        response.headers["Content-type"] = "text/csv; charset=utf-8"
        
        return response
        
    except Exception as e:
        logging.error(f"生成分析结果时出错: {str(e)}", exc_info=True)
        return jsonify({
            "status": "fail",
            "message": "生成分析结果时出了点小问题，请重试或联系技术同学。"
        }), 500