import magic
import os
import uuid  # 用于生成唯一临时文件名
import tempfile
from werkzeug.datastructures import FileStorage
from flask import current_app
import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException
from pdfminer.pdfdocument import PDFEncryptionError
from pdfminer.pdfparser import PDFSyntaxError
import requests
from urllib.parse import urlparse
from requests.exceptions import RequestException

# 自定义error类型
class InvalidFileTypeError(Exception):
    """文件类型不符合要求"""
    def __str__(self):
        return "请上传PDF格式的文件"

class FileTooLargeError(Exception):
    """文件大小超过限制"""
    def __init__(self, max_size_mb: int):
        self.max_size_mb = max_size_mb
        
    def __str__(self):
        return f"我们可接收的最大文件不能超过{self.max_size_mb}MB哟"
    
class PDFReadError(Exception):
    """PDF读取异常，用来反馈不同类型的读取错误"""
    pass

class InvalidURLError(Exception):
    """URL格式不符合要求"""
    def __str__(self):
        return "链接格式不正确，请检查是否包含http或https哟~"

class URLUnreachableError(Exception):
    """URL无法访问"""
    def __str__(self):
        return "链接无法访问，可能已过期或不存在啦~"
    
# 辅助函数：生成临时文件路径（独立于save_temp_file，解决循环依赖）
def _create_temp_path():
    """生成临时文件路径（仅创建路径，不保存文件内容）"""
    temp_dir = os.path.join(tempfile.gettempdir(), 'resume_system')
    os.makedirs(temp_dir, exist_ok=True)  # 确保临时目录存在
    # 使用UUID生成唯一文件名，避免冲突
    unique_filename = f"resume_temp_{uuid.uuid4()}.pdf"
    return os.path.join(temp_dir, unique_filename)

# 验证文件类型（不依赖save_temp_file，解决循环依赖）
def validate_file_type(file):
    """验证文件是否为PDF类型（双重验证：扩展名+文件内容）"""
    # 1. 检查文件扩展名（快速筛选）
    if not file.filename.lower().endswith('.pdf'):
        raise InvalidFileTypeError()
    
    # 2. 检查文件内容（通过MIME类型，更安全）
    temp_path = _create_temp_path()  # 使用独立函数生成路径
    try:
        file.save(temp_path)  # 临时保存文件到路径
        # 读取文件MIME类型（需要python-magic库）
        file_type = magic.from_file(temp_path, mime=True)
        if file_type != 'application/pdf':
            raise InvalidFileTypeError()
    finally:
        # 无论验证成功与否，都删除临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)

# 检查文件是否过大
def validate_file_size(file):
    """验证文件大小是否超过限制"""
    # 从配置中获取最大文件大小（单位：MB）
    max_size_mb = current_app.config.get('MAX_PDF_SIZE', 10)  # 默认10MB
    max_size_bytes = max_size_mb * 1024 * 1024
    
    # 检查文件大小
    if file.content_length is None:
        return False
    
    if file.content_length > max_size_bytes:
        raise FileTooLargeError(max_size_mb)
    return True

# 保存临时文件
def save_temp_file(file: FileStorage) -> str:
    """保存文件到临时目录（增强大小验证）"""
    # 1. 验证文件类型和大小（如果需要）
    size_valid = True  # 初始化默认值

    validate_file_type(file)
    size_valid = validate_file_size(file)  # 获取验证结果
    
    # 2. 二次验证：当客户端未提供content_length时，检查实际文件大小
    if not size_valid:
        actual_size = os.path.getsize(temp_file_path)
        max_size_mb = current_app.config.get('MAX_PDF_SIZE', 10)
        max_size_bytes = max_size_mb * 1024 * 1024
        
        if actual_size > max_size_bytes:
            os.remove(temp_file_path)  # 删除超大文件
            raise FileTooLargeError(max_size_mb)
    
    # 3. 创建并保存临时文件
    temp_dir = os.path.join(tempfile.gettempdir(), 'resume_system')
    os.makedirs(temp_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_dir, f"resume_{uuid.uuid4()}.pdf")
    file.save(temp_file_path)

    return temp_file_path

# 读取pdf内容并以文字输出(从临时文件处获取pdf)
def read_pdf(file_path: str) -> str:
    """
    读取PDF文件内容并返回文本
    :param file_path: 临时文件路径
    :return: 提取的文本内容（所有页合并）
    """

    # 基础校验： 1. 文件是否存在（防止系统自动删除等意外情况）；2. 简单检验扩展名，防止人为修改
    if not os.path.exists(file_path):
        raise PDFReadError('文件似乎飘走啦，辛苦你在上传一下哟~')
    
    if not file_path.lower().endswith('.pdf'):
        raise PDFReadError('文件格式不是pdf，请上传pdf文件呢？')
    
    # 读取pdf内容，若是有错误则输出错误信息
    try:
        # 读取pdf文字内容
        with pdfplumber.open(file_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n\n" # 空格符表示下一个页面

            if not full_text.strip():
                raise PDFReadError('没有可识别的文字内容哟，请尝试上传非扫描版的简历！')
            
        return full_text
            
        # 其他error的输出
    except PDFSyntaxError:
        raise PDFReadError(f"PDF文件好像有点小脾气哦～它可能在传输中受伤了，请尝试重新下载或用其他软件打开后另存为PDF")
    except PDFEncryptionError:
        raise PDFReadError(f"这个PDF文件上了锁哦！请提供密码或让文件所有者分享无密码版本")
    except PdfminerException:
        raise PDFReadError(f"这个PDF文件有点特别呢～系统暂时无法解析它，请确认文件格式是否正确")
    except Exception as e:
        # 其他未知错误（隐藏技术细节）
        raise PDFReadError("解析文件时出了点小问题，请重试或换一个文件试试；如果多次有误，请联系技术同学。")

# URL验证函数
def validate_paper_url(url: str) -> None:
    """
    验证url格式是否符合正常格式，且是否可达
    """
    # 1. 基础格式验证（必须）
    try:
        parsed = urlparse(url.strip())
        # 必须包含 http/https 协议 + 域名
        if not (parsed.scheme in ('http', 'https') and parsed.netloc):
            raise InvalidURLError("哎呀~ 链接格式好像不太对哦！要以 http:// 或 https:// 开头，并且要有完整的网站地址才行呢~")
    except ValueError as e:
        raise InvalidURLError("这个URL里好像藏着奇怪的字符哦~ 请检查一下是不是输错啦！")

    # 2. 基础可达性验证（必须）
    try:
        # 简化：单次请求，5秒超时（砍掉重试，降低复杂度）
        response = requests.head(url, timeout=5, allow_redirects=True)
        # 200/301/302 视为有效，其他状态码视为不可达
        if response.status_code not in {200, 301, 302}:
            raise URLUnreachableError(f"链接访问失败啦！错误代码：{response.status_code} 请确认链接是否正确~")
    except RequestException as e:
        raise URLUnreachableError("网络开小差了~ 请检查链接是否有效，或者稍后再试哦~ ")