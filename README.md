# 数字孪生 AI 语音服务

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg) ![Python](https://img.shields.io/badge/Python-3.10+-blue.svg) ![LLM](https://img.shields.io/badge/LLM-厂商无关-8A2BE2) ![Version](https://img.shields.io/badge/version-V2.5-green.svg)

模型厂商无关的 AI 语音交互服务，为虚幻引擎 5（UE5）数字孪生平台提供**语音识别 + 大模型对话 + 语音合成**全链路。LLM/ASR 通过可配置适配器接入，UE5 蓝图通过 HTTP 调用即可嵌入 AI 功能。

## 项目背景

在城市数字化孪生平台开发中，甲方提出引入大模型实现智能交互的需求。本项目构建了一个可独立部署的 AI 语音服务：UE5 蓝图只需发 HTTP 请求，就能拿到「用户说了什么 + AI 怎么答 + 对应的语音」，开箱即出声。

## 核心功能（V2.5）

- **语音识别（ASR）** — 双引擎可配：本地 faster-whisper（离线）或 阿里云 NLS 一句话识别（云端高精度）
- **大模型对话（LLM）** — OpenAI 兼容适配器，多轮上下文 + 多会话隔离（任意厂商/本地 Ollama/vLLM 均可）
- **语音合成（TTS）** — edge-tts 免费合成，零密钥；响应直接带 MP3（base64 + URL 双形态），合成结果自动缓存
- **文字交互** — 纯文本对话模式，用于快速测试和 UE 集成
- **UE5 蓝图对接** — 完整的 HTTP 接口方案与字段级文档

## 技术栈

| 层级 | 技术 |
|:---|:---|
| Web 框架 | FastAPI（Python） |
| 语音识别 | 适配器：faster-whisper（本地离线，默认）/ 阿里云 NLS（可选） |
| 大模型 | 可插拔适配器：任意 OpenAI 兼容接口（包内默认 MiniMax 适配示例） |
| 语音合成 | edge-tts（免费，无需密钥），MP3 输出 + 磁盘缓存 |
| 对接引擎 | Unreal Engine 5（HTTP 蓝图调用） |

## API 接口

| 接口 | 方法 | 说明 |
|:---|:---|:---|
| `GET /`（或 `/health`） | GET | 健康检查，返回版本与引擎状态 |
| `POST /chat` | POST | 文字对话：`{"text": "你好", "session_id": "kiosk1", "tts": false}` |
| `POST /voice` | POST | 语音对话（V2.4 兼容：读 `temp_recording.wav`）→ 识别 + 对话 + **返回 MP3** |
| `POST /voice_base64` | POST | 语音对话（V2.5 新增）：JSON 推 base64 音频，支持 wav/mp3/裸 PCM |
| `POST /voice_upload` | POST | 语音对话（multipart 上传音频文件） |
| `POST /tts/synthesize` | POST | 纯文字合成语音（欢迎语/固定话术） |
| `GET /tts/voices` | GET | 列出可用音色 |
| `GET /audio/{id}` | GET | 播放缓存的合成音频（MP3） |
| `POST /clear` | POST | 清除对话历史（可按 `session_id` 清，不传清全部） |

## 架构

```
UE5 蓝图 (HTTP)
    │
    ▼
┌────────────────────────────────────┐
│  FastAPI 服务 (localhost:8888)     │
│                                    │
│  /chat   → LLM 适配器 → 文字       │
│  /voice* → ASR 适配器 → LLM → TTS  │──► MP3 (base64 + /audio/{id} URL)
│  /tts    → TTS 适配器（独立合成）  │
│                                    │
│  会话历史：按 session_id 隔离      │
└────────────────────────────────────┘
     │              │              │
     ▼              ▼              ▼
 Whisper/      OpenAI兼容      edge-tts
 阿里云NLS     LLM 接口        (免费)
 (可配)        (可配)          (零密钥)
```

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置（复制 config.example.json 为 config.json，填入 LLM api_key；
#    想切云端 ASR 就把 asr.provider 改成 aliyun_nls 并填 AK）
#    ※ API Key 不会也不应提交到仓库

# 3. 启动服务
python start_service.py

# 4. 测试
python AI_Chat.py
curl -X POST http://localhost:8888/tts/synthesize -H "Content-Type: application/json" -d "{\"text\":\"你好，欢迎来到数字孪生平台\"}"
```

> 首次语音识别会自动下载 Whisper base 模型（约 150MB）。不想装 faster-whisper：删掉 requirements 里那行，把 `asr.provider` 换成 `aliyun_nls`。

## 项目结构

```
dt-ai-voice-service/
├── voice_service.py          # 核心服务（FastAPI 路由 + LLM 适配器）
├── asr_engines.py            # ASR 适配器（local_whisper / aliyun_nls）
├── tts_engines.py            # TTS 引擎（edge-tts）+ 音频缓存
├── session_store.py          # 多会话对话历史
├── start_service.py          # 启动器
├── AI_Chat.py                # 命令行交互测试工具
├── build.bat                 # 打包脚本
├── config.example.json       # 配置模板（复制为 config.json 后填入 API Key）
├── scripts/scan_secrets.py   # 提交前敏感信息扫描
├── UE蓝图对接指南.md          # UE5 蓝图集成文档
└── CHANGELOG.md              # 版本历史
```

## 安全说明

- API Key 通过 `config.json`（已被 .gitignore 排除）或环境变量 `LLM_API_KEY` 提供，**不要**将密钥写入代码或提交到仓库。
- 服务默认监听 `0.0.0.0:8888`，公网部署请自行加反代与鉴权。
- 提交代码前建议跑 `python scripts/scan_secrets.py`（规则化扫描密钥/隐私形态，命中即拒绝提交）。

## License

[MIT](LICENSE)
