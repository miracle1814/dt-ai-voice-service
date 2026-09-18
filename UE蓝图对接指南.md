# UE5 蓝图对接 AI 语音服务指南

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
        │    POST /voice  │  1. Whisper语音识别  │
        └──────────────→ │  2. MiniMax对话      │
        │                 │  3. MiniMax TTS      │
        │                 └──────────────────────┘
        │                          │
        │                          ▼
        │                 ┌──────────────────────┐
        │   返回JSON:      │  {"success": true,   │
        │   - user_text   │   "ai_reply": "...",  │
        │   - ai_reply    │   "audio": "base64"} │
        │   - audio       └──────────────────────┘
        ▼                          │
┌─────────────┐                    │
│  播放模块    │←──解码──┘
│  (音频组件)  │
└─────────────┘
```

## 🔧 蓝图结构

### 1. 变量设置

| 变量名 | 类型 | 说明 |
|:---|:---|:---|
| `API_URL` | String | `http://localhost:8888` |
| `RecordingFile` | String | `temp_recording.wav` (完整路径) |
| `bIsRecording` | Boolean | 录音状态 |
| `LastAIResponse` | String | AI回复文本 |
| `LastAudioBase64` | String | 音频数据(Base64) |

### 2. 录音流程

```
┌────────────────────┐
│   按下语音按钮      │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│   Start Recording   │
│   (系统组件)        │
└─────────┬──────────┘
          │
          │ (等待1-3秒)
          ▼
┌────────────────────┐
│   Stop Recording    │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  Save to File      │
│  temp_recording.wav│
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  Call HTTP Request │
└─────────┬──────────┘
```

### 3. HTTP请求 (Python脚本方式)

由于UE蓝图HTTP功能有限，推荐使用Python插件方式：

#### 方案A：Python HTTP请求 (推荐)

创建 `call_voice_api.py`:

```python
import requests
import base64
import json

def call_voice_api(wav_path):
    """调用语音服务API"""
    url = "http://localhost:8888/voice"
    
    with open(wav_path, 'rb') as f:
        # UE中可以通过Form提交
        files = {'audio': f}
        data = {'action': 'start'}
        response = requests.post(url, data=data, files=files)
    
    return response.json()

# 获取结果
result = call_voice_api("C:/path/to/temp_recording.wav")
print(result['ai_reply'])  # AI回复文本
print(result['audio'])     # Base64音频
```

#### 方案B：直接用控制面板

在UE中只需要显示一个内嵌网页，调用控制面板的界面。

### 4. 简化方案：文字交互

如果暂时不用语音，可以用文字方式：

```
┌─────────────────────┐
│  用户输入文本        │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  HTTP POST /chat    │
│  Body: {"text": "..."}│
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  显示 AI 回复        │
│  播放 TTS 音频(Base64)│
└─────────────────────┘
```

## 📝 具体蓝图节点

### 健康检查
```
GET http://localhost:8888/
→ {"status": "ok", "version": "V2.4"}
```

### 语音对话
```
POST http://localhost:8888/voice
Body: {"action": "start"}

响应:
{
    "success": true,
    "user_text": "用户说的话",
    "ai_reply": "AI的回复",
    "audio": "Base64编码的MP3音频"
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
    "audio": ""
}
```

### 清除历史
```
POST http://localhost:8888/clear
响应: {"success": true, "message": "对话历史已清除"}
```

## 🎯 快速开始：纯蓝图实现

### 步骤1: 添加HTTP请求组件
在关卡蓝图中添加 `HTTP Request` 组件

### 步骤2: 录音
使用UE的 `Audio Capture` 组件或第三方插件

### 步骤3: 调用API

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
│   ├── Set AI Reply Text
│   ├── Play Audio from Base64
│   └── Show on UI
│
└── On HTTP Response (Failed)
    └── Show Error Message
```

### 步骤4: 播放音频

Base64音频解码播放：
```
Base64 String → Decode → Save as MP3 → Load Sound Wave → Play
```

## 🔧 技术问题

### Q: UE无法直接发送multipart/form-data？
A: 使用Python脚本中转，或使用插件如 `VaRest`

### Q: Base64音频如何播放？
A: 保存为临时文件后用 `Play Sound at Location` 播放

### Q: 如何实现按住说话？
A: 使用 `OnPressed` / `On Released` 事件

## 📂 相关文件

- `voice_service.py` - 语音服务主程序
- `voice_panel.py` - 控制面板（可用于调试）
- `UE_Blueprint_Example.uasset` - 蓝图示例（需手动创建）

## 🚀 推荐：先用控制面板测试

在UE集成的完整方案完成前，可以先用 `voice_panel.py` 控制面板测试语音对话的完整流程，确认效果后再做UE集成。
