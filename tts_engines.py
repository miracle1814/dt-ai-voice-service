#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TTS 引擎层 —— 文字转语音 + 音频缓存。

V2.5 内置 edge-tts（微软免费在线合成，无需任何密钥），输出 MP3。
引擎契约：`synthesize(text, voice) -> bytes(mp3)`；新增云端引擎按此契约实现即可。

音频缓存：合成结果落盘 audio_cache/，通过 GET /audio/{audio_id} 提供 URL 播放，
  相同文本+音色命中缓存直接复用（演示场景重复问题占大多数流量）。
"""
import asyncio
import hashlib
import logging
import os
import time

log = logging.getLogger("tts")

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_cache")
CACHE_TTL_SEC = 24 * 3600          # 缓存文件保留 24 小时，启动时清理过期
# 云引擎失败后的短路时间：期间直接放弃云引擎，避免每次请求都等一轮超时
ENGINE_COOLDOWN_SEC = 300


class TTSEngine:
    """edge-tts 合成器（零密钥）。voice 见 GET /tts/voices。"""

    name = "edge"

    def __init__(self, default_voice: str = "zh-CN-XiaoxiaoNeural"):
        self.default_voice = default_voice
        self._down_until = 0.0

    @staticmethod
    def list_voices() -> list:
        return [
            {"voice_key": "zh-CN-XiaoxiaoNeural", "desc": "晓晓（女·温柔，默认）"},
            {"voice_key": "zh-CN-YunxiNeural", "desc": "云希（男·阳光）"},
            {"voice_key": "zh-CN-YunyangNeural", "desc": "云扬（男·播音）"},
            {"voice_key": "zh-CN-XiaoyiNeural", "desc": "晓伊（女·活泼）"},
        ]

    def is_available(self) -> bool:
        return time.time() >= self._down_until

    async def synthesize(self, text: str, voice: str = "") -> bytes:
        """异步合成（FastAPI async 路由直接 await）。失败抛异常，由路由层决定降级策略。

        注意：不要在协程里调 asyncio.run() 包本方法 —— 会抛
        "asyncio.run() cannot be called from a running event loop"。
        """
        if not self.is_available():
            raise RuntimeError("TTS 引擎处于失败冷却期，稍后自动恢复")
        return await self._synth_async(text, voice or self.default_voice)

    async def _synth_async(self, text: str, voice: str) -> bytes:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        buf = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        if not buf:
            raise RuntimeError("edge-tts 返回空音频")
        return bytes(buf)

    def mark_down(self):
        self._down_until = time.time() + ENGINE_COOLDOWN_SEC
        log.warning("[TTS] 引擎标记失败，冷却 %d 秒", ENGINE_COOLDOWN_SEC)

    def mark_up(self):
        self._down_until = 0.0


# ---------------------------------------------------------------- 缓存
def cache_store(data: bytes) -> str:
    """落盘缓存并返回 audio_id（12 位哈希）。相同内容天然去重。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    audio_id = hashlib.md5(data).hexdigest()[:12] + ".mp3"
    path = os.path.join(CACHE_DIR, audio_id)
    if not os.path.exists(path):
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    return audio_id[:12]


def cache_path(audio_id: str) -> str:
    """按 audio_id 取缓存文件绝对路径；非法 id 或不存在返回空串。"""
    safe = os.path.basename(audio_id)
    if not safe or not safe.replace(".mp3", "").isalnum() or len(safe) > 20:
        return ""
    path = os.path.join(CACHE_DIR, safe if safe.endswith(".mp3") else safe + ".mp3")
    return path if os.path.isfile(path) else ""


def cache_cleanup():
    """启动时清理过期缓存文件。"""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cutoff = time.time() - CACHE_TTL_SEC
        removed = 0
        for fn in os.listdir(CACHE_DIR):
            p = os.path.join(CACHE_DIR, fn)
            try:
                if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                    os.remove(p)
                    removed += 1
            except OSError:
                pass
        if removed:
            log.info("[TTS] 清理过期缓存 %d 个", removed)
    except OSError:
        pass
