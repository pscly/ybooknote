"""SiYuan 嵌套树同步：每章独立文档 + 块引用互链 + 标签 + 读书馆选书页。

分工（符合 P1/P5）：
- 本脚本（确定性）：校验 reviewed、按 1notes 多文档结构建/重建 SiYuan 嵌套树、
  注入块引用导航、打标签、建读书馆、回填 index。正文从磁盘读取，不进 Claude 上下文。
- 章节顺序用内核 changeSort 锁定，与笔记本排序模式无关。

  python book.py sync <book>                 # 单本：幂等重建整棵树
  python 9scripts/sync_siyuan.py --plan <book>   # 预览计划（不写 SiYuan）
  python 9scripts/sync_siyuan.py --shelf         # 建/刷新「读书馆」分类选书页
  python 9scripts/sync_siyuan.py --record <book> <parent_doc_id> [asset]  # 仅回填
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import config, frontmatter, index
from lib.textutil import sanitize_dirname

_NAV_RE = re.compile(r"<!-- NAV:START.*?<!-- NAV:END -->", re.S)
# 章节 md 尾部偶有游离的占位链接 [text](.../ybooknote)，同步时一并去掉
_TRAIL_LINK_RE = re.compile(r"^\s*\[text\]\(https?://[^)]*\)\s*$", re.M)

ICON_BOOK = "1f4d6"       # 📖 父文档
ICON_SUMMARY = "1f4d1"    # 📑 全书总览
ICON_HIGHLIGHTS = "2728"  # ✨ 摘录与金句
ICON_CHAPTERS = "1f4da"   # 📚 分章笔记 / 读书馆
ICON_CHAPTER = "1f4c4"    # 📄 单章


# ───────────────────────── 文本清洗 ─────────────────────────

def _clean_body(path) -> str:
    """读 md，去 frontmatter、去 NAV 导航块、去尾部游离占位链接。"""
    _, body = frontmatter.read_file(path)
    body = _NAV_RE.sub("", body)
    body = _TRAIL_LINK_RE.sub("", body)
    return body.strip()


def _first_h1(body: str) -> str | None:
    for ln in body.splitlines():
        if ln.startswith("# "):
            return ln[2:].strip()
    return None


def _drop_first_h1(body: str) -> str:
    lines = body.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            return "\n".join(lines[:i] + lines[i + 1:]).strip()
    return body


def _chapter_sort_key(p):
    m = re.search(r"(\d+)", p.name)
    return (int(m.group(1)) if m else 9999, p.name)


def _ref(block_id: str, anchor: str) -> str:
    """块引用：((id "锚文本"))，锚文本内双引号降级为单引号、去换行。"""
    anchor = (anchor or "").replace('"', "'").replace("\n", " ").strip()
    return f'(({block_id} "{anchor}"))'


# ───────────────────────── 计划组装 ─────────────────────────

def _read_meta(entry: dict) -> tuple[list, str]:
    """从 summary.md frontmatter 读 (tags, category)；缺失回退 index 与空。"""
    notes_dir = config.ROOT / entry["notes"]["dir"]
    summary = notes_dir / "summary.md"
    tags, category = entry.get("tags") or [], ""
    if summary.exists():
        meta, _ = frontmatter.read_file(summary)
        tags = meta.get("tags") or tags
        category = meta.get("category") or ""
    return list(tags), category


def _chapter_files(entry: dict) -> list[Path]:
    notes_dir = config.ROOT / entry["notes"]["dir"]
    ch_dir = notes_dir / "chapters"
    if not ch_dir.exists():
        return []
    return sorted((p for p in ch_dir.glob("*.md")), key=_chapter_sort_key)


def build_tree_plan(entry: dict) -> dict:
    """组装嵌套树结构计划（不写 SiYuan）。正文在 push 时从磁盘按需读。"""
    notebook = config.env("SIYUAN_NOTEBOOK_ID")
    target = (config.env("SIYUAN_TARGET_PATH") or "/ai辅助").rstrip("/")
    book_title = sanitize_dirname(entry["title"])
    base = f"{target}/{book_title}"
    notes_dir = config.ROOT / entry["notes"]["dir"]
    source_epub = (config.ROOT / entry["source"]["path"]).resolve()
    tags, category = _read_meta(entry)

    summary = notes_dir / "summary.md"
    highlights = notes_dir / "highlights.md"
    chapters = []
    for p in _chapter_files(entry):
        body = _clean_body(p)
        title = _first_h1(body) or p.stem
        chapters.append({
            "title": title,
            "name": sanitize_dirname(title),
            "src": str(p),
            "hpath": f"{base}/分章笔记/{sanitize_dirname(title)}",
        })

    return {
        "book_id": entry["book_id"],
        "title": entry["title"],
        "author": entry.get("author", ""),
        "tags": tags,
        "category": category,
        "notebook_id": notebook,
        "target": target,
        "base_hpath": base,
        "summary_src": str(summary) if summary.exists() else None,
        "highlights_src": str(highlights) if highlights.exists() else None,
        "chapters_index_hpath": f"{base}/分章笔记" if chapters else None,
        "chapters": chapters,
        "epub_path": str(source_epub),
        "existing_parent_id": entry.get("siyuan_doc_id"),
        "existing_asset": entry.get("siyuan_asset"),
    }


def _parent_body(plan: dict, asset: str | None) -> str:
    lines = [
        f"> 📖 **{plan['title']}**　作者：{plan.get('author') or '—'}",
    ]
    if asset:
        lines.append(f"> 📎 原书 epub：[{plan['title']}·source.epub]({asset})")
    lines.append("> 📚 GitHub 全文：https://github.com/pscly/ybooknote")
    body = "\n".join(lines)
    # 标签独立成段，确保进 SiYuan 标签面板
    tags = plan.get("tags") or []
    if tags:
        body += "\n\n🏷 " + " ".join(f"#{t}#" for t in tags)
    if plan.get("category"):
        body += f"\n\n📂 分类：{plan['category']}"
    return body


# ───────────────────────── 预览 ─────────────────────────

def cmd_tree(needle: str) -> int:
    data = index.load()
    entry = index.find_one(data, needle)
    if not entry:
        print(f"未找到唯一匹配的书: '{needle}'")
        return 2
    plan = build_tree_plan(entry)
    print(f"=== SiYuan 嵌套树计划：{entry['title']} ===")
    print(f"  父文档 : {plan['base_hpath']}  既有父id={plan['existing_parent_id'] or '无'}")
    print(f"  标签   : {'、'.join(plan['tags']) or '—'}    分类：{plan['category'] or '—'}")
    if plan["summary_src"]:
        print("    - 全书总览")
    if plan["highlights_src"]:
        print("    - 摘录与金句")
    if plan["chapters"]:
        print(f"    - 分章笔记（{len(plan['chapters'])} 章，每章独立文档）")
        for c in plan["chapters"]:
            print(f"        · {c['title']}")
    return 0


# ───────────────────────── 同步（建树+互链） ─────────────────────────

def cmd_push(needle: str) -> int:
    import siyuan_api as sy
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
    title = plan["title"]

    # 幂等：删旧父子树（removeDoc 级联子文档）
    if plan["existing_parent_id"]:
        try:
            if sy.remove_doc_by_id(plan["existing_parent_id"]):
                print(f"  已删除旧父文档 {plan['existing_parent_id']}")
        except Exception as exc:
            print(f"  删除旧父文档失败（忽略）: {exc}")

    # 附件（复用已有）
    asset = plan["existing_asset"]
    if not asset:
        asset = sy.upload_asset(plan["epub_path"])
        print(f"  上传 epub → {asset}")

    # —— 第一遍：建文档收集 id ——
    parent_id = sy.create_doc(nb, plan["base_hpath"], _parent_body(plan, asset))
    sy.set_icon(parent_id, ICON_BOOK)
    print(f"  父文档 {parent_id}  📖  {plan['base_hpath']}")

    summary_id = highlights_id = chapters_index_id = None
    top_children = []  # (id) 顺序：总览、金句、分章笔记

    if plan["summary_src"]:
        b = _drop_first_h1(_clean_body(plan["summary_src"]))
        summary_id = sy.create_doc(nb, f"{plan['base_hpath']}/全书总览", b)
        sy.set_icon(summary_id, ICON_SUMMARY)
        top_children.append(summary_id)
    if plan["highlights_src"]:
        b = _drop_first_h1(_clean_body(plan["highlights_src"]))
        highlights_id = sy.create_doc(nb, f"{plan['base_hpath']}/摘录与金句", b)
        sy.set_icon(highlights_id, ICON_HIGHLIGHTS)
        top_children.append(highlights_id)

    chapter_ids = []  # [(title, id)]
    if plan["chapters"]:
        chapters_index_id = sy.create_doc(nb, plan["chapters_index_hpath"], "")
        sy.set_icon(chapters_index_id, ICON_CHAPTERS)
        top_children.append(chapters_index_id)
        for c in plan["chapters"]:
            body = _drop_first_h1(_clean_body(c["src"]))
            cid = sy.create_doc(nb, c["hpath"], body)
            sy.set_icon(cid, ICON_CHAPTER)
            chapter_ids.append((c["title"], cid))
        print(f"  分章笔记 {chapters_index_id}  📚  {len(chapter_ids)} 章独立文档")

    # —— 锁定顺序：父下三件套；分章笔记下各章 ——
    id2path = sy.paths_by_ids(
        top_children + [cid for _, cid in chapter_ids]
    )
    if top_children:
        sy.change_sort(nb, [id2path[i] for i in top_children if i in id2path])
    if chapter_ids:
        sy.change_sort(nb, [id2path[cid] for _, cid in chapter_ids if cid in id2path])

    # —— 第二遍：注入块引用导航 ——
    book_anchor = f"📖 {title}"
    # 父文档：本书笔记清单
    lines = ["## 本书笔记"]
    if summary_id:
        lines.append(f"- 📑 {_ref(summary_id, '全书总览')}")
    if highlights_id:
        lines.append(f"- ✨ {_ref(highlights_id, '摘录与金句')}")
    if chapters_index_id:
        lines.append(f"- 📚 {_ref(chapters_index_id, '分章笔记')}")
    lines.append("\n> 提示：展开左侧文档树可逐章浏览；各文档间已用块引用互链（见反向链接面板/关系图）。")
    sy.append_block(parent_id, "\n".join(lines))

    # 总览 / 金句：顶部导航
    sibling_index = []
    if chapters_index_id:
        sibling_index = [_ref(chapters_index_id, "📚 分章笔记")]
    if summary_id:
        nav = " · ".join([_ref(parent_id, book_anchor)]
                         + ([_ref(highlights_id, "✨ 摘录与金句")] if highlights_id else [])
                         + sibling_index)
        sy.prepend_block(summary_id, "🧭 " + nav)
    if highlights_id:
        nav = " · ".join([_ref(parent_id, book_anchor)]
                         + ([_ref(summary_id, "📑 全书总览")] if summary_id else [])
                         + sibling_index)
        sy.prepend_block(highlights_id, "🧭 " + nav)

    # 分章笔记目录文档：顶部回父 + 章节 TOC
    if chapters_index_id:
        sy.prepend_block(chapters_index_id, "🧭 " + _ref(parent_id, book_anchor))
        toc = ["## 章节目录"] + [f"- {_ref(cid, t)}" for t, cid in chapter_ids]
        sy.append_block(chapters_index_id, "\n".join(toc))
        # 各章：顶部 父·目录·上一章·下一章
        n = len(chapter_ids)
        for i, (t, cid) in enumerate(chapter_ids):
            parts = [_ref(parent_id, book_anchor), _ref(chapters_index_id, "📚 目录")]
            if i > 0:
                parts.append(_ref(chapter_ids[i - 1][1], f"← {chapter_ids[i - 1][0]}"))
            if i < n - 1:
                parts.append(_ref(chapter_ids[i + 1][1], f"{chapter_ids[i + 1][0]} →"))
            sy.prepend_block(cid, "🧭 " + " · ".join(parts))

    cmd_record(needle, parent_id, asset, child_count=len(chapter_ids))
    return 0


def cmd_record(needle: str, doc_id: str, asset: str | None, child_count: int | None = None) -> int:
    data = index.load()
    entry = index.find_one(data, needle)
    if not entry:
        print(f"未找到唯一匹配的书: '{needle}'")
        return 2
    entry["siyuan_doc_id"] = doc_id
    if asset:
        entry["siyuan_asset"] = asset
    if child_count is not None:
        entry["siyuan_child_count"] = child_count
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


# ───────────────────────── 读书馆（分类选书页） ─────────────────────────

def cmd_shelf() -> int:
    import siyuan_api as sy
    data = index.load()
    nb = config.env("SIYUAN_NOTEBOOK_ID")
    target = (config.env("SIYUAN_TARGET_PATH") or "/ai辅助").rstrip("/")

    # 幂等删旧
    old = data.get("siyuan_shelf_id")
    if old:
        try:
            sy.remove_doc_by_id(old)
        except Exception as exc:
            print(f"  删除旧读书馆失败（忽略）: {exc}")

    # 按大类分组（仅已同步且有父文档的书）
    groups: dict[str, list] = {}
    for b in data["books"]:
        pid = b.get("siyuan_doc_id")
        if not pid or b.get("status") != "synced":
            continue
        _, category = _read_meta(b)
        groups.setdefault(category or "未分类", []).append((b, pid))

    lines = ["> 按大类选书；点书名块引用直达该书。标签筛选见左侧标签面板。", ""]
    total = sum(len(v) for v in groups.values())
    # 「未分类」垫底，其余按类名
    for cat in sorted(groups, key=lambda c: (c == "未分类", c)):
        books = sorted(groups[cat], key=lambda x: x[0]["title"])
        lines.append(f"## {cat}（{len(books)}）")
        for b, pid in books:
            tags, _ = _read_meta(b)
            tag_str = ("　" + "、".join(tags)) if tags else ""
            author = b.get("author") or "—"
            lines.append(f"- {_ref(pid, b['title'])}　— {author}{tag_str}")
        lines.append("")

    shelf_id = sy.create_doc(nb, f"{target}/📚 读书馆", "\n".join(lines))
    sy.set_icon(shelf_id, ICON_CHAPTERS)
    data["siyuan_shelf_id"] = shelf_id
    index.save(data)
    print(f"✅ 读书馆已建：{shelf_id}  {len(groups)} 大类 / {total} 本")
    return 0


# ───────────────────────── CLI ─────────────────────────

def main(argv: list[str] | None = None) -> int:
    config.enable_utf8_console()
    parser = argparse.ArgumentParser(description="SiYuan 嵌套树同步（每章独立文档+块引用互链+标签+读书馆）")
    parser.add_argument("--plan", metavar="BOOK", help="预览嵌套树计划")
    parser.add_argument("--shelf", action="store_true", help="建/刷新读书馆分类选书页")
    parser.add_argument("--record", nargs="+", metavar=("BOOK", "DOC_ID"),
                        help="回填: BOOK PARENT_DOC_ID [ASSET]")
    parser.add_argument("book", nargs="?", help="等价于 sync <book>（建整棵树）")
    args = parser.parse_args(argv)

    if args.shelf:
        return cmd_shelf()
    if args.record:
        book = args.record[0]
        doc_id = args.record[1] if len(args.record) > 1 else None
        asset = args.record[2] if len(args.record) > 2 else None
        if not doc_id:
            print("用法: --record <book> <parent_doc_id> [asset]")
            return 2
        return cmd_record(book, doc_id, asset)
    if args.plan:
        return cmd_tree(args.plan)

    if not args.book:
        print("用法: python book.py sync <book>  |  --plan <book>  |  --shelf")
        return 2
    return cmd_push(args.book)


if __name__ == "__main__":
    raise SystemExit(main())
