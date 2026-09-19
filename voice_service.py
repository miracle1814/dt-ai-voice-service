#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数字孪生平台 AI 语音服务
版本: V2.4
"""
import base64
import json
import os
import re
from datetime import datetime
from fastapi import FastAPI, Request, File, UploadFile, Form
from faster_whisper import WhisperModel
import requests
import uvicorn
import wave

# 修复无窗口模式下的stdout/stderr问题
import sys
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# ============ 配置 ============
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# 默认配置（api_key 不入库：从 config.json 或环境变量 LLM_API_KEY 读取）
# LLM 适配器：base_url/model 均可配置 —— 任何 OpenAI 兼容接口（含本地 Ollama/
# vLLM）改配置即接；默认内置 MiniMax 适配（其 v2 接口为 OpenAI 兼容格式）。
DEFAULT_CONFIG = {
    "api_key": "",
    "llm_base_url": "https://api.minimaxi.com/v1/text/chatcompletion_v2",
    "llm_model": "MiniMax-M2.5",
    "host": "0.0.0.0",
    "port": 8888
}

def load_config():
    """从配置文件加载"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_CONFIG

CONFIG = load_config()
API_KEY = CONFIG.get("api_key") or os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = CONFIG.get("llm_base_url", DEFAULT_CONFIG["llm_base_url"])
LLM_MODEL = CONFIG.get("llm_model", DEFAULT_CONFIG["llm_model"])
SERVICE_HOST = CONFIG.get("host", DEFAULT_CONFIG["host"])
SERVICE_PORT = CONFIG.get("port", DEFAULT_CONFIG["port"])

if not API_KEY:
    print("[警告] 未配置 LLM API Key —— 请复制 config.example.json 为 config.json 并填入，"
          "或设置环境变量 LLM_API_KEY（/chat /voice 接口将不可用）")

SAMPLE_RATE = 16000
AUDIO_FILENAME = "temp_recording.wav"
WHISPER_MODEL = "base"
WHISPER_LANGUAGE = "zh"

whisper_model = None
conversation_history = []  # 对话历史
MAX_HISTORY = 10  # 最多保存10轮对话

def get_audio_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, AUDIO_FILENAME)

def remove_emoji(text):
    """移除emoji和Markdown符号"""
    if not text:
        return ""
    import unicodedata
    # 只移除真正emoji，保留中文
    result = []
    for char in text:
        if char == '*' or char == '#':
            continue
        try:
            # 检查是否是emoji
            if unicodedata.category(char) in ['So', 'Mn', 'Mc', 'Me']:
                continue
        except:
            pass
        result.append(char)
    text = ''.join(result)
    # 清理多余换行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def need_search(text):
    patterns = [
        r"今天.*新闻", r"最新.*新闻", r"最近.*新闻", r"今日.*头条",
        r"现在.*股价", r".*股票.*多少", r".*价格.*多少",
        r"天气.*", r".*天气.*",
        r"什么是.*", r".*是什么",
        r"怎么.*", r"如何.*", r"怎样.*",
        r".*比赛.*", r".*赛事.*",
        r".*电影.*", r".*电视剧.*",
        r".*排名.*", r".*排行榜.*",
        r".*发布.*", r".*上市.*",
        r".*版本.*", r".*更新.*",
    ]
    for p in patterns:
        if re.search(p, text.lower()):
            return True
    return False

