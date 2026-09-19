# 数字孪生 AI 语音服务

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg) ![Python](https://img.shields.io/badge/Python-3.10+-blue.svg) ![LLM](https://img.shields.io/badge/LLM-厂商无关-8A2BE2)

模型厂商无关的 AI 语音交互服务，为虚幻引擎 5（UE5）数字孪生平台提供语音识别 + 大模型对话能力。LLM 通过可配置适配器接入（**任何 OpenAI 兼容接口均可**，包内默认内置 MiniMax 适配作为开箱示例）。

## 项目背景

在城市数字化孪生平台开发中，甲方提出引入大模型实现智能交互的需求。本项目构建了一个可独立部署的 AI 语音服务，通过 REST API 对外提供语音识别、大模型对话、语音合成等能力，UE5 蓝图通过 HTTP 调用即可嵌入 AI 功能。

## 核心功能

- **语音识别** — 基于 Whisper 模型，支持中文语音转文字
- **大模型对话** — OpenAI 兼容适配器，支持上下文多轮对话（厂商/模型可配置，本地 Ollama/vLLM 亦可）
- **文字交互** — 纯文本对话模式，用于快速测试和 UE 集成
- **UE5 蓝图对接** — 完整的 HTTP 接口方案，蓝图可直接调用

## 技术栈

| 层级 | 技术 |
|:---|:---|
| Web 框架 | FastAPI（Python） |
| 语音识别 | faster-whisper（本地 Whisper base 模型，离线运行） |
| 大模型 | 可插拔适配器：任意 OpenAI 兼容接口（包内默认 MiniMax 适配示例） |
| 对接引擎 | Unreal Engine 5（HTTP 蓝图调用） |

## API 接口

| 接口 | 方法 | 说明 |
|:---|:---|:---|
| `GET /` | 健康检查 | 返回 `{"status": "ok", "version": "V2.4"}` |
| `POST /chat` | 文字对话 | `{"text": "你好"}` → `{"ai_reply": "..."}` |
| `POST /voice` | 语音对话 | 上传音频文件 → 识别 + 对话 + TTS 合成 |
| `POST /clear` | 清除历史 | 清除多轮对话上下文 |

## 架构

```
UE5 蓝图 (HTTP)
    │
    ▼
┌─────────────────────────────┐
│   FastAPI 服务 (localhost:8888) │
│  ┌─────────────────────────┐  │
│  │  /chat   → MiniMax 对话  │  │
│  │  /voice  → Whisper → LLM │  │
│  │  /clear  → 清除上下文    │  │
│  └─────────────────────────┘  │
└─────────────────────────────┘
    │               │
    ▼               ▼
 Whisper          MiniMax API
 (本地)          (云端)
```

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 LLM 适配器（三选一或组合）
#    a. 复制 config.example.json 为 config.json，填入 api_key
#    b. 换厂商/模型：改同一文件里的 llm_base_url 与 llm_model（任何
#       OpenAI 兼容接口均可，含本地 Ollama/vLLM）
#    c. 或仅设环境变量：set LLM_API_KEY=你的key
#    ※ API Key 不会也不应提交到仓库

# 3. 启动服务
python start_service.py

# 4. 测试
python AI_Chat.py
```

> 首次运行会自动下载 Whisper base 模型（约 150MB），也可手动指定模型目录。

## 项目结构

```
dt-ai-voice-service/
├── voice_service.py          # 核心服务（FastAPI + Whisper + MiniMax）
├── start_service.py          # 启动器
├── AI_Chat.py                # 命令行交互测试工具
├── build.bat                 # 打包脚本
├── config.example.json       # 配置模板（复制为 config.json 后填入 API Key）
├── UE蓝图对接指南.md          # UE5 蓝图集成文档
└── AI语音服务交付文档.md       # 完整交付文档
```

## 安全说明

- API Key 通过 `config.json`（已被 .gitignore 排除）或环境变量 `LLM_API_KEY` 提供，**不要**将密钥写入代码或提交到仓库。
- 服务默认监听 `0.0.0.0:8888`，公网部署请自行加反代与鉴权。

## License

[MIT](LICENSE)
