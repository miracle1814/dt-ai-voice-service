# UE5 蓝图对接 AI 语音服务指南

> 与 **V2.5** 代码逐字段对齐（2026-09-19 核对）。V2.5 起语音端点**直接返回 TTS 音频**
>（MP3 base64 + URL 双形态）；`/chat` 保持纯文字，body 传 `"tts": true` 可单次带回音频。

## 📋 对接概览

```
UE5 蓝图                    语音服务 (localhost:8888)
┌─────────────┐            ┌──────────────────────────────┐
│  录音模块    │──保存──→   │  temp_recording.wav          │
│  (麦克风)   │            └──────────────┬───────────────┘
└─────────────┘                           │
        │                                 ▼
        │                  ┌──────────────────────────────┐
        │   POST /voice    │   FastAPI 服务               │
        └──────────────→  │  1. ASR 语音识别（可配引擎）  │
        │                 │  2. LLM 对话（适配器）        │
        │                 │  3. TTS 合成 → MP3            │
        │                 └──────────────┬───────────────┘
        │                                │
        ▼                                ▼
   返回JSON:  user_text（用户说了什么）
              ai_reply  （AI的文字回复）
              audio     （MP3 base64，可直接解码播放）
              audio_url （http://host:8888/audio/{id}，可直接给 MediaPlayer）
```

> **LLM 厂商无关**：服务端通过适配器调用大模型（OpenAI 兼容格式），
> `config.json` 里改 `llm.base_url` / `llm.model` / `llm.api_key` 三项即可切换
> 任意厂商或本地推理（Ollama / vLLM），UE 侧无需任何改动。

## 🔧 蓝图结构

### 1. 变量设置

| 变量名 | 类型 | 说明 |
|:---|:---|:---|
| `API_URL` | String | `http://localhost:8888` |
| `SessionId` | String | 会话标识，如 `kiosk1`（多客户端上下文隔离，可不传） |
| `RecordingFile` | String | `temp_recording.wav` (完整路径) |
| `bIsRecording` | Boolean | 录音状态 |
| `LastUserText` | String | 识别出的用户语音文本 |
| `LastAIResponse` | String | AI回复文字 |
| `LastAudioURL` | String | AI回复语音的播放地址 |

### 2. 录音流程

```
┌────────────────────┐
│   按下语音按钮      │
└─────────┬──────────┘
          ▼
┌────────────────────┐
│   Start Recording  │   UE Audio Capture 组件或第三方录音插件
└─────────┬──────────┘
          │ (等待1-3秒)
          ▼
┌────────────────────┐
│   Stop Recording   │
└─────────┬──────────┘
          ▼
┌────────────────────┐
│  Save to File      │   temp_recording.wav（16kHz 单声道最稳）
└─────────┬──────────┘
          ▼
┌────────────────────┐
│  Call HTTP Request │
└────────────────────┘
```

### 3. HTTP 请求（Python 脚本方式，推荐）

UE 蓝图的 HTTP 功能有限，推荐经 Python 插件中转。创建 `call_voice_api.py`：

```python
import requests

def call_voice_api(wav_path, session_id="default"):
    """语音对话：上传录音 → 拿文字回复 + MP3"""
    url = "http://localhost:8888/voice_upload"
    with open(wav_path, 'rb') as f:
        resp = requests.post(url, files={'file': f}, data={'session_id': session_id})
    return resp.json()

def chat(text, session_id="default"):
    """文字对话"""
    resp = requests.post("http://localhost:8888/chat", json={"text": text, "session_id": session_id})
    return resp.json()

def tts(text, session_id="default"):
    """纯文字合成（欢迎语/固定话术）"""
    resp = requests.post("http://localhost:8888/tts/synthesize", json={"text": text})
    return resp.json()

# 用法
result = call_voice_api("C:/path/to/temp_recording.wav")
print(result['user_text'])   # 识别出的用户语音
print(result['ai_reply'])    # AI的文字回复
print(result['audio_url'])   # MP3 播放地址（或用 result['audio'] base64）
```

## 📝 端点参考（与 V2.5 代码逐字段核对）

### 健康检查
```
GET http://localhost:8888/          （/health 等价）
→ {"status": "ok", "version": "V2.5", "asr": "local_whisper",
   "sessions": {"sessions": 1, "total_messages": 4}}
```

### 语音对话（三选一，响应结构一致）
```
POST http://localhost:8888/voice            body: {"action": "start"}（读固定路径录音，V2.4 兼容）
POST http://localhost:8888/voice_upload     multipart: file=<音频文件>; form 可选 session_id / voice
POST http://localhost:8888/voice_base64     body: {"audio_base64": "...", "format": "wav|mp3|pcm",
                                                   "session_id": "kiosk1", "voice": ""}

响应:
{
    "success": true,
    "user_text": "用户说的话",
    "ai_reply": "AI的文字回复",
    "reply": "AI的文字回复",          ← V2.4 兼容别名，与 ai_reply 相同
    "session_id": "kiosk1",
    "audio": "<MP3的base64>",         ← V2.5 新增；TTS 失败时无此字段（文字仍正常返回）
    "audio_id": "a1b2c3d4e5f6",
    "audio_url": "http://localhost:8888/audio/a1b2c3d4e5f6"
}
```

