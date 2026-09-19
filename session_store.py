#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多会话对话历史管理。

V2.4 是单一全局历史；V2.5 起按 session_id 隔离 —— UE 侧每个客户端/每块大屏
用自己的 session_id，互不串话。不传 session_id 的旧调用自动落到 "default"
会话，与 V2.4 行为兼容。
"""
import threading

MAX_SESSIONS = 50          # 最多同时保留多少个会话（FIFO 淘汰最旧的）
MAX_HISTORY_TURNS = 10     # 每个会话最多保留多少轮对话


class SessionStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._histories = {}   # session_id -> [{"role": ..., "content": ...}, ...]

    def get_history(self, session_id: str) -> list:
        with self._lock:
            return list(self._histories.get(session_id, []))

    def append(self, session_id: str, user_text: str, ai_reply: str):
        with self._lock:
            if session_id not in self._histories and len(self._histories) >= MAX_SESSIONS:
                oldest = next(iter(self._histories))
                self._histories.pop(oldest, None)
            history = self._histories.setdefault(session_id, [])
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": ai_reply})
            if len(history) > MAX_HISTORY_TURNS * 2:
                del history[: len(history) - MAX_HISTORY_TURNS * 2]

    def clear(self, session_id: str = "") -> int:
        """清空指定会话；不传 session_id 清空全部（兼容 V2.4 语义）。返回清掉的会话数。"""
        with self._lock:
            if session_id:
                return 1 if self._histories.pop(session_id, None) is not None else 0
            n = len(self._histories)
            self._histories.clear()
            return n

    def stats(self) -> dict:
        with self._lock:
            return {"sessions": len(self._histories),
                    "total_messages": sum(len(h) for h in self._histories.values())}
