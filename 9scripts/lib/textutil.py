"""文本工具：book_id 生成（ASCII 稳定）与磁盘目录名净化（保留中文，去非法字符）。"""
from __future__ import annotations

import re
import unicodedata

# Windows/通用文件系统保留字符
_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slugify(title: str) -> str:
    """转 ASCII slug；纯中文标题会得到空串（由 make_book_id 兜底为 'book'）。"""
    if not title:
        return ""
    norm = unicodedata.normalize("NFKD", title)
    ascii_str = norm.encode("ascii", "ignore").decode("ascii").lower()
    ascii_str = re.sub(r"[^a-z0-9]+", "-", ascii_str)
    return ascii_str.strip("-")


def make_book_id(title: str, short: str) -> str:
    """book_id = slug(title 或 'book') + '-' + sha256 前 6 位，作为稳定逻辑主键。"""
    base = slugify(title) or "book"
    # 限制 slug 长度，避免过长目录/键
    base = base[:48].strip("-") or "book"
    return f"{base}-{short}"


def sanitize_dirname(title: str) -> str:
    """磁盘目录名：保留中文，仅去掉文件系统非法字符与首尾点/空格。"""
    name = _ILLEGAL_RE.sub("", title or "")
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(". ")
    return name or "untitled"
