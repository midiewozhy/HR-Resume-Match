def clean_output(data: dict) -> dict:
    """
    清理LLM返回的数据：
    - 数值保留原始格式
    - null值填充为空字符串
    - 特定占位符字符串保持不变
    """
    PLACEHOLDERS = {"无匹配岗位", "无适合岗位推荐", "无匹配信息"}
    
    def process_value(value):
        if value is None:
            return ""
        elif isinstance(value, str):
            # 保留特定占位符字符串不变
            if value in PLACEHOLDERS:
                return value
            # 清理普通字符串
            return value.strip()
        elif isinstance(value, (int, float)):
            # 保留数值原始格式
            return value
        elif isinstance(value, list):
            # 递归处理列表元素
            return [process_value(item) for item in value]
        elif isinstance(value, dict):
            # 递归处理字典值
            return {k: process_value(v) for k, v in value.items()}
        else:
            # 其他类型保持不变
            return value
    
    return {k: process_value(v) for k, v in data.items()}