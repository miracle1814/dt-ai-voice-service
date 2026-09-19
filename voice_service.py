#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数字孪生平台 AI 语音服务
版本: V2.5

V2.5 相对 V2.4 的升级（端点全部向后兼容，响应只增不改）：
  1. ASR 适配器化：本地 Whisper（默认，离线）/ 阿里云 NLS 一句话识别（配置即切）
  2. TTS 出声：edge-tts 免费合成（零密钥），语音端点直接返回 MP3（base64 + audio_url）
  3. 音频缓存：audio_cache/ 落盘 + GET /audio/{id} URL 播放，重复问题零重复合成
  4. 多会话：所有端点支持 session_id，各客户端上下文隔离；/clear 支持按会话清理
  5. 新端点：POST /voice_base64（UE 推 base64 音频）、POST /tts/synthesize、
            GET /tts/voices、GET /health
"""
import base64
import json
import logging
import os
import re
from datetime import datetime

import requests
import uvicorn
from fastapi import FastAPI, Request, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from asr_engines import create_asr_from_config, pcm_to_wav_bytes
from session_store import SessionStore
from tts_engines import TTSEngine, cache_store, cache_path, cache_cleanup

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("voice_service")

# 修复无窗口模式下的 stdout/stderr 问题
import sys
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# ============ 配置 ============
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "llm": {
        "base_url": "https://api.minimaxi.com/v1/text/chatcompletion_v2",
        "model": "MiniMax-M2.5",
        "api_key": "",
        "max_tokens": 300,
    },
    "asr": {"provider": "local_whisper", "whisper_model": "base", "language": "zh"},
    "tts": {"provider": "edge", "voice": "zh-CN-XiaoxiaoNeural", "auto_speak_on_voice": True},
    "auto_search": True,
    "host": "0.0.0.0",
    "port": 8888,
}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def load_config() -> dict:
    """读 config.json 并与默认值深合并。"""
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = _deep_merge(cfg, json.load(f))
        except Exception as e:
            log.warning("config.json 解析失败，使用默认配置: %s", e)
    return cfg


_RAW_CFG = {}
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            _RAW_CFG = json.load(f) or {}
    except Exception:
        _RAW_CFG = {}

CONFIG = load_config()
if _RAW_CFG.get("api_key"):
    CONFIG["llm"]["api_key"] = CONFIG["llm"].get("api_key") or _RAW_CFG["api_key"]
CONFIG["host"] = _RAW_CFG.get("host", CONFIG["host"])
CONFIG["port"] = _RAW_CFG.get("port", CONFIG["port"])

API_KEY = CONFIG["llm"].get("api_key") or os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = CONFIG["llm"]["base_url"]
LLM_MODEL = CONFIG["llm"]["model"]
LLM_MAX_TOKENS = int(CONFIG["llm"].get("max_tokens", 300))
SERVICE_HOST = CONFIG["host"]
SERVICE_PORT = int(CONFIG["port"])
AUTO_SEARCH = bool(CONFIG.get("auto_search", True))

if not API_KEY:
    print("[警告] 未配置 LLM API Key —— 请复制 config.example.json 为 config.json 并填入，"
          "或设置环境变量 LLM_API_KEY（/chat /voice 的对话能力不可用，/tts/synthesize 不受影响）")

# ============ 引擎与会话（模块级单例） ============
try:
    ASR = create_asr_from_config(CONFIG)
except Exception as e:
    log.warning("ASR 引擎初始化失败（/voice 链路不可用，文字链路不受影响）: %s", e)
    ASR = None

TTS = TTSEngine(default_voice=CONFIG["tts"].get("voice", "zh-CN-XiaoxiaoNeural"))
SESSIONS = SessionStore()
AUDIO_FILENAME = "temp_recording.wav"
DEFAULT_SESSION = "default"


def get_audio_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), AUDIO_FILENAME)


# ============ 文本工具 ============
def remove_emoji(text):
    """移除 emoji 和 Markdown 符号（TTS 与大屏字幕都不吃这些）。"""
    if not text:
        return ""
    import unicodedata
    result = []
    for char in text:
        if char in ("*", "#"):
            continue
        if unicodedata.category(char) in ("So", "Mn", "Mc", "Me"):
            continue
        result.append(char)
    text = "".join(result)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


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
    return any(re.search(p, text.lower()) for p in patterns)


def search_online(query, max_results=3):
    """轻量联网参考：百度热搜/搜索结果标题（无需密钥，标题级质量，仅供 LLM 参考）。"""
    try:
        results = []
        if any(k in query for k in ("新闻", "热搜", "头条", "今天")):
            try:
                resp = requests.get(
                    "https://top.baidu.com/board?tab=realtime", timeout=10,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                )
                titles = re.findall(r'class="c-single-text-ellipsis">(.*?)</div>', resp.text)
                results = [t.strip().replace("<em>", "").replace("</em>", "")
                           for t in titles[:max_results] if t.strip()]
            except Exception as e:
                log.warning("[搜索] 热搜获取失败: %s", e)
        if not results:
            try:
                resp = requests.get(
                    f"https://www.baidu.com/s?wd={query}&rn={max_results}", timeout=10,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                )
                titles = re.findall(r'class="c-single-text-ellipsis">(.*?)</div>', resp.text)
                results = [t.strip().replace("<em>", "").replace("</em>", "")
                           for t in titles[:max_results] if t.strip()]
            except Exception as e:
                log.warning("[搜索] 百度搜索失败: %s", e)
        log.info("[搜索] %s -> %d 条", query[:30], len(results))
        return results
    except Exception as e:
        log.warning("[搜索] 失败: %s", e)
        return []


def call_llm_with_history(text: str, session_id: str) -> str:
    """带会话历史的 LLM 调用（厂商适配器）。

    适配契约：POST {llm_base_url}，Bearer 鉴权，请求/响应为 OpenAI 兼容格式。
    更换厂商 = 改 config.json 的 llm.base_url / llm.model / llm.api_key 三项，无需改代码。
    """
    now = datetime.now()
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
    system_prompt = (
        f"你是智能物业管家，简洁友好回复，用中文，禁止使用Markdown格式（如**加粗**）。"
        f"当前时间：{now.strftime('%Y年%m月%d日 %H:%M')} {weekday}。"
    )
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(SESSIONS.get_history(session_id))
    messages.append({"role": "user", "content": text})
    payload = {"model": LLM_MODEL, "messages": messages, "max_tokens": LLM_MAX_TOKENS}
    resp = requests.post(
        LLM_BASE_URL,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json=payload, timeout=30,
    )
    content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError(
            "LLM 返回为空 —— 检查 config.json 的 llm.api_key / base_url / model（或环境变量 LLM_API_KEY）"
        )
    return content


def augment_with_search(text: str) -> str:
    """按开关拼联网搜索参考。"""
    if not AUTO_SEARCH or not need_search(text):
        return text
    results = search_online(text)
    if results:
        return text + "\n\n【最新搜索结果】\n" + "\n".join(results) + "\n请根据以上最新信息回答用户的问题。"
    return text + "\n\n（请基于你的知识库中最新最准确的信息回答）"


def _finish_turn(session_id: str, user_text: str, ai_reply: str):
    SESSIONS.append(session_id, user_text, ai_reply)


async def _try_synthesize(text: str, voice: str = "") -> dict:
    """合成并落缓存。成功返回 {audio_id, audio_base64}；失败返回 {}（不阻塞对话链路）。"""
    try:
        mp3 = await TTS.synthesize(text, voice)
        audio_id = cache_store(mp3)
        return {"audio_id": audio_id, "audio_base64": base64.b64encode(mp3).decode()}
    except Exception as e:
        log.warning("[TTS] 合成失败（对话不受影响）: %s", e)
        return {}


# ============ FastAPI ============
app = FastAPI(title="DT AI Voice Service", version="2.5")


@app.on_event("startup")
def _startup():
    cache_cleanup()


@app.get("/")
@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "V2.5",
        "asr": ASR.name if ASR else "unavailable",
        "sessions": SESSIONS.stats(),
    }


@app.post("/chat")
async def chat(request: Request):
    """文字对话。V2.5 兼容 V2.4 契约；可选 body.tts=true 让回复直接带音频。"""
    try:
        body = await request.json()
        text = (body.get("text") or "").strip()
        if not text:
            return {"success": False, "error": "请提供text字段"}
        session_id = body.get("session_id") or DEFAULT_SESSION
        log.info("[Chat][%s] %s", session_id, text)

        augmented = augment_with_search(text)
        ai_reply = remove_emoji(call_llm_with_history(augmented, session_id))
        log.info("[Chat][%s] AI: %s", session_id, ai_reply[:80])
        _finish_turn(session_id, augmented, ai_reply)

        resp = {"success": True, "user_text": text, "ai_reply": ai_reply,
                "reply": ai_reply, "session_id": session_id, "audio": ""}
        if body.get("tts"):
            audio = await _try_synthesize(ai_reply, body.get("voice", ""))
            if audio:
                resp["audio"] = audio["audio_base64"]
                resp["audio_id"] = audio["audio_id"]
                resp["audio_url"] = str(request.base_url).rstrip("/") + f"/audio/{audio['audio_id']}"
        return resp
    except Exception as e:
        log.exception("[Chat] 错误")
        return {"success": False, "error": str(e)}


async def _voice_reply(request: Request, audio_bytes: bytes, audio_format: str, session_id: str, voice: str):
    """语音链路公共体：ASR → 搜索增强 → LLM → （默认）TTS。"""
    if ASR is None:
        return {"success": False, "error": "ASR 引擎不可用（检查 config.json 的 asr 配置与依赖）"}
    user_text = ASR.transcribe(audio_bytes, audio_format)
    log.info("[Voice][%s] ASR(%s): %s", session_id, audio_format, user_text)
    if not user_text:
        return {"success": False, "error": "未识别到语音"}

    augmented = augment_with_search(user_text)
    ai_reply = remove_emoji(call_llm_with_history(augmented, session_id))
    _finish_turn(session_id, augmented, ai_reply)

    resp = {"success": True, "user_text": user_text, "ai_reply": ai_reply,
            "reply": ai_reply, "session_id": session_id}
    if CONFIG["tts"].get("auto_speak_on_voice", True):
        audio = await _try_synthesize(ai_reply, voice)
        if audio:
            resp["audio"] = audio["audio_base64"]
            resp["audio_id"] = audio["audio_id"]
            resp["audio_url"] = str(request.base_url).rstrip("/") + f"/audio/{audio['audio_id']}"
    return resp


@app.post("/voice")
async def voice(request: Request):
    """V2.4 兼容：UE 录音到固定路径后调 {"action":"start"}，服务端读 temp_recording.wav。"""
    try:
        body = await request.json()
        if body.get("action") != "start":
            return {"success": False, "error": "未知action"}
        audio_file = get_audio_path()
        if not os.path.exists(audio_file):
            return {"success": False, "error": "请先录音"}
        if os.path.getsize(audio_file) < 1000:
            return {"success": False, "error": "录音太短"}
        with open(audio_file, "rb") as f:
            audio_bytes = f.read()
        return await _voice_reply(
            request, audio_bytes, "wav",
            body.get("session_id") or DEFAULT_SESSION, body.get("voice", ""),
        )
    except Exception as e:
        log.exception("[Voice] 错误")
        return {"success": False, "error": str(e)}


@app.post("/voice_upload")
async def voice_upload(request: Request, file: UploadFile = File(...)):
    """V2.4 兼容：multipart 上传音频文件。V2.5 支持表单字段 session_id / voice。"""
    try:
        form = await request.form()
        audio_bytes = await file.read()
        if len(audio_bytes) < 1000:
            return {"success": False, "error": "录音太短"}
        fmt = (os.path.splitext(file.filename or "")[1].lstrip(".").lower() or "wav")
        return await _voice_reply(
            request, audio_bytes, fmt,
            form.get("session_id") or DEFAULT_SESSION, form.get("voice") or "",
        )
    except Exception as e:
        log.exception("[VoiceUpload] 错误")
        return {"success": False, "error": str(e)}


@app.post("/voice_base64")
async def voice_base64(request: Request):
    """V2.5 新增：JSON 推 base64 音频（UE 里比 multipart 好造）。

    body: {"audio_base64": "...", "format": "wav|mp3|pcm", "session_id": "...", "voice": "..."}
    format=pcm 时按 16kHz/单声道/16bit 裸 PCM 自动包 WAV。
    """
    try:
        body = await request.json()
        b64 = (body.get("audio_base64") or "").strip()
        if not b64:
            return {"success": False, "error": "请提供 audio_base64 字段"}
        audio_bytes = base64.b64decode(b64)
        if len(audio_bytes) < 1000:
            return {"success": False, "error": "录音太短"}
        fmt = (body.get("format") or "wav").lower()
        if fmt in ("pcm", "raw"):
            audio_bytes = pcm_to_wav_bytes(audio_bytes)
            fmt = "wav"
        return await _voice_reply(
            request, audio_bytes, fmt,
            body.get("session_id") or DEFAULT_SESSION, body.get("voice", ""),
        )
    except Exception as e:
        log.exception("[VoiceBase64] 错误")
        return {"success": False, "error": str(e)}


@app.post("/tts/synthesize")
async def tts_synthesize(request: Request):
    """V2.5 新增：纯文字合成，供 UE 做欢迎语/固定话术等。"""
    try:
        body = await request.json()
        text = (body.get("text") or "").strip()
        if not text:
            return {"success": False, "error": "请提供text字段"}
        voice = body.get("voice", "")
        mp3 = await TTS.synthesize(remove_emoji(text), voice)
        audio_id = cache_store(mp3)
        return {
            "success": True,
            "audio_id": audio_id,
            "audio_url": str(request.base_url).rstrip("/") + f"/audio/{audio_id}",
            "audio_base64": base64.b64encode(mp3).decode(),
            "voice": voice or TTS.default_voice,
        }
    except Exception as e:
        log.exception("[TTS] 错误")
        return {"success": False, "error": str(e)}


@app.get("/tts/voices")
def tts_voices():
    return {"success": True, "default": TTS.default_voice, "voices": TTSEngine.list_voices()}


@app.get("/audio/{audio_id}")
def audio(audio_id: str):
    """播放缓存的合成音频（MP3）。UE 的 MediaPlayer 节点直接吃这个 URL。"""
    path = cache_path(audio_id)
    if not path:
        return JSONResponse(status_code=404, content={"success": False, "error": "audio not found"})
    return FileResponse(path, media_type="audio/mpeg", filename=os.path.basename(path))


@app.post("/clear")
def clear_history(body: dict = None):
    """清除对话历史。body 可选 {"session_id": "..."}；不传清空全部（V2.4 语义）。"""
    session_id = (body or {}).get("session_id", "")
    n = SESSIONS.clear(session_id)
    return {"success": True,
            "message": f"已清除 {n} 个会话" if not session_id else ("已清除" if n else "会话不存在")}


if __name__ == "__main__":
    print("=" * 44)
    print("数字孪生AI语音服务 V2.5")
    print(f"http://{SERVICE_HOST.replace('0.0.0.0', 'localhost')}:{SERVICE_PORT}")
    print(f"  ASR: {ASR.name if ASR else 'unavailable'} | TTS: {TTS.name} | LLM: {LLM_MODEL}")
    print("=" * 44)
    uvicorn.run(app, host=SERVICE_HOST, port=SERVICE_PORT, log_level="warning")
