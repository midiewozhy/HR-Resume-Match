from services.llm_services import (
    analyze_candidate,
    APIEmptyError,
    LLMContentEmptyError,
    )
from services.output_services import clean_output
from services.resources_services import initialize_user_data
from flask import jsonify, Blueprint, session
#from api.resources import user_data_manager
#from services.general_services import get_session_id

# 创建蓝图
output_bp = Blueprint('output', __name__, url_prefix='/api/output')

@output_bp.route('/analyze', methods=['GET'])
def analyze_cdd_output():
    # 分析候选人及输出的接口函数
    try:
        resume = session['resume']
        pdf_urls = session['pdf_urls']
        print(f"Received resume for analysis: {resume[:50]}...")  # 调试输出，截断长文本
        result = analyze_candidate(resume, pdf_urls)
        # 无错误时清理数据
        cleaned_result = clean_output(result)
        
        return jsonify({
            "status": "success",
            "data": cleaned_result
        }), 200

    except APIEmptyError as e:
        return jsonify({
            "status": "fail",
            "message": str(e)
        }), 503
    except LLMContentEmptyError as e:
        return jsonify({
            "status": "fail",
            "message": str(e)
        }), 500

@output_bp.route('/start_new_analysis', methods=['POST'])
def start_new_analysis():
    
    # 重置用户数据
    initialize_user_data()
    
    return jsonify({
        "status": "success",
        "message": "新一轮分析已开启，请重新上传简历和论文URL。"
    }), 200
