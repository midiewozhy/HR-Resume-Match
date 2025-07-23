from services.llm_services import (
    analyze_candidate,
    APIEmptyError,
    LLMContentEmptyError,
    )
from services.output_services import clean_output
from flask import jsonify, Blueprint
from resources import user_data_manager
from services.general_services import get_session_id

# 创建蓝图
output_bp = Blueprint('output', __name__, url_prefix='/api/output')

@output_bp.route('/analyze', methods=['GET'])
def analyze_cdd_output():
    # 分析候选人及输出的接口函数
    try:
        result = analyze_candidate()
        # 无错误时清理数据
        cleaned_result = clean_output(result)
        
        return jsonify({
            "status": "success",
            "data": cleaned_result
        }), 200

    except APIEmptyError as e:
        return jsonify({
            "status": "fail",
            "message": e
        }), 503
    except LLMContentEmptyError as e:
        return jsonify({
            "status": "fail",
            "message": e
        }), 500

@output_bp.route('/start_new_analysis', methods=['POST'])
def start_new_analysis():
    # 获取session_id
    session_id = get_session_id()
    
    # 重置用户数据
    user_data_manager.initialize_user_data(session_id)
    
    return jsonify({
        "status": "success",
        "message": "新一轮分析已开启，请重新上传简历和论文URL。"
    }), 200
