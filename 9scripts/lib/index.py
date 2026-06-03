"""index.json（系统大脑）原子读写与查询。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from . import config

SCHEMA_VERSION = 1

# 状态机：合法状态与允许的转移
STATES = ["pending", "analyzing", "drafted", "reviewed", "synced", "failed"]
TRANSITIONS = {
    "pending": {"analyzing", "failed"},
    "analyzing": {"drafted", "failed", "pending"},
    "drafted": {"reviewed", "analyzing", "failed"},
    "reviewed": {"synced", "drafted", "failed"},
    "synced": {"drafted", "analyzing"},   # 书变更后可回退重跑
    "failed": {"pending", "analyzing"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load() -> dict:
    if config.INDEX_PATH.exists():
        return json.loads(config.INDEX_PATH.read_text(encoding="utf-8"))
    return {"schema_version": SCHEMA_VERSION, "books": []}


def save(data: dict) -> None:
    config.META_DIR.mkdir(parents=True, exist_ok=True)
    tmp = config.INDEX_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, config.INDEX_PATH)


def find_by_book_id(data: dict, book_id: str) -> dict | None:
    return next((b for b in data["books"] if b.get("book_id") == book_id), None)


def find_by_hash(data: dict, sha256: str) -> dict | None:
    return next((b for b in data["books"] if b.get("source", {}).get("sha256") == sha256), None)


def find_by_kavita_id(data: dict, kid) -> dict | None:
    return next((b for b in data["books"] if (b.get("kavita") or {}).get("id") == kid), None)


def find_one(data: dict, needle: str) -> dict | None:
    """按 book_id 精确，否则按标题/目录名模糊匹配（CLI 友好）。"""
    exact = find_by_book_id(data, needle)
    if exact:
        return exact
    hits = [
        b for b in data["books"]
        if needle in (b.get("title") or "") or needle in (b.get("notes", {}).get("dir") or "")
    ]
    return hits[0] if len(hits) == 1 else None
