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


def _chapters_doc_body(entry: dict) -> str:
    """分章笔记文档：目录 + 各章正文（标题下移一级，去 NAV）。"""
    notes_dir = config.ROOT / entry["notes"]["dir"]
    ch_dir = notes_dir / "chapters"
    ch_files = sorted((p for p in ch_dir.glob("*.md")), key=_chapter_sort_key) if ch_dir.exists() else []
    if not ch_files:
        return ""
    titles = []
    bodies = []
    for p in ch_files:
        body = _clean_body(p)
        # 取该章 H1 作目录项
        h1 = next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), p.stem)
        titles.append(h1)
        bodies.append(_demote(body, 1))   # 「# 第N章」→「## 第N章」
    toc = "\n".join(f"- {t}" for t in titles)
    return f"# 分章笔记\n\n## 目录\n{toc}\n\n---\n\n" + "\n\n---\n\n".join(bodies) + "\n"


def build_tree_plan(entry: dict) -> dict:
    """生成嵌套树各子文档正文文件，返回计划 dict。"""
    notebook = config.env("SIYUAN_NOTEBOOK_ID")
    target = (config.env("SIYUAN_TARGET_PATH") or "/ai辅助").rstrip("/")
    book_title = sanitize_dirname(entry["title"])
    base = f"{target}/{book_title}"
    source_epub = (config.ROOT / entry["source"]["path"]).resolve()
    notes_dir = config.ROOT / entry["notes"]["dir"]

    out = source_epub.parent / ".cache" / "siyuan"
    out.mkdir(parents=True, exist_ok=True)

    children = []
    summary = notes_dir / "summary.md"
    if summary.exists():
        b = _drop_first_h1(_clean_body(summary))
        f = out / "全书总览.md"
        f.write_text(b, encoding="utf-8")
        children.append({"sub": "全书总览", "hpath": f"{base}/全书总览", "body_file": str(f), "icon": "1f4d1", "chars": len(b)})
    hl = notes_dir / "highlights.md"
    if hl.exists():
        b = _drop_first_h1(_clean_body(hl))
        f = out / "摘录与金句.md"
        f.write_text(b, encoding="utf-8")
        children.append({"sub": "摘录与金句", "hpath": f"{base}/摘录与金句", "body_file": str(f), "icon": "2728", "chars": len(b)})
    cb = _chapters_doc_body(entry)
    if cb:
        f = out / "分章笔记.md"
        f.write_text(cb, encoding="utf-8")
        children.append({"sub": "分章笔记", "hpath": f"{base}/分章笔记", "body_file": str(f), "icon": "1f4da", "chars": len(cb)})

    plan = {
        "book_id": entry["book_id"],
        "title": entry["title"],
        "author": entry.get("author", ""),
        "tags": entry.get("tags", []),
        "notebook_id": notebook,
        "base_hpath": base,
        "icon": "1f4d6",
        "epub_path": str(source_epub),
        "existing_parent_id": entry.get("siyuan_doc_id"),
        "existing_asset": entry.get("siyuan_asset"),
        "children": children,
    }
    (out / "tree-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan


def _parent_md(plan: dict, asset: str | None) -> str:
    tags = "、".join(plan.get("tags") or []) or "—"
    lines = [
        f"> 📖 **{plan['title']}**　作者：{plan.get('author') or '—'}",
        f"> 标签：{tags}",
        "",
    ]
    if asset:
        lines.append(f"> 📎 原书 epub：[{plan['title']}·source.epub]({asset})")
    lines.append("> 📚 GitHub 全文：https://github.com/pscly/ybooknote")
    lines.append("")
    lines.append("## 本书笔记（见下方子文档）")
    for c in plan["children"]:
        lines.append(f"- **{c['sub']}**")
    lines.append("")
    lines.append("> 提示：展开左侧文档树即可在「全书总览 / 摘录与金句 / 分章笔记」之间跳转。")
    return "\n".join(lines)


def cmd_tree(needle: str) -> int:
    data = index.load()
    entry = index.find_one(data, needle)
    if not entry:
        print(f"未找到唯一匹配的书: '{needle}'")
        return 2
    plan = build_tree_plan(entry)
    print(f"=== SiYuan 嵌套树计划：{entry['title']} ===")
    print(f"  父文档 : {plan['base_hpath']}  既有父id={plan['existing_parent_id'] or '无'}")
    for c in plan["children"]:
        print(f"    - {c['sub']}  ({c['chars']} 字)")
    return 0


def cmd_push(needle: str) -> int:
    """服务端经内核 API 建整棵嵌套树并记账（正文不进上下文）。"""
    import siyuan_api
    data = index.load()
    entry = index.find_one(data, needle)
    if not entry:
        print(f"未找到唯一匹配的书: '{needle}'")
        return 2
    if entry["status"] not in ("reviewed", "synced"):
        print(f"✗ 仅 reviewed/synced 可同步，当前 status={entry['status']}。先 `book.py status review <book>`。")
        return 1

    plan = build_tree_plan(entry)
    nb = plan["notebook_id"]

    # 幂等：删旧父子树
    if plan["existing_parent_id"]:
        try:
            if siyuan_api.remove_doc_by_id(plan["existing_parent_id"]):
                print(f"  已删除旧父文档 {plan['existing_parent_id']}")
        except Exception as exc:
            print(f"  删除旧父文档失败（忽略）: {exc}")

    # 附件（复用已有）
    asset = plan["existing_asset"]
    if not asset:
        asset = siyuan_api.upload_asset(plan["epub_path"])
        print(f"  上传 epub → {asset}")

    # 父文档
    parent_id = siyuan_api.create_doc(nb, plan["base_hpath"], _parent_md(plan, asset))
    siyuan_api.set_icon(parent_id, plan["icon"])
    print(f"  父文档 {parent_id}  📖  {plan['base_hpath']}")

    # 子文档
    for c in plan["children"]:
        md = Path(c["body_file"]).read_text(encoding="utf-8")
        cid = siyuan_api.create_doc(nb, c["hpath"], md)
        siyuan_api.set_icon(cid, c.get("icon", "1f4d1"))
        print(f"    + {c['sub']}  {cid}  ({c['chars']} 字)")

    cmd_record(needle, parent_id, asset)
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
    notes_dir = config.ROOT / entry["notes"]["dir"]
    for fname in ("summary.md", "highlights.md"):
        fp = notes_dir / fname
        if fp.exists():
            meta, body = frontmatter.read_file(fp)
            meta["status"] = "synced"
            frontmatter.write_file(fp, meta, body)
    index.save(data)
    print(f"✅ 已记账：{entry['title']} → synced  parent_doc={doc_id}  asset={asset or '—'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    config.enable_utf8_console()
    parser = argparse.ArgumentParser(description="SiYuan 嵌套树同步决策/记账")
    parser.add_argument("--plan", metavar="BOOK", help="生成嵌套树同步计划")
    parser.add_argument("--record", nargs="+", metavar=("BOOK", "DOC_ID"),
                        help="回填: BOOK PARENT_DOC_ID [ASSET]")
    parser.add_argument("book", nargs="?", help="等价于 --plan <book>")
    args = parser.parse_args(argv)

    if args.record:
        book = args.record[0]
        doc_id = args.record[1] if len(args.record) > 1 else None
        asset = args.record[2] if len(args.record) > 2 else None
        if not doc_id:
            print("用法: --record <book> <parent_doc_id> [asset]")
            return 2
        return cmd_record(book, doc_id, asset)

    target = args.plan or args.book
    if not target:
        print("用法: python book.py sync <book>")
        return 2
    return cmd_push(target)


if __name__ == "__main__":
    raise SystemExit(main())