### 文字对话
```
POST http://localhost:8888/chat
Body: {"text": "你好", "session_id": "kiosk1", "tts": false}

响应:
{
    "success": true,
    "user_text": "你好",
    "ai_reply": "你好！有什么可以帮您的？",
    "reply": "…",                     ← V2.4 兼容别名
    "session_id": "kiosk1",
    "audio": ""                       ← V2.4 兼容字段，恒为空；body tts:true 时才会填
}
```

### 文字合成语音（V2.5 新增）
```
POST http://localhost:8888/tts/synthesize
Body: {"text": "欢迎来到数字孪生平台", "voice": "zh-CN-XiaoxiaoNeural"}

响应: {"success": true, "audio_id": "…", "audio_url": "…", "audio_base64": "…", "voice": "…"}
```

### 音色列表（V2.5 新增）
```
GET http://localhost:8888/tts/voices
→ {"success": true, "default": "zh-CN-XiaoxiaoNeural", "voices": [{"voice_key": "…", "desc": "…"}, …]}
```

### 清除历史
```
POST http://localhost:8888/clear          Body（可选）: {"session_id": "kiosk1"}
→ 不传 body 清空全部（V2.4 语义）；传 session_id 只清该会话
→ {"success": true, "message": "已清除"}
```

## 🎯 快速开始：纯蓝图实现

### 步骤1: 添加 HTTP 请求组件
在关卡蓝图中添加 `HTTP Request` 组件（或经 Python 中转，见上）

### 步骤2: 录音
使用 UE 的 `Audio Capture` 组件或第三方录音插件

### 步骤3: 调用 API 并播放语音回复

```
Event Graph:
├── On Voice Button Clicked
│   ├── Start Audio Capture
│   ├── Delay 2.0
│   ├── Stop Audio Capture
│   ├── Save Audio to File (temp_recording.wav)
│   └── Call Send Voice Request
│
├── On HTTP Response (Success)
│   ├── Parse JSON
│   ├── Set LastUserText    ← user_text
│   ├── Set LastAIResponse  ← ai_reply
│   ├── Set LastAudioURL    ← audio_url        ← V2.5 新增
│   ├── Show on UI
│   └── [V2.5 播放语音，两种方式二选一]
│        ├── 方式A: MediaPlayer 节点 OpenURL(LastAudioURL) → 直接流式播放
│        └── 方式B: 取 audio 字段 → base64 解码 → 导入为 SoundWave → 播放
│
└── On HTTP Response (Failed)
    └── Show Error Message
```

> **多会话说明**：不同大屏/客户端用不同 `session_id`，对话上下文互不干扰；
> 同一客户端想"重新开始对话"，调一次 `/clear` 带上自己的 session_id 即可。

### 步骤4（可选）: 更换音色 / 关闭自动语音

- 音色：请求 body 传 `"voice": "zh-CN-YunxiNeural"`（可用音色见 `/tts/voices`）；
- 只想拿文字不要音频：`config.json` 里 `tts.auto_speak_on_voice` 改 `false`
  （响应不再带 audio 字段，链路更快）。

## 🔧 技术问题

### Q: UE 无法直接发送 multipart/form-data？
A: 使用 Python 脚本中转（上文方案），或改用 `/voice_base64`（纯 JSON），或使用 `VaRest` 等插件

### Q: 如何实现按住说话？
A: 使用 `OnPressed` / `On Released` 事件

### Q: 换大模型厂商要改 UE 侧吗？
A: 不用。改服务端 `config.json` 的 `llm.base_url` / `llm.model` / `llm.api_key`
即可，蓝图与 HTTP 契约完全不变。ASR/TTS 引擎同理（`asr.provider` / `tts` 段）。

### Q: audio 字段时有时无？
A: TTS 合成失败时响应不带 audio 字段，但 `ai_reply` 文字一定返回——UE 侧做好空值判断即可。

## 📂 相关文件

- `voice_service.py` - 语音服务主程序
- `asr_engines.py` - ASR 适配器（换识别引擎看这里）
- `tts_engines.py` - TTS 引擎与缓存
- `session_store.py` - 多会话管理
- `AI_Chat.py` - 命令行测试工具（先用它验证服务是否正常）
- `config.example.json` - 配置模板（复制为 config.json 后填入 API Key）

## 🚀 推荐：先用命令行测试

在 UE 集成之前，先用 `python AI_Chat.py` 验证服务与 LLM 适配器工作正常，
再验证一次 TTS：`curl http://localhost:8888/tts/voices`，然后做 UE 侧集成。
