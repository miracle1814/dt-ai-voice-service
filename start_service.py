#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI语音服务 启动器"""
import subprocess
import time
import os
import sys
import json

EXE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(EXE_DIR, "config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"host": "0.0.0.0", "port": 8888}

CONFIG = load_config()
EXE_PATH = os.path.join(EXE_DIR, "AI_VoiceService.exe")
SERVICE_HOST = CONFIG.get("host", "0.0.0.0").replace("0.0.0.0", "localhost")
SERVICE_PORT = CONFIG.get("port", 8888)
SERVICE_URL = f"http://{SERVICE_HOST}:{SERVICE_PORT}"

def check():
    import requests
    try:
        return requests.get(SERVICE_URL, timeout=2).status_code == 200
    except:
        return False

def main():
    print("=" * 40)
    print("   数字孪生AI语音服务 V2.4")
    print("=" * 40)
    print(f"   服务地址: {SERVICE_URL}")
    print()
    
    if check():
        print(f"[OK] 服务已在运行: {SERVICE_URL}")
        print()
        input("按回车键退出...")
        return
    
    print("[*] 正在启动服务...")
    subprocess.Popen(
        f'start "" /b "{EXE_PATH}"',
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    for i in range(10):
        time.sleep(1)
        if check():
            print()
            print(f"[OK] 服务已启动!")
            print(f"     访问地址: {SERVICE_URL}")
            print()
            print("   测试命令:")
            print(f'   curl -X POST {SERVICE_URL}/chat -H "Content-Type: application/json" -d "{{\\"text\\":\\"你好\\"}}"')
            print()
            print("   按 Ctrl+C 停止服务")
            print("   关闭此窗口 = 退出")
            print()
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print()
                print("[*] 正在停止服务...")
                subprocess.run('powershell -Command "Get-Process -Name AI_VoiceService -EA SilentlyContinue | Stop-Process -Force"', shell=True)
                print("[OK] 服务已停止")
                return
    print("[X] 启动失败!")
    input("按回车键退出...")

if __name__ == "__main__":
    main()
