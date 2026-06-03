"""状态机推进（脚本治理，落实 P1）。

校验 index.TRANSITIONS 合法转移，更新 index.json 与笔记 frontmatter 的 status，二者保持一致。
`reviewed` 只能由 `drafted` 进入 —— 强制人工抽检关卡。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import config, frontmatter, index

_STATUS_EMOJI = {
    "pending": "⚪",
    "analyzing": "🔵",
    "drafted": "🟡",
    "reviewed": "🟢",
    "synced": "✅",
    "failed": "🔴",
}


def _sync_frontmatter(entry: dict, state: str) -> None:
    notes_dir = config.ROOT / entry["notes"]["dir"]
    for fname in ("summary.md", "highlights.md"):
        fp = notes_dir / fname
        if fp.exists():
            meta, body = frontmatter.read_file(fp)
            meta["status"] = state
            frontmatter.write_file(fp, meta, body)


def set_status(needle: str, state: str, error: str | None = None, force: bool = False) -> int:
    if state not in index.STATES:
        print(f"非法状态 '{state}'，合法值: {', '.join(index.STATES)}")
        return 2
    data = index.load()
    entry = index.find_one(data, needle)
    if not entry:
        print(f"未找到唯一匹配的书: '{needle}'（用 `book.py list` 查看 book_id）")
        return 2

    cur = entry["status"]
    allowed = index.TRANSITIONS.get(cur, set())
    if state != cur and state not in allowed and not force:
        print(f"✗ 拒绝转移 {cur} → {state}。允许: {sorted(allowed) or '无'}（--force 可强制）")
        return 1

    entry["status"] = state
    entry["last_error"] = error if state == "failed" else None
    entry["updated_at"] = index.now_iso()
    _sync_frontmatter(entry, state)
    index.save(data)
    print(f"{_STATUS_EMOJI.get(state, '')} {entry['title']}  [{entry['book_id']}]  {cur} → {state}")
    if error:
        print(f"   last_error: {error}")
    return 0


def print_list() -> int:
    data = index.load()
    if not data["books"]:
        print("index 为空。先 `book.py ingest`。")
        return 0
    print(f"{'状态':<10} {'book_id':<24} {'章':>4}  标题")
    print("-" * 72)
    for b in sorted(data["books"], key=lambda x: (x["status"], x["title"])):
        emoji = _STATUS_EMOJI.get(b["status"], "  ")
        ch = b.get("notes", {}).get("chapters_extracted", "?")
        label = f"{emoji} {b['status']}"
        print(f"{label:<11} {b['book_id']:<24} {ch:>4}  {b['title'][:50]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    config.enable_utf8_console()
    parser = argparse.ArgumentParser(description="查看/推进书目状态")
    parser.add_argument("state", nargs="?", help="目标状态，或 'list' 查看全部")
    parser.add_argument("book", nargs="?", help="book_id 或标题片段")
    parser.add_argument("--error", help="state=failed 时记录错误信息")
    parser.add_argument("--force", action="store_true", help="跳过转移校验")
    args = parser.parse_args(argv)

    if not args.state or args.state == "list":
        return print_list()
    if not args.book:
        print("用法: book.py status <state> <book>   或   book.py status list")
        return 2
    return set_status(args.book, args.state, error=args.error, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
