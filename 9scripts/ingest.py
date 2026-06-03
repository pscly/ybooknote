"""ingest：扫 _inbox（及 1books 根下散落 epub）→ 元数据 → sha256 → 建中文目录 →
搬 source.epub → 抽章缓存 → 建 1notes 骨架 → 写 index(status=pending)。

确定性 + 破坏性（移动文件）操作，全部由本脚本完成，符合 P1。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import epubutil
from lib import config, frontmatter, hashing, index
from lib.textutil import make_book_id, sanitize_dirname

_SKELETON_SUMMARY = "<!-- 待 AI 生成：全书总览（summary）。运行 Map-Reduce 后填充。 -->\n"
_SKELETON_HL = "<!-- 待 AI 生成：摘录与金句（highlights）。 -->\n"


def _candidate_epubs() -> list[Path]:
    found: list[Path] = []
    if config.INBOX_DIR.exists():
        found += sorted(config.INBOX_DIR.glob("*.epub"))
    # 1books 根下散落的 epub（兼容现有两本），不含各书子目录
    found += sorted(p for p in config.BOOKS_DIR.glob("*.epub"))
    return found


def _rel(p: Path) -> str:
    return p.resolve().relative_to(config.ROOT).as_posix()


def _unique_dirname(title: str, book_id: str, data: dict) -> str:
    base = sanitize_dirname(title)
    short = book_id.rsplit("-", 1)[-1]
    used = {
        b["notes"]["dir"].rsplit("/", 1)[-1]
        for b in data["books"]
        if b.get("book_id") != book_id
    }
    if base in used or (config.NOTES_DIR / base).exists() or (config.BOOKS_DIR / base).exists():
        return f"{base}-{short}"
    return base


def _ingest_one(epub_path: Path, data: dict, title_override: str | None) -> dict | None:
    sha = hashing.sha256_file(epub_path)
    short = hashing.short_hash(sha)

    dup = index.find_by_hash(data, sha)
    if dup:
        print(f"  跳过（已入库 sha 相同）: {dup['title']}  [{dup['book_id']}] status={dup['status']}")
        return None

    meta = epubutil.read_meta(epub_path, fallback_title=epub_path.stem)
    title = (title_override or meta.title).strip()
    book_id = make_book_id(title, short)
    dirname = _unique_dirname(title, book_id, data)

    book_dir = config.BOOKS_DIR / dirname
    notes_dir = config.NOTES_DIR / dirname
    cache_dir = book_dir / ".cache" / "chapters"
    book_dir.mkdir(parents=True, exist_ok=True)

    # 搬运 epub -> source.epub
    source = book_dir / "source.epub"
    shutil.move(str(epub_path), str(source))

    # 抽章
    result = epubutil.extract(source, cache_dir, fallback_title=title)
    manifest = {
        "title": title,
        "author": meta.author,
        "language": meta.language,
        "total_chars": result.total_chars,
        "chapters": [
            {"idx": c.idx, "title": c.title, "file": c.filename, "chars": c.chars}
            for c in result.chapters
        ],
    }
    (cache_dir / "chapters.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 笔记骨架
    (notes_dir / "chapters").mkdir(parents=True, exist_ok=True)
    (notes_dir / "chapters" / ".gitkeep").write_text("", encoding="utf-8")
    fm = {
        "title": title,
        "author": meta.author,
        "book_id": book_id,
        "status": "pending",
        "tags": [],
        "created": index.now_iso()[:10],
    }
    frontmatter.write_file(notes_dir / "summary.md", fm, _SKELETON_SUMMARY)
    frontmatter.write_file(notes_dir / "highlights.md", dict(fm), _SKELETON_HL)

    entry = {
        "book_id": book_id,
        "title": title,
        "author": meta.author,
        "source": {
            "path": _rel(source),
            "format": "epub",
            "sha256": sha,
        },
        "notes": {
            "dir": _rel(notes_dir),
            "summary": "summary.md",
            "chapters_extracted": len(result.chapters),
        },
        "status": "pending",
        "tags": [],
        "prompt_version": None,
        "kavita": None,
        "siyuan_doc_id": None,
        "siyuan_asset": None,
        "last_error": None,
        "created_at": index.now_iso(),
        "updated_at": index.now_iso(),
    }
    data["books"].append(entry)
    print(f"  入库 OK: {title}  [{book_id}]  章节={len(result.chapters)}  字数≈{result.total_chars}")
    return entry


def main(argv: list[str] | None = None) -> int:
    config.enable_utf8_console()
    parser = argparse.ArgumentParser(description="扫描 epub 并入库（pending）")
    parser.add_argument("--title", help="覆盖书名（仅当只有一本待入库时有意义）")
    args = parser.parse_args(argv)

    epubs = _candidate_epubs()
    if not epubs:
        print("没有发现待入库 epub（放到 1books/_inbox/ 后重试）。")
        return 0
    if args.title and len(epubs) > 1:
        print("⚠ --title 仅适用于单本入库；检测到多本，忽略 --title。")
        args.title = None

    data = index.load()
    print(f"发现 {len(epubs)} 个 epub，开始入库……")
    added = 0
    for ep in epubs:
        print(f"- {ep.name}")
        try:
            if _ingest_one(ep, data, args.title):
                added += 1
        except Exception as exc:  # 解析失败：跳过该本，不中断整体
            print(f"  失败: {exc}")
    index.save(data)
    print(f"完成：新增 {added} 本，index 共 {len(data['books'])} 本 -> {config.INDEX_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
