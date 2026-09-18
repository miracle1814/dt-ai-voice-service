#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI语音服务 交互工具"""
import requests
import sys
import os
import wave
import threading
import time
import json

# 加载配置
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
EXE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"host": "localhost", "port": 8888}

CONFIG = load_config()
SERVICE_HOST = CONFIG.get("host", "0.0.0.0").replace("0.0.0.0", "localhost")
SERVICE_PORT = CONFIG.get("port", 8888)
SERVICE_URL = f"http://{SERVICE_HOST}:{SERVICE_PORT}"

# 全局变量
is_recording = False
temp_wav = "temp_voice.wav"

def check():
    try:
        r = requests.get(SERVICE_URL, timeout=2)
        return r.status_code == 200
    except:
        return False

def record_audio():
    """录音函数"""
    import pyaudio
    
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    frames = []
    
    global is_recording
    while is_recording:
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    with wave.open(temp_wav, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

def chat():
    """文字交互"""
    print("\n[文字模式] 输入内容发送，输入 q 返回")
    print("-" * 40)
    while True:
        try:
            msg = input("\n你: ").strip()
            if msg.lower() == "q":
                break
            if not msg:
                continue
            r = requests.post(f"{SERVICE_URL}/chat", json={"text": msg}, timeout=30)
            data = r.json()
            if data.get("success"):
                print(f"\nAI: {data.get('ai_reply', '')}")
            else:
                print(f"\n错误: {data.get('error', '未知错误')}")
        except Exception as e:
            print(f"\n请求失败: {e}")

def voice():
    """语音交互"""
    global is_recording
    
    print("\n[语音模式]")
    print("  按回车开始录音，再按回车停止")
    print("-" * 40)
    
    while True:
        try:
            cmd = input("\n按回车开始录音 (q返回): ").strip()
            if cmd.lower() == "q":
                break
            
            print("  [录音中...] 按回车停止")
            is_recording = True
            threading.Thread(target=record_audio, daemon=True).start()
            
            input()
            
            is_recording = False
            time.sleep(0.3)
            
            print("  [识别中...]")
            with open(temp_wav, "rb") as f:
                files = {"file": ("voice.wav", f, "audio/wav")}
                r = requests.post(f"{SERVICE_URL}/voice_upload", files=files, timeout=60)
                data = r.json()
            
            if data.get("success"):
                print(f"\n  识别: {data.get('text', '')}")
                print(f"  AI: {data.get('reply', '')}")
            else:
                print(f"\n  错误: {data.get('error', '未知错误')}")
                
        except FileNotFoundError:
            print("  错误: 未检测到麦克风")
        except Exception as e:
            print(f"\n错误: {e}")

def main():
    print("=" * 40)
    print("   AI语音服务 V2.4 - 交互工具")
    print(f"   服务地址: {SERVICE_URL}")
    print("=" * 40)
    
    if not check():
        print("\n[X] 服务未启动!")
        print(f"   请先运行 AI_Service_Start.exe")
        input("\n按回车键退出...")
        return
    
    print(f"\n[OK] 已连接: {SERVICE_URL}")
    
    while True:
        print("\n" + "=" * 40)
        print("  1. 文字交互")
        print("  2. 语音交互 (麦克风)")
        print("  3. 清除对话历史")
        print("  q. 退出")
        print("=" * 40)
        
        choice = input("\n请选择: ").strip()
        
        if choice == "1":
            chat()
        elif choice == "2":
            voice()
        elif choice == "3":
            try:
                requests.post(f"{SERVICE_URL}/clear", timeout=5)
                print("\n[OK] 对话历史已清除")
            except:
                print("\n[X] 清除失败")
        elif choice.lower() == "q":
            print("\n再见!")
            break
        else:
            print("\n无效选择")

if __name__ == "__main__":
    main()
