"""README.md 自动生成（禁止人工/AI 手改）。

遍历 1notes/*/summary.md 的 frontmatter 渲染索引表；frontmatter 缺失时回退 index.json。
链接路径做 URL 编码，确保含空格/中文/括号的目录名不破坏 Markdown 链接。
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import config, frontmatter, index

_STATUS_EMOJI = {
    "pending": "⚪ 待分析",
    "analyzing": "🔵 分析中",
    "drafted": "🟡 草稿",
    "reviewed": "🟢 已抽检",
    "synced": "✅ 已同步",
    "failed": "🔴 失败",
}

_HEADER = """<!-- 本文件由 9scripts/gen_readme.py 自动生成，请勿手改。改动会在下次生成时被覆盖。 -->

# 📚 AI 读书笔记库

> 用 AI 读书并总结，笔记为单一事实源（`1notes/`），评审通过后单向同步到 SiYuan。
> 书源不入库（版权），仅分享笔记。详见 [设计方案](设计方案.md)。
"""


def _md_link(text: str, rel_path: str) -> str:
    return f"[{text}]({quote(rel_path)})"


def _book_row(entry: dict) -> tuple:
    notes_dir = config.ROOT / entry["notes"]["dir"]
    summary = notes_dir / "summary.md"
    meta = {}
    if summary.exists():
        meta, _ = frontmatter.read_file(summary)
    title = meta.get("title") or entry["title"]
    author = meta.get("author") or entry.get("author") or "—"
    tags = meta.get("tags") or entry.get("tags") or []
    status = meta.get("status") or entry["status"]
    tag_str = "、".join(tags) if tags else "—"
    ch = entry.get("notes", {}).get("chapters_extracted", "—")
    rel = f"{entry['notes']['dir']}/summary.md"
    link = _md_link(title, rel)
    return (status, title, link, author, tag_str, ch)


def render(data: dict) -> str:
    rows = [_book_row(b) for b in data["books"]]
    rows.sort(key=lambda r: (r[0], r[1]))

    lines = [_HEADER, ""]
    total = len(rows)
    synced = sum(1 for r in rows if r[0] == "synced")
    lines.append(f"共 **{total}** 本 · 已同步 **{synced}** 本\n")
    lines.append("| 书名 | 作者 | 标签 | 状态 | 章节 |")
    lines.append("|------|------|------|------|------:|")
    for status, _title, link, author, tag_str, ch in rows:
        lines.append(f"| {link} | {author} | {tag_str} | {_STATUS_EMOJI.get(status, status)} | {ch} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    config.enable_utf8_console()
    data = index.load()
    content = render(data)
    config.README_PATH.write_text(content, encoding="utf-8")
    print(f"README.md 已生成：{len(data['books'])} 本 -> {config.README_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