def search_online(query, max_results=3):
    """使用百度热搜获取实时信息"""
    try:
        print(f"[搜索] {query}")
        results = []
        
        # 获取百度实时热搜
        if any(k in query for k in ['新闻', '热搜', '头条', '今天']):
            try:
                resp = requests.get(
                    'https://top.baidu.com/board?tab=realtime',
                    timeout=10,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                )
                titles = re.findall(r'class="c-single-text-ellipsis">(.*?)</div>', resp.text)
                if titles:
                    for i, t in enumerate(titles[:max_results], 1):
                        t = t.strip().replace('<em>', '').replace('</em>', '')
                        results.append(f"{i}. {t}")
            except Exception as e:
                print(f"[热搜] 获取失败: {e}")
        
        # 如果热搜没有结果，尝试百度搜索
        if not results:
            try:
                search_url = f"https://www.baidu.com/s?wd={query}&rn={max_results}"
                resp = requests.get(search_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                titles = re.findall(r'class="c-single-text-ellipsis">(.*?)</div>', resp.text)
                for t in titles[:max_results]:
                    t = t.strip().replace('<em>', '').replace('</em>', '')
                    if t:
                        results.append(t)
            except Exception as e:
                print(f"[搜索] 百度搜索失败: {e}")
        
        print(f"[搜索] 找到{len(results)}条")
        return results
    except Exception as e:
        print(f"[搜索] 失败: {e}")
        return []

# ============ FastAPI ============
app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok", "version": "V2.4"}

@app.post("/chat")
async def chat(request: Request):
    global conversation_history
    try:
        body = await request.json()
        text = body.get("text", "")
        if not text:
            return {"success": False, "error": "请提供text字段"}
        
        print(f"[Chat] {text}")
        
        # 自动联网搜索，获取最新信息
        print("[搜索] 正在联网获取最新信息...")
        search_results = search_online(text)
        if search_results:
            search_info = "\n\n【最新搜索结果】\n" + "\n".join(search_results) + "\n请根据以上最新信息回答用户的问题。"
            text = text + search_info
        else:
            # 即使没有搜索结果也说明一下
            text = text + "\n\n（请基于你的知识库中最新最准确的信息回答）"
        
        ai_reply = call_ai_with_history(text)
        print(f"[AI原始] {repr(ai_reply)}")
        ai_reply = remove_emoji(ai_reply)
        print(f"[AI清理后] {repr(ai_reply)}")
        
        # 保存对话历史
        conversation_history.append({"role": "user", "content": text})
        conversation_history.append({"role": "assistant", "content": ai_reply})
        # 限制历史长度
        if len(conversation_history) > MAX_HISTORY * 2:
            conversation_history = conversation_history[-MAX_HISTORY * 2:]
        
        return {"success": True, "user_text": body.get("text", ""), "ai_reply": ai_reply, "audio": ""}
    except Exception as e:
        print(f"[Chat] 错误: {e}")
        return {"success": False, "error": str(e)}

@app.post("/voice")
async def voice(request: Request):
    global whisper_model, conversation_history
    try:
        body = await request.json()
        if body.get("action") != "start":
            return {"success": False, "error": "未知action"}
        
        audio_file = get_audio_path()
        if not os.path.exists(audio_file):
            return {"success": False, "error": "请先录音"}
        if os.path.getsize(audio_file) < 1000:
            return {"success": False, "error": "录音太短"}
        
        if whisper_model is None:
            whisper_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        
        segments, _ = whisper_model.transcribe(audio_file, language=WHISPER_LANGUAGE)
        text = "".join([s.text for s in segments]).strip()
        print(f"[Voice] {text}")
        
        if not text:
            return {"success": False, "error": "未识别到语音"}
        
        # 自动联网搜索，获取最新信息
        print("[搜索] 正在联网获取最新信息...")
        search_results = search_online(text)
        if search_results:
            search_info = "\n\n【最新搜索结果】\n" + "\n".join(search_results) + "\n请根据以上最新信息回答用户的问题。"
            text = text + search_info
        else:
            # 即使没有搜索结果也说明一下
            text = text + "\n\n（请基于你的知识库中最新最准确的信息回答）"
        
        ai_reply = remove_emoji(call_ai_with_history(text))
        
        # 保存对话历史
        conversation_history.append({"role": "user", "content": text})
        conversation_history.append({"role": "assistant", "content": ai_reply})
        if len(conversation_history) > MAX_HISTORY * 2:
            conversation_history = conversation_history[-MAX_HISTORY * 2:]
        
        return {"success": True, "user_text": text.split("【搜索结果】")[0], "reply": ai_reply}
    except Exception as e:
        print(f"[Voice] 错误: {e}")
        return {"success": False, "error": str(e)}

@app.post("/voice_upload")
async def voice_upload(file: UploadFile = File(...)):
    """接收上传的录音文件进行语音识别"""
    global whisper_model, conversation_history
    try:
        # 保存上传的文件
        audio_path = get_audio_path()
        with open(audio_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        if os.path.getsize(audio_path) < 1000:
            return {"success": False, "error": "录音太短"}
        
        if whisper_model is None:
            whisper_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        
        segments, _ = whisper_model.transcribe(audio_path, language=WHISPER_LANGUAGE)
        text = "".join([s.text for s in segments]).strip()
        
        if not text:
            return {"success": False, "error": "未识别到语音"}
        
        print(f"[Voice] {text}")
        
        # 联网搜索
        search_results = search_online(text)
        if search_results:
            search_info = "\n\n【最新搜索结果】\n" + "\n".join(search_results) + "\n请根据以上最新信息回答。"
            text = text + search_info
        else:
            text = text + "\n\n（请基于最新准确信息回答）"
        
        ai_reply = remove_emoji(call_ai_with_history(text))
        
        conversation_history.append({"role": "user", "content": text})
        conversation_history.append({"role": "assistant", "content": ai_reply})
        if len(conversation_history) > MAX_HISTORY * 2:
            conversation_history = conversation_history[-MAX_HISTORY * 2:]
        
        return {"success": True, "text": text.split("【搜索结果】")[0], "reply": ai_reply}
    except Exception as e:
        print(f"[VoiceUpload] 错误: {e}")
        return {"success": False, "error": str(e)}

def call_ai_with_history(text):
    """带对话历史的 LLM 调用（厂商适配器）。

    适配契约：POST {llm_base_url}，Bearer 鉴权，请求/响应为 OpenAI 兼容格式
    （messages / choices[].message.content）。更换厂商 = 改 config 的
    llm_base_url / llm_model / api_key 三项，无需改代码。
    """
    global conversation_history
    now = datetime.now()
    weekday = ["周一","周二","周三","周四","周五","周六","周日"][now.weekday()]
    system_prompt = f"你是智能物业管家，简洁友好回复，用中文，禁止使用Markdown格式（如**加粗**）。当前时间：{now.strftime('%Y年%m月%d日 %H:%M')} {weekday}。"

    # 构建消息列表
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": text})

    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": 300
    }

    resp = requests.post(LLM_BASE_URL, headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}, json=payload, timeout=30)
    return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")

@app.post("/clear")
def clear_history():
    """清除对话历史"""
    global conversation_history
    conversation_history = []
    return {"success": True, "message": "对话历史已清除"}

if __name__ == "__main__":
    print("=" * 40)
    print("数字孪生AI语音服务 V2.4")
    print(f"http://{SERVICE_HOST.replace('0.0.0.0','localhost')}:{SERVICE_PORT}")
    print("=" * 40)
    uvicorn.run(app, host=SERVICE_HOST, port=SERVICE_PORT, log_level="warning")
