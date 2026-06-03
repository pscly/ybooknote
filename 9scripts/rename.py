"""重命名一本书（脚本治理移动，符合 P1）。

改 title 与磁盘目录名（1books/<新名>、1notes/<新名>），更新 index 路径与笔记 frontmatter。
book_id 保持稳定（由 sha 派生，不随书名变），避免破坏既有引用。

  python book.py rename <book> "<新书名>"
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import config, frontmatter, index
from lib.textutil import sanitize_dirname


def _unique_dirname(new_title: str, book_id: str, data: dict) -> str:
    base = sanitize_dirname(new_title)
    short = book_id.rsplit("-", 1)[-1]
    used = {
        b["notes"]["dir"].rsplit("/", 1)[-1]
        for b in data["books"]
        if b.get("book_id") != book_id
    }
    if base in used:
        return f"{base}-{short}"
    return base


def main(argv: list[str] | None = None) -> int:
    config.enable_utf8_console()
    parser = argparse.ArgumentParser(description="重命名一本书（书名+目录）")
    parser.add_argument("book", help="book_id 或现书名片段")
    parser.add_argument("title", help="新书名")
    args = parser.parse_args(argv)

    data = index.load()
    entry = index.find_one(data, args.book)
    if not entry:
        print(f"未找到唯一匹配的书: '{args.book}'（用 book.py list 查看）")
        return 2

    new_title = args.title.strip()
    new_dir = _unique_dirname(new_title, entry["book_id"], data)
    old_dir = entry["notes"]["dir"].rsplit("/", 1)[-1]

    if new_dir == old_dir and new_title == entry["title"]:
        print("书名与目录均未变化，无需操作。")
        return 0

    # 移动 1books 与 1notes 目录（确定性、破坏性 → 脚本负责）
    for top in ("1books", "1notes"):
        src = config.ROOT / top / old_dir
        dst = config.ROOT / top / new_dir
        if src.exists():
            if dst.exists():
                print(f"✗ 目标已存在: {dst}")
                return 1
            shutil.move(str(src), str(dst))

    # 更新 index
    entry["title"] = new_title
    entry["source"]["path"] = f"1books/{new_dir}/source.epub"
    entry["notes"]["dir"] = f"1notes/{new_dir}"
    entry["updated_at"] = index.now_iso()
    index.save(data)

    # 更新笔记 frontmatter 的 title
    notes_dir = config.ROOT / entry["notes"]["dir"]
    for fname in ("summary.md", "highlights.md"):
        fp = notes_dir / fname
        if fp.exists():
            meta, body = frontmatter.read_file(fp)
            meta["title"] = new_title
            frontmatter.write_file(fp, meta, body)

    print(f"✅ 已重命名：{old_dir}")
    print(f"            → {new_dir}")
    print(f"   标题: {new_title}  [book_id 不变: {entry['book_id']}]")
    print("   记得跑 `python book.py readme` 刷新导航/索引。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
