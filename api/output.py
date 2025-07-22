from services.llm_services import (
    analyze_candidate,
    APIEmptyError,
    LLMContentEmptyError,
    )
from services.output_services import clean_output
from flask import jsonify, Blueprint

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