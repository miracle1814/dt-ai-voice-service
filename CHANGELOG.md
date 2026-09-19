# 更新日志

## V2.5（2026-09-19）

> 主题：从"文字回复 demo"升级为"能出声的语音交互服务"。**所有 V2.4 端点契约向后兼容，响应字段只增不改。**

### 新增

- **TTS 出声**：内置 edge-tts（微软免费在线合成，零密钥零配置）。
  - `/voice`、`/voice_upload` 响应新增 `audio`（MP3 base64）、`audio_id`、`audio_url` 字段，UE 解码即播或直接用 URL 播；
  - `/chat` 默认纯文字（保持 V2.4 行为），body 传 `"tts": true` 可单次带回音频。
- **音频缓存**：合成结果落盘 `audio_cache/`，`GET /audio/{audio_id}` 提供 URL 播放；相同内容秒级去重，缓存 24h 自动过期。
- **新端点**：
  - `POST /voice_base64` — JSON 推 base64 音频（UE 侧比 multipart 好造），支持 wav/mp3/裸 PCM（自动包 WAV）；
  - `POST /tts/synthesize` — 纯文字合成（欢迎语、固定话术）；
  - `GET /tts/voices` — 列出可用音色；
  - `GET /health` — 健康检查（与 `/` 等价，附引擎与会话状态）。
- **多会话**：所有对话端点支持 `session_id`，各客户端上下文隔离；不传自动落 `default` 会话（兼容 V2.4）。`/clear` 支持按会话清理，不传清空全部。
- **ASR 适配器**：`config.json -> asr.provider` 二选一 —— `local_whisper`（默认，本地离线）/ `aliyun_nls`（阿里云一句话识别，Token 自动管理）。引擎契约统一，新增引擎零改路由。

### 变更

- faster-whisper 改为**懒加载**：未安装时服务照常启动，文字链路可用，语音端点返回明确错误提示。
- `requirements.txt` 新增 edge-tts、python-multipart。

### 兼容性

- V2.4 的顶层 `api_key` / `host` / `port` 配置写法仍生效；推荐迁移到 `llm.*` 分层结构（见 config.example.json）。
- `/voice` 的 `{"action":"start"}` 旧流程不变；`/voice_upload` multipart 不变。

## V2.4（2026-04-10 首次交付 / 2026-09-19 整理开源）

- FastAPI + 本地 faster-whisper + OpenAI 兼容 LLM 适配器（默认 MiniMax 示例）。
- 端点：`/`（健康检查）、`/chat`、`/voice`、`/voice_upload`、`/clear`。
- 特性：百度热搜/搜索标题作轻量联网参考；emoji/Markdown 清洗；10 轮全局对话历史。
