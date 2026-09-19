#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI语音服务 启动器。

双模式：
  1. 源码模式（默认）：直接用当前 Python 启动 voice_service.py —— 开发/开源场景；
  2. EXE 模式：源码不存在而同级有 AI_VoiceService.exe 时启动它 —— PyInstaller 打包交付场景。
"""
import json
import os
import subprocess
import sys
import time

EXE_DIR = os.path.dirname(os.path.abspath(__file__))
EXE_PATH = os.path.join(EXE_DIR, "AI_VoiceService.exe")
SRC_PATH = os.path.join(EXE_DIR, "voice_service.py")
CONFIG_FILE = os.path.join(EXE_DIR, "config.json")


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"host": "0.0.0.0", "port": 8888}


CONFIG = load_config()
SERVICE_HOST = str(CONFIG.get("host", "0.0.0.0")).replace("0.0.0.0", "localhost")
SERVICE_PORT = int(CONFIG.get("port", 8888))
SERVICE_URL = f"http://{SERVICE_HOST}:{SERVICE_PORT}"


def check():
    import requests
    try:
        return requests.get(SERVICE_URL, timeout=2).status_code == 200
    except Exception:
        return False


def spawn():
    if not os.path.exists(SRC_PATH) and os.path.exists(EXE_PATH):
        subprocess.Popen([EXE_PATH], cwd=EXE_DIR,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    subprocess.Popen([sys.executable, SRC_PATH], cwd=EXE_DIR,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    print("=" * 40)
    print("   数字孪生AI语音服务 V2.5")
    print("=" * 40)
    print(f"   服务地址: {SERVICE_URL}")
    print()

    if check():
        print(f"[OK] 服务已在运行: {SERVICE_URL}")
        input("按回车键退出...")
        return

    print("[*] 正在启动服务...")
    spawn()

    for _ in range(30):
        time.sleep(1)
        if check():
            print()
            print("[OK] 服务已启动!")
            print(f"     访问地址: {SERVICE_URL}")
            print()
            print("   测试命令:")
            print(f'   curl -X POST {SERVICE_URL}/chat -H "Content-Type: application/json" -d "{{\\"text\\":\\"你好\\"}}"')
            print(f'   curl {SERVICE_URL}/tts/voices')
            print()
            print("   按 Ctrl+C 停止服务")
            print()
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print()
                print("[*] 正在停止服务...")
                subprocess.run(
                    'powershell -Command "Get-Process -Name AI_VoiceService -EA SilentlyContinue | Stop-Process -Force"',
                    shell=True,
                )
                print("[OK] 服务已停止（源码模式请同时关闭 voice_service 进程）")
                return
    print("[X] 启动失败! 请手动运行: python voice_service.py 查看报错")
    input("按回车键退出...")


if __name__ == "__main__":
    main()
