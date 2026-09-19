# UE5 蓝图对接 AI 语音服务指南

> 与 **V2.4** 代码逐字段对齐（2026-09-19 核对）。当前版本服务端返回**文字回复**，
> 不含 TTS 音频——如需语音播报，见文末「TTS 扩展指引」。

## 📋 对接概览

```
UE5 蓝图                    语音服务 (localhost:8888)
┌─────────────┐            ┌──────────────────────┐
│  录音模块    │──保存──→   │  temp_recording.wav  │
│  (麦克风)   │            └──────────────────────┘
└─────────────┘                    │
        │                          ▼
        │                 ┌──────────────────────┐
        │                 │   FastAPI 服务       │
        │                 │                      │
        │    POST /voice  │  1. Whisper 语音识别 │
        └──────────────→ │  2. LLM 对话（适配器）│
        │                 └──────────────────────┘
        │                          │
        │                          ▼
        │                 ┌──────────────────────┐
        │   返回JSON:      │  "success": true,    │
        │   - user_text   │  "user_text": "...", │
        │   - ai_reply    │  "ai_reply": "..."   │
        └─────────────┘    └──────────────────────┘
```

> **LLM 厂商无关**：服务端通过适配器调用大模型（OpenAI 兼容格式），
> `config.json` 里改 `llm_base_url` / `llm_model` / `api_key` 三项即可切换
> 任意厂商或本地推理（Ollama / vLLM），UE 侧无需任何改动。

## 🔧 蓝图结构

### 1. 变量设置

| 变量名 | 类型 | 说明 |
|:---|:---|:---|
| `API_URL` | String | `http://localhost:8888` |
| `RecordingFile` | String | `temp_recording.wav` (完整路径) |
| `bIsRecording` | Boolean | 录音状态 |
| `LastUserText` | String | 识别出的用户语音文本 |
| `LastAIResponse` | String | AI回复文本 |

### 2. 录音流程

```
┌────────────────────┐
│   按下语音按钮      │
└─────────┬──────────┘
          ▼
┌────────────────────┐
│   Start Recording  │
│   (系统组件)       │
└─────────┬──────────┘
          │ (等待1-3秒)
          ▼
┌────────────────────┐
│   Stop Recording   │
└─────────┬──────────┘
          ▼
┌────────────────────┐
│  Save to File      │
│  temp_recording.wav│
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
import json

def call_voice_api(wav_path):
    """调用语音服务API"""
    url = "http://localhost:8888/voice"

    with open(wav_path, 'rb') as f:
        files = {'audio': f}
        data = {'action': 'start'}
        response = requests.post(url, data=data, files=files)

    return response.json()

# 获取结果
result = call_voice_api("C:/path/to/temp_recording.wav")
print(result['user_text'])  # 识别出的用户语音
print(result['ai_reply'])   # AI回复文本
```

## 📝 端点参考（与 V2.4 代码逐字段核对）

### 健康检查
```
GET http://localhost:8888/
→ {"status": "ok", "version": "V2.4"}
```

### 语音对话
```
POST http://localhost:8888/voice
Body: {"action": "start"}（音频文件为项目根目录的 temp_recording.wav）

响应:
{
    "success": true,
    "user_text": "用户说的话",
    "ai_reply": "AI的回复",
    "reply": "AI的回复"          ← 历史兼容别名，与 ai_reply 相同
}
```

### 文字对话
```
POST http://localhost:8888/chat
Body: {"text": "你好"}

响应:
{
    "success": true,
    "user_text": "你好",
    "ai_reply": "你好！有什么可以帮您的？",
    "audio": ""                   ← 历史遗留字段，恒为空（TTS 未内置）
}
```

### 清除历史
```
POST http://localhost:8888/clear
响应: {"success": true, "message": "对话历史已清除"}
```

## 🎯 快速开始：纯蓝图实现

### 步骤1: 添加 HTTP 请求组件
在关卡蓝图中添加 `HTTP Request` 组件（或经 Python 中转，见上）

### 步骤2: 录音
使用 UE 的 `Audio Capture` 组件或第三方录音插件

### 步骤3: 调用 API 并展示

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
│   ├── Set LastUserText   ← user_text
│   ├── Set LastAIResponse ← ai_reply
│   └── Show on UI
│
└── On HTTP Response (Failed)
    └── Show Error Message
```

### 步骤4（可选扩展）: 接入 TTS 播报

当前服务端返回纯文字。若需语音播报，两条路径：

1. **UE 侧合成**：把 `ai_reply` 交给 UE 的 TTS 插件/第三方语音服务；
2. **服务端扩展**：仿照 `call_ai_with_history` 的适配器模式，在
   `voice_service.py` 中新增 TTS 适配器（返回 base64 音频字段），
   并在蓝图里恢复「解码 → 播放」节点。

## 🔧 技术问题

### Q: UE 无法直接发送 multipart/form-data？
A: 使用 Python 脚本中转（上文方案），或使用 `VaRest` 等插件

### Q: 如何实现按住说话？
A: 使用 `OnPressed` / `On Released` 事件

### Q: 换大模型厂商要改 UE 侧吗？
A: 不用。改服务端 `config.json` 的 `llm_base_url` / `llm_model` / `api_key`
即可，蓝图与 HTTP 契约完全不变。

## 📂 相关文件

- `voice_service.py` - 语音服务主程序
- `AI_Chat.py` - 命令行测试工具（先用它验证服务是否正常）
- `config.example.json` - 配置模板（复制为 config.json 后填入）

## 🚀 推荐：先用命令行测试

在 UE 集成之前，先用 `python AI_Chat.py` 验证服务与 LLM 适配器工作正常，
再做 UE 侧集成。
