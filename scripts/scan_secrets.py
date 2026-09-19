#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_secrets.py —— 提交前敏感信息扫描（防密钥/业务数据/隐私误入库）。

用法：
    python scripts/scan_secrets.py            # 扫描待提交内容（全仓）
    python scripts/scan_secrets.py --staged   # 只扫 git staged 文件（配 pre-commit 用）

退出码：0 = 干净；1 = 命中敏感项（提交前必须处理）。
命中处理原则：密钥换真实值来源（环境变量/config.json）；业务与私人数据不入仓。
"""
import os
import re
import subprocess
import sys

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(R)

# ---- 规则：每条 = (说明, 正则) 。误报可加 allowlist 白名单（见文末）。----
RULES = [
    ("通用密钥赋值",        r"""(api[_-]?key|secret|access[_-]?key|app[_-]?secret)\s*[:=]\s*["'][A-Za-z0-9_\-]{16,}["']""", ),
    ("云厂商AK形态",        r"""\b(LTAI[A-Za-z0-9]{12,}|AKID[A-Za-z0-9]{16,})\b"""),
    ("Bearer 长令牌",       r"""Bearer\s+[A-Za-z0-9_\-\.]{24,}"""),
    ("JWT 形态",            r"""eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\."""),
    ("私钥块",              r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ("内网地址/端口组合",   r"""(mysql|redis|jdbc)[^\n]{0,40}(password|passwd|pwd)\s*[:=]\s*\S+""", ),
    ("手机号",              r"\b1[3-9]\d{9}\b"),
    ("身份证号",            r"\b\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b"),
]

# ---- 误报白名单：命中这些 pattern 的行视为干净（例如文档占位符）----
ALLOWLIST_PATTERNS = [
    r"your-llm-api-key", r"你的", r"占位", r"placeholder", r"example",
    r"\$\{", r"xxx+", r"\*\*\*",
]
ALLOWLIST = [re.compile(p, re.I) for p in ALLOWLIST_PATTERNS]

# ---- 永不扫描/永不入库的文件 ----
SKIP_FILES = {"config.json", ".pwd", "secrets.json", "audio_cache", "__pycache__", ".git",
              "scan_terms.local.txt"}  # 本地业务词库自身也要跳过，否则自己扫自己必命中
SKIP_EXT = {".mp3", ".wav", ".png", ".jpg", ".zip", ".exe", ".onnx", ".bin"}

# ---- 本地业务标识词库（可选，不入库）----
# 用途：把实际项目独有的业务词（项目名/人名/内部代号等）放在 scripts/scan_terms.local.txt，
# 每行一个词。本脚本加载它做额外扫描，从而拦截"业务数据/用户信息"入库。
# 该词库文件已被 .gitignore 排除 —— 词本身也是隐私，绝不随仓库发布。
LOCAL_TERMS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scan_terms.local.txt")


def load_local_terms() -> list:
    try:
        with open(LOCAL_TERMS_FILE, "r", encoding="utf-8") as f:
            terms = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        return terms
    except OSError:
        return []


def iter_files(only_staged: bool):
    if only_staged:
        out = subprocess.run(["git", "diff", "--cached", "--name-only", "-z"],
                             capture_output=True, text=True)
        names = [n for n in out.stdout.split("\0") if n]
    else:
        names = []
        for root, dirs, files in os.walk(R):
            dirs[:] = [d for d in dirs if d not in SKIP_FILES]
            for fn in files:
                names.append(os.path.relpath(os.path.join(root, fn), R))
    for rel in sorted(set(names)):
        ext = os.path.splitext(rel)[1].lower()
        if ext in SKIP_EXT or os.path.basename(rel) in SKIP_FILES:
            continue
        if any(part in SKIP_FILES for part in rel.replace("\\", "/").split("/")[:-1]):
            continue
        yield rel


def scan(only_staged: bool) -> int:
    local_terms = load_local_terms()
    if local_terms:
        print(f"  [i] 已加载本地业务标识词库 {len(local_terms)} 条（不入库）")
    hits = 0
    for rel in iter_files(only_staged):
        try:
            with open(rel, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue
        for no, line in enumerate(lines, 1):
            if any(a.search(line) for a in ALLOWLIST):
                continue
            for desc, pattern in [(r[0], r[1]) for r in RULES]:
                if re.search(pattern, line):
                    print(f"  ❌ [{desc}] {rel}:{no}")
                    print(f"     {line.strip()[:110]}")
                    hits += 1
            for term in local_terms:
                if term in line:
                    print(f"  ❌ [业务标识词: {term[:4]}***] {rel}:{no}")
                    print(f"     {line.strip()[:110]}")
                    hits += 1
    print("=" * 60)
    if hits:
        print(f"❌ 命中 {hits} 处疑似敏感信息 —— 提交前必须处理（换占位符/移出仓库）")
        return 1
    print("✅ 未发现敏感信息（规则 %d 条 + 本地词库 %d 条；仅静态扫描，关键文件请再人工过目）"
          % (len(RULES), len(local_terms)))
    return 0


if __name__ == "__main__":
    sys.exit(scan(only_staged="--staged" in sys.argv))
