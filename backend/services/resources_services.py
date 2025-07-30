import os
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
from pathlib import Path

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
    
class FileSaveError(Exception):
    """文件保存异常"""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return f"文件保存失败: {self.message}"
    
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
    
# 验证文件类型
def validate_file_type(file: FileStorage) -> None:
    """验证文件是否为PDF类型（无需保存临时文件）"""
    # 1. 检查文件扩展名（快速筛选）
    if not file.filename.lower().endswith('.pdf'):
        raise InvalidFileTypeError()
    
    # 2. 检查文件前几个字节（魔数）来验证PDF格式
    # PDF文件的前4个字节是'%PDF'
    header = file.stream.read(4)
    file.stream.seek(0)  # 重置文件指针
    
    if header != b'%PDF':
        raise InvalidFileTypeError()

# 检查文件是否过大
def validate_file_size(file: FileStorage) -> None:
    """验证文件大小是否超过限制，必要时流式计算大小"""
    max_size_mb = current_app.config.get('MAX_PDF_SIZE', 10)
    max_size_bytes = max_size_mb * 1024 * 1024
    
    # 优先使用content_length属性（如果存在）
    if file.content_length is not None:
        if file.content_length > max_size_bytes:
            raise FileTooLargeError(max_size_mb)
        return
    
    # 如果content_length不可用，则流式计算文件大小
    # 注意：这会读取整个文件内容到内存，谨慎使用
    total_size = 0
    chunk_size = 4096
    
    try:
        while chunk := file.stream.read(chunk_size):
            total_size += len(chunk)
            if total_size > max_size_bytes:
                file.stream.close()  # 关闭流以释放资源
                raise FileTooLargeError(max_size_mb)
        
        # 重置文件指针，以便后续处理
        file.stream.seek(0)
    except Exception as e:
        # 确保流被关闭
        file.stream.close()
        raise FileSaveError(f"验证文件大小时出错: {str(e)}") from e

# 保存临时文件
def save_temp_file(file: FileStorage) -> str:
    """保存文件到临时目录（增强大小验证）"""
    # 1. 验证文件类型和大小（如果需要）
    validate_file_type(file)
    validate_file_size(file)  # 获取验证结果

    # 2. 创建并保存临时文件
    temp_dir = os.path.join(tempfile.gettempdir(), 'resume_system')
    os.makedirs(temp_dir, exist_ok=True)

    # 使用tempfile.NamedTemporaryFile创建安全的临时文件
    with tempfile.NamedTemporaryFile(
        mode='wb',
        dir=temp_dir,
        prefix='resume_',
        suffix='.pdf',
        delete=False
    ) as temp_file:
        temp_file_path = temp_file.name
        
        # 分块写入文件，避免大文件占用过多内存
        chunk_size = 4096
        with file.stream as stream:
            stream.seek(0)
            while chunk := stream.read(chunk_size):
                temp_file.write(chunk) 

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
        file_path = str(Path(file_path))  # 确保路径是Path对象
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