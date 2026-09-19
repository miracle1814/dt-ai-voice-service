#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ASR 适配器层 —— 语音识别引擎可插拔。

契约：每个引擎实现 `transcribe(audio_bytes, audio_format) -> str`，
失败抛异常、成功返回纯文本（调用方只认这个契约，换引擎零改路由）。

内置引擎：
  local_whisper  本地 faster-whisper（离线，首次运行自动下载模型，约 150MB）
  aliyun_nls     阿里云智能语音交互·一句话识别 REST（需 AK + AppKey，按量计费）

选择方式：config.json -> "asr": {"provider": "local_whisper" | "aliyun_nls"}
"""
import io
import json
import logging
import time
import uuid
import wave

log = logging.getLogger("asr")


# ---------------------------------------------------------------- 公共工具
def pcm_to_wav_bytes(pcm: bytes, sample_rate: int = 16000, channels: int = 1, sampwidth: int = 2) -> bytes:
    """把裸 PCM（默认 16kHz/单声道/16bit）包成 WAV 容器，供各引擎统一消费。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


# ---------------------------------------------------------------- 引擎 1：本地 Whisper
class LocalWhisperASR:
    """faster-whisper 本地识别。模型懒加载：首次调用才初始化/下载。"""

    name = "local_whisper"

    def __init__(self, model_name: str = "base", language: str = "zh"):
        self._model_name = model_name
        self._language = language
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                raise RuntimeError(
                    "未安装 faster-whisper：pip install faster-whisper "
                    "（或把 config 的 asr.provider 换成 aliyun_nls）"
                )
            log.info("[ASR] 加载本地 Whisper 模型: %s（首次运行会自动下载）", self._model_name)
            self._model = WhisperModel(self._model_name, device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, audio_bytes: bytes, audio_format: str = "wav") -> str:
        model = self._ensure_model()
        import tempfile, os
        suffix = ".wav" if audio_format == "wav" else f".{audio_format}"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            tmp.write(audio_bytes)
            tmp.close()
            segments, _ = model.transcribe(tmp.name, language=self._language)
            return "".join(s.text for s in segments).strip()
        finally:
            try:
                os.remove(tmp.name)
            except OSError:
                pass


# ---------------------------------------------------------------- 引擎 2：阿里云 NLS 一句话识别
_NLS_GATEWAY = "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr"
_NLS_META = "https://nls-meta.cn-shanghai.aliyuncs.com"

class AliyunNLSASR:
    """阿里云一句话识别（REST 单发，非流式）。Token 自动获取并缓存。"""

    name = "aliyun_nls"

    def __init__(self, access_key_id: str, access_key_secret: str, app_key: str,
                 region: str = "cn-shanghai", sample_rate: int = 16000):
        if not (access_key_id and access_key_secret and app_key):
            raise RuntimeError("aliyun_nls 缺少配置：asr.aliyun 下需填 access_key_id / access_key_secret / app_key")
        self._ak_id = access_key_id
        self._ak_secret = access_key_secret
        self._app_key = app_key
        self._region = region
        self._sample_rate = sample_rate
        self._token = ""
        self._token_expire_at = 0.0

    # --- POP RPC 签名（V1.0）获取 NLS Token ---
    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expire_at - 120:
            return self._token
        import base64
        import hmac
        from hashlib import sha1
        from urllib.parse import urlencode, quote

        params = {
            "AccessKeyId": self._ak_id,
            "Action": "CreateToken",
            "Format": "JSON",
            "RegionId": self._region,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": uuid.uuid4().hex,
            "SignatureVersion": "1.0",
            "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "Version": "2019-02-28",
        }
        sorted_qs = "&".join(
            f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(params.items())
        )
        string_to_sign = "POST&%2F&" + quote(sorted_qs, safe="-_.~")
        signature = base64.b64encode(
            hmac.new((self._ak_secret + "&").encode(), string_to_sign.encode(), sha1).digest()
        ).decode()
        params["Signature"] = signature
        import requests as _rq
        resp = _rq.post(_NLS_META, data=urlencode(params), timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        token = payload.get("Token", {})
        if not token.get("Id"):
            raise RuntimeError(f"获取 NLS Token 失败: {payload}")
        self._token = token["Id"]
        self._token_expire_at = int(token.get("ExpireTime", time.time() + 3000))
        log.info("[ASR] NLS Token 已获取，有效期至 %s", time.strftime("%H:%M:%S", time.localtime(self._token_expire_at)))
        return self._token

    def transcribe(self, audio_bytes: bytes, audio_format: str = "wav") -> str:
        import requests as _rq
        token = self._get_token()
        params = {
            "appkey": self._app_key,
            "format": audio_format,
            "sample_rate": self._sample_rate,
        }
        headers = {"X-NLS-Token": token, "Content-Type": "application/octet-stream"}
        resp = _rq.post(_NLS_GATEWAY, params=params, headers=headers, data=audio_bytes, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") != 20000000:
            raise RuntimeError(f"NLS 识别失败: {result}")
        return (result.get("result") or "").strip()


# ---------------------------------------------------------------- 工厂
def create_asr_from_config(cfg: dict):
    """按 config['asr'] 构建引擎。缺省 local_whisper（零配置可跑）。"""
    asr_cfg = (cfg or {}).get("asr", {}) or {}
    provider = (asr_cfg.get("provider") or "local_whisper").strip()
    if provider == "local_whisper":
        return LocalWhisperASR(
            model_name=asr_cfg.get("whisper_model", "base"),
            language=asr_cfg.get("language", "zh"),
        )
    if provider == "aliyun_nls":
        ali = asr_cfg.get("aliyun", {}) or {}
        return AliyunNLSASR(
            access_key_id=ali.get("access_key_id", ""),
            access_key_secret=ali.get("access_key_secret", ""),
            app_key=ali.get("app_key", ""),
            region=ali.get("region", "cn-shanghai"),
            sample_rate=int(ali.get("sample_rate", 16000)),
        )
    raise RuntimeError(f"未知 ASR provider: {provider}（可选 local_whisper / aliyun_nls）")
