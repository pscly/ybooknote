"""文件哈希：判断书是否变更 -> 是否需重跑分析。"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def short_hash(hexdigest: str, n: int = 6) -> str:
    return hexdigest[:n]
