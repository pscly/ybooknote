"""Markdown YAML frontmatter 读写。"""
from __future__ import annotations

from pathlib import Path

import yaml

DELIM = "---"


def parse(text: str) -> tuple[dict, str]:
    """返回 (meta, body)。无 frontmatter 时 meta={} 。"""
    if text.startswith(DELIM):
        lines = text.splitlines()
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == DELIM:
                end = i
                break
        if end is not None:
            meta_text = "\n".join(lines[1:end])
            body = "\n".join(lines[end + 1:])
            meta = yaml.safe_load(meta_text) or {}
            return meta, body.lstrip("\n")
    return {}, text


def dump(meta: dict, body: str) -> str:
    meta_text = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"{DELIM}\n{meta_text}\n{DELIM}\n\n{body.strip()}\n"


def read_file(path: str | Path) -> tuple[dict, str]:
    return parse(Path(path).read_text(encoding="utf-8"))


def write_file(path: str | Path, meta: dict, body: str) -> None:
    Path(path).write_text(dump(meta, body), encoding="utf-8")
