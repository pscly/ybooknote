"""SiYuan 单向幂等同步的「决策 + 记账」端。

分工（符合 P1/P5）：
- 本脚本（确定性）：校验 reviewed、组装正文、给出 CREATE/UPDATE 决策、回填 index。
- Claude Code（经 SiYuan MCP）：据决策建/更文档、设图标、上传 epub 附件、写正文，回收 doc_id/asset。

  python 9scripts/sync_siyuan.py --plan <book>
  python 9scripts/sync_siyuan.py --record <book> <doc_id> [asset_path]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import config, frontmatter, index
from lib.textutil import sanitize_dirname


import re as _re

_NAV_RE = _re.compile(r"<!-- NAV:START.*?<!-- NAV:END -->", _re.S)


def _clean_body(path) -> str:
    """读 md，去 frontmatter、去 NAV 导航块（SiYuan 里相对链接无效）。"""
    _, body = frontmatter.read_file(path)
    return _NAV_RE.sub("", body).strip()


def _drop_first_h1(body: str) -> str:
    lines = body.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            return "\n".join(lines[:i] + lines[i + 1:]).strip()
    return body


def _demote(body: str, levels: int = 1) -> str:
    out = []
    for ln in body.splitlines():
        m = _re.match(r"(#{1,6})(\s)", ln)
        out.append("#" * levels + ln if m else ln)
    return "\n".join(out)


def _chapter_sort_key(p):
    m = _re.match(r"(\d+)", p.name)
    return (int(m.group(1)) if m else 9999, p.name)


def _assemble_body(entry: dict, include_chapters: bool = True) -> str:
    notes_dir = config.ROOT / entry["notes"]["dir"]
    parts: list[str] = []

    summary = notes_dir / "summary.md"
    if summary.exists():
        body = _drop_first_h1(_clean_body(summary))
        if body and not body.startswith("<!--"):
            parts.append("# 全书总览\n\n" + body)

    hl = notes_dir / "highlights.md"
    if hl.exists():
        body = _drop_first_h1(_clean_body(hl))
        if body and not body.startswith("<!--"):
            parts.append("# 摘录与金句\n\n" + body)

    if include_chapters:
        ch_dir = notes_dir / "chapters"
        ch_files = sorted((p for p in ch_dir.glob("*.md")), key=_chapter_sort_key) if ch_dir.exists() else []
        if ch_files:
            chap_parts = ["# 分章笔记"]
            for p in ch_files:
                # 章节 H1「# 第N章」→「## 第N章」，内部 ## → ###，统一收进“分章笔记”
                chap_parts.append(_demote(_clean_body(p), 1))
            parts.append("\n\n".join(chap_parts))

    return "\n\n".join(p for p in parts if p).strip() + "\n"


def cmd_plan(needle: str) -> int:
    data = index.load()
    entry = index.find_one(data, needle)
    if not entry:
        print(f"未找到唯一匹配的书: '{needle}'")
        return 2
    if entry["status"] != "reviewed":
        print(f"✗ 仅 reviewed 可同步，当前 status={entry['status']}。先 `book.py status review <book>`。")
        return 1

    notebook = config.env("SIYUAN_NOTEBOOK_ID")
    target = (config.env("SIYUAN_TARGET_PATH") or "/ai辅助").rstrip("/")
    doc_title = sanitize_dirname(entry["title"])
    hpath = f"{target}/{doc_title}"
    source_epub = (config.ROOT / entry["source"]["path"]).resolve()

    body = _assemble_body(entry)
    cache = source_epub.parent / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    body_path = cache / "siyuan-body.md"
    body_path.write_text(body, encoding="utf-8")

    action = "UPDATE" if entry.get("siyuan_doc_id") else "CREATE"
    plan = {
        "action": action,
        "book_id": entry["book_id"],
        "notebook_id": notebook,
        "hpath": hpath,
        "doc_title": doc_title,
        "icon": "1f4d6",  # 📖
        "siyuan_doc_id": entry.get("siyuan_doc_id"),
        "body_file": str(body_path),
        "need_upload_epub": not entry.get("siyuan_asset"),
        "epub_path": str(source_epub),
        "siyuan_asset": entry.get("siyuan_asset"),
    }
    plan_path = cache / "siyuan-plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== SiYuan 同步决策：{action} ===")
    print(f"  book_id      : {entry['book_id']}")
    print(f"  notebook_id  : {notebook}")
    print(f"  目标 hpath   : {hpath}")
    print(f"  图标         : 📖 (1f4d6)")
    if action == "UPDATE":
        print(f"  既有 doc_id  : {entry['siyuan_doc_id']}（走更新，不新建）")
    print(f"  正文文件     : {body_path}  ({len(body)} 字)")
    print(f"  上传 epub    : {'是' if plan['need_upload_epub'] else '否（已存 '+str(entry.get('siyuan_asset'))+'）'}")
    print(f"  epub 路径    : {source_epub}")
    print(f"  plan.json    : {plan_path}")
    print("\n下一步（Claude 经 SiYuan MCP 执行）：")
    if action == "CREATE":
        print("  1) document.create(notebook, parentPath=目标文件夹, title=doc_title, markdown=正文)")
        print("  2) 设 📖 图标；need_upload_epub 时 file.upload_asset(epub) 并在文首插入「📎 原书」链接")
        print("  3) 回收 docId/asset → python 9scripts/sync_siyuan.py --record <book> <docId> <asset>")
    else:
        print("  1) 用既有 doc_id 覆盖正文（fs.write overwrite 或 block 更新）")
        print("  2) epub 已传则不重传；回收后 --record 更新状态")
    return 0


def cmd_record(needle: str, doc_id: str, asset: str | None) -> int:
    data = index.load()
    entry = index.find_one(data, needle)
    if not entry:
        print(f"未找到唯一匹配的书: '{needle}'")
        return 2
    entry["siyuan_doc_id"] = doc_id
    if asset:
        entry["siyuan_asset"] = asset
    entry["status"] = "synced"
    entry["last_error"] = None
    entry["updated_at"] = index.now_iso()
    # 同步 frontmatter 状态
    notes_dir = config.ROOT / entry["notes"]["dir"]
    for fname in ("summary.md", "highlights.md"):
        fp = notes_dir / fname
        if fp.exists():
            meta, body = frontmatter.read_file(fp)
            meta["status"] = "synced"
            frontmatter.write_file(fp, meta, body)
    index.save(data)
    print(f"✅ 已记账：{entry['title']} → synced  doc_id={doc_id}  asset={asset or '—'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    config.enable_utf8_console()
    parser = argparse.ArgumentParser(description="SiYuan 同步决策/记账")
    parser.add_argument("--plan", metavar="BOOK", help="生成同步决策与正文")
    parser.add_argument("--record", nargs="+", metavar=("BOOK", "DOC_ID"),
                        help="回填: BOOK DOC_ID [ASSET]")
    # 位置参数兜底：`sync <book>` 等价于 `--plan <book>`
    parser.add_argument("book", nargs="?", help="等价于 --plan <book>")
    args = parser.parse_args(argv)

    if args.record:
        book = args.record[0]
        doc_id = args.record[1] if len(args.record) > 1 else None
        asset = args.record[2] if len(args.record) > 2 else None
        if not doc_id:
            print("用法: --record <book> <doc_id> [asset]")
            return 2
        return cmd_record(book, doc_id, asset)

    target = args.plan or args.book
    if not target:
        print("用法: python book.py sync <book>")
        return 2
    return cmd_plan(target)


if __name__ == "__main__":
    raise SystemExit(main())
