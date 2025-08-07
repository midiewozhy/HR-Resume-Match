import logging
import json
from services.feishu_services import construct_single_system_prompt, get_batch_system_prompt
from services.client_services import llm_client
import re
import json
from config import Config
from threading import Lock, Thread
import queue
from queue import Empty
import openai
import requests

# 静态数据
# 获取飞书文档内容
# pre_score_content = _content_cache["_pre_content_cache"]
# paper_score_content = _content_cache["_paper_content_cache"]
# tag_content = _content_cache["_tag_content_cache"]
# 获取system prompt

# 自定义Error类型
class APIEmptyError(Exception):
    def __init__(self):
        super().__init__("非常抱歉，服务暂时不可用哦~请稍后再试或联系技术支持哟！")

class LLMContentEmptyError(Exception):
    def __init__(self):
        super().__init__("评估结果生成失败啦~再给大模型一次机会吧！或者也可以联系技术支持哦！")

def get_user_prompt(pdf: str, url: str):
    user_info = f"""
    分析素材：  
    - PDF内容(简历或论文)： {pdf}
    - 论文链接：  {url}
    请严格按 system prompt 输出 JSON。  
    """
    #- 评分标准（预打分用）：{pre_score_content}  
    #- 岗位画像（匹配岗位用）：{tag_content}  
    #- 论文打分方针（有论文时用）：{paper_score_content} 

    user_prompt = [
        {"role": "user", "content": user_info},
    ]

    return user_prompt

def construct_prompt(user_prompt: list):
    system_prompt = construct_single_system_prompt() # 获取静态的system prompt
    whole_prompt = system_prompt + user_prompt
    return whole_prompt

def analyze_candidate(resume: str, pdf_urls: list):
    """分析候选人，内部实时获取动态数据，复用静态数据"""
    # 1. 构造prompt（复用静态数据和动态数据）
    user_prompt = get_user_prompt(resume, pdf_urls)  # 传入动态数据，内部引用静态数据
    whole_prompt = construct_prompt(user_prompt)  # 内部引用静态的system_prompt
    print(whole_prompt)

    # 3. 调用大模型
    try:
        completion = llm_client.chat.completions.create(
            model=Config.BOT_ID,
            messages=whole_prompt,
            temperature=0,
            seed=42,
        )
    except (requests.Timeout, requests.ConnectionError) as e:
        logging.error(str(e))
        raise APIEmptyError
    except openai.APIError as e:
        logging.error(str(e))
        raise APIEmptyError
    except Exception:
        raise Exception

    # 4. 校验响应
    if not completion.choices or not completion.choices[0].message.content:
        raise APIEmptyError # 抛出异常，由API层处理

    # 5. 处理返回结果
    ai_ret = completion.choices[0].message.content.strip()
    ai_ret = re.sub(r'^(<\|FunctionCallEnd\|>|```json\n?|```\n?)', '', ai_ret, flags=re.IGNORECASE)
    ai_ret = re.sub(r'```\s*$', '', ai_ret)

    if not ai_ret:
        raise LLMContentEmptyError # 抛出异常
    
    if ai_ret.startswith("{{"):
        ai_ret = ai_ret[1:]
    if ai_ret.endswith("}}"):
        ai_ret = ai_ret[:-1]

    # 6. 解析JSON并返回
    try:
        return json.loads(ai_ret)
    except json.JSONDecodeError as e:
        logging.error(f"JSON解析失败 | 内容: {ai_ret[:100]}... | 错误：{str(e)}")
        raise LLMContentEmptyError from e
    
def batch_analysis(paper_urls: list[tuple[int,str]]):

    system_prompt = get_batch_system_prompt()
    results_lock = Lock()
    task_queue = queue.Queue()
    results = {}
    threads = []

    for item in paper_urls:
        task_queue.put(item)
    
    def consumer(system_prompt, results, queue, results_lock):
        while True:
            try:
                # 从队列获取任务（包含索引和数据），超时退出避免阻塞
                index, data = queue.get(timeout=1)
            except Empty:
                break

            user_info = f"""
            分析素材：
            论文链接{data}    
            """

            user_prompt = [{"role": "user","content": user_info}]
            whole_prompt = system_prompt + user_prompt
            #print(whole_prompt)

            try:
                completion = llm_client.chat.completions.create(
                    model=Config.BATCH_BOT_ID,
                    messages=whole_prompt,
                    temperature=0,
                    seed=42,
                )
                    # 4. 校验响应
                if not completion.choices or not completion.choices[0].message.content:
                    raise ValueError("大模型响应为空")# 抛出异常，由API层处理

                # 5. 处理返回结果
                ai_ret = completion.choices[0].message.content.strip()
                ai_ret = re.sub(r'^(<\|FunctionCallEnd\|>|```json\n?|```\n?)', '', ai_ret, flags=re.IGNORECASE)
                ai_ret = re.sub(r'```\s*$', '', ai_ret)

                if not ai_ret:
                    raise ValueError("内容清理后为空")
                
                if ai_ret.startswith("{{"):
                    ai_ret = ai_ret[1:]
                if ai_ret.endswith("}}"):
                    ai_ret = ai_ret[:-1]

                # 6. 解析JSON并返回
                try:
                    result = json.loads(ai_ret)
                    result['link'] = data
                    with results_lock:
                        results[index] = result
                except json.JSONDecodeError as e:
                    raise json.JSONDecodeError
                except Exception as e:
                    raise Exception
            except (requests.Timeout, requests.ConnectionError) as e:
                logging.error(str(e))
                with results_lock:    
                    results[index] = {
                        "link":data,
                        "score": "", 
                        "summary": "解析有误，请人工处理", 
                        "tag_primary": "", 
                        "contact_tag_primary": "",
                        "tag_secondary":"",
                        "contact_tag_secondary":""
                        }
            except openai.APIError as e:
                logging.error(str(e))
                with results_lock:    
                    results[index] = {
                        "link":data,
                        "score": "", 
                        "summary": "解析有误，请人工处理", 
                        "tag_primary": "", 
                        "contact_tag_primary": "",
                        "tag_secondary":"",
                        "contact_tag_secondary":""
                        }
            except json.JSONDecodeError as e:
                logging.error(f"JSON解析失败 | 内容: {ai_ret[:100]}... | 错误：{str(e)}")
                with results_lock:
                    results[index] = {
                        "link": data,
                        "score": "", 
                        "summary": "解析有误，请人工处理", 
                        "tag_primary": "", 
                        "contact_tag_primary": "",
                        "tag_secondary":"",
                        "contact_tag_secondary":""
                        }
            except ValueError as e:
                logging.error(str(e))
                with results_lock:    
                    results[index] = {
                        "link":data,
                        "score": "", 
                        "summary": "解析有误，请人工处理", 
                        "tag_primary": "", 
                        "contact_tag_primary": "",
                        "tag_secondary":"",
                        "contact_tag_secondary":""
                        }
            except Exception as e:
                logging.error(str(e))
                with results_lock:    
                    results[index] = {
                        "link":data,
                        "score": "", 
                        "summary": "解析有误，请人工处理", 
                        "tag_primary": "", 
                        "contact_tag_primary": "",
                        "tag_secondary":"",
                        "contact_tag_secondary":""
                        }
            finally:
                task_queue.task_done()
                
    for i in range(20):
        t = Thread(
            target = consumer, 
            name = f"consumer_{str(i+1)}",
            args = (system_prompt, results, task_queue, results_lock),)
        t.daemon = True
        t.start()
        threads.append(t)

    task_queue.join()

    for t in threads:
        t.join()

    return results

                    
    
                


    


