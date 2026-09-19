# AI语音服务 交付文档

## 版本
V2.4

## 日期
2026-04-10

## 交付内容

```
数字孪生AI语音服务/
├── AI_VoiceService.exe    ← 核心服务程序
├── AI_Service_Start.exe   ← 启动器
├── AI_Chat.exe            ← 交互工具
└── config.json           ← 配置文件
```

## 配置说明

打开 `config.json` 修改：

```json
{
    "api_key": "your-minimax-api-key-here",
    "host": "0.0.0.0",
    "port": 8888
}
```

| 参数 | 说明 |
|:---|:---|
| api_key | LLM 适配器 API 密钥 |
| host | 监听地址（0.0.0.0=所有网卡） |
| port | 端口号 |

## API接口

| 接口 | 方法 | 说明 |
|:---|:---|:---|
| `/` | GET | 健康检查 |
| `/chat` | POST | 文字对话 |
| `/voice_upload` | POST | 语音识别对话（麦克风） |
| `/clear` | POST | 清除对话历史 |

## UE蓝图对接示例

```
POST: http://localhost:8888/chat
Body: {"text": "你的问题"}
```

## 使用流程

1. 双击 `AI_Service_Start.exe` 启动服务
2. 双击 `AI_Chat.exe` 进行交互测试
3. UE蓝图通过HTTP请求调用服务

## 项目迁移

拷贝 `AI_VoiceService.exe` 和 `config.json` 到UE项目目录即可。
