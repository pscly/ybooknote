"""路径常量与 .env 读取。

仓库根 = 本文件向上 3 层（9scripts/lib/config.py -> 9scripts/lib -> 9scripts -> ROOT）。
所有脚本一律从这里取路径，避免硬编码或靠 cwd 猜。
"""
from __future__ import annotations

import os
from pathlib import Path

_CONFIG_FILE = Path(__file__).resolve()
ROOT = _CONFIG_FILE.parents[2]

META_DIR = ROOT / "0meta"
INDEX_PATH = META_DIR / "index.json"
PROMPTS_DIR = META_DIR / "prompts"
BOOKS_DIR = ROOT / "1books"
INBOX_DIR = BOOKS_DIR / "_inbox"
NOTES_DIR = ROOT / "1notes"
SCRIPTS_DIR = ROOT / "9scripts"
README_PATH = ROOT / "README.md"
ENV_PATH = ROOT / ".env"

_env_cache: dict | None = None


def _load_env_file() -> dict:
    global _env_cache
    if _env_cache is not None:
        return _env_cache
    data: dict = {}
    if ENV_PATH.exists():
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            data[key.strip()] = val.strip()
    _env_cache = data
    return data


def env(key: str, default: str | None = None) -> str | None:
    """优先读进程环境变量，其次读 .env 文件。"""
    val = os.environ.get(key)
    if val:
        return val
    return _load_env_file().get(key, default)


def enable_utf8_console() -> None:
    """让中文在 Windows 控制台/管道下正确输出，避免 UnicodeEncodeError。

    入口脚本（book.py 及各 main）开头调用一次。
    """
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
