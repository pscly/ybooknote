"""每本书的导航页（1notes/<书>/README.md）+ 给各页注入「回跳导航条」。

确定性渲染，归脚本（P1）。导航条用 NAV 标记块包裹，幂等：重复运行只替换标记块内内容，不动正文。
GitHub 浏览到书目录时会自动展示该目录的 README.md，即导航页。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import config, frontmatter, index

NAV_START = "<!-- NAV:START 自动生成，请勿手改 -->"
NAV_END = "<!-- NAV:END -->"
_NAV_RE = re.compile(re.escape(NAV_START) + r".*?" + re.escape(NAV_END), re.S)


def _chapter_sort_key(p: Path):
    m = re.match(r"(\d+)", p.name)
    return (int(m.group(1)) if m else 9999, p.name)


def _chapter_files(notes_dir: Path) -> list[Path]:
    ch = notes_dir / "chapters"
    if not ch.exists():
        return []
    return sorted((p for p in ch.glob("*.md")), key=_chapter_sort_key)


def _h1_title(path: Path) -> str:
    """取首个 '# ' 标题，跳过 frontmatter 与 NAV 块。"""
    text = path.read_text(encoding="utf-8")
    text = _NAV_RE.sub("", text)
    _, body = frontmatter.parse(text)
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def _link(text: str, rel: str) -> str:
    return f"[{text}]({quote(rel)})"


def _inject_nav(path: Path, nav_md: str) -> None:
    text = path.read_text(encoding="utf-8")
    block = f"{NAV_START}\n{nav_md}\n{NAV_END}"
    if _NAV_RE.search(text):
        text = _NAV_RE.sub(block, text)
    elif text.startswith("---"):
        # 插到 frontmatter 关闭 '---' 之后
        lines = text.splitlines(keepends=True)
        close = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                close = i
                break
        if close is not None:
            head = "".join(lines[: close + 1])
            rest = "".join(lines[close + 1:])
            text = head + "\n" + block + "\n" + rest
        else:
            text = block + "\n\n" + text
    else:
        text = block + "\n\n" + text
    path.write_text(text, encoding="utf-8")


def build_book_index(entry: dict) -> None:
    notes_dir = config.ROOT / entry["notes"]["dir"]
    if not notes_dir.exists():
        return
    summary = notes_dir / "summary.md"
    meta = {}
    if summary.exists():
        meta, _ = frontmatter.read_file(summary)
    title = meta.get("title") or entry["title"]
    author = meta.get("author") or entry.get("author") or "—"
    tags = meta.get("tags") or entry.get("tags") or []
    status = meta.get("status") or entry["status"]
    tag_str = "、".join(tags) if tags else "—"

    chapters = _chapter_files(notes_dir)

    # ---- 导航页 README.md ----
    lines = [
        f"# 📖 {title}",
        "",
        f"> 作者：{author} ｜ 标签：{tag_str} ｜ 状态：{status}",
        "",
        "## 总览",
        f"- {_link('📑 全书总览（summary）', 'summary.md')}",
        f"- {_link('✨ 摘录与金句（highlights）', 'highlights.md')}",
        "",
    ]
    if chapters:
        lines.append(f"## 📚 分章笔记（共 {len(chapters)} 篇）")
        for p in chapters:
            lines.append(f"- {_link(_h1_title(p), 'chapters/' + p.name)}")
        lines.append("")
    (notes_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")

    # ---- 给 summary / highlights 注入导航条 ----
    if summary.exists():
        _inject_nav(summary, "🧭 " + " · ".join([
            _link("📚 本书导航", "README.md"),
            _link("✨ 摘录金句", "highlights.md"),
        ]))
    hl = notes_dir / "highlights.md"
    if hl.exists():
        _inject_nav(hl, "🧭 " + " · ".join([
            _link("📚 本书导航", "README.md"),
            _link("📑 全书总览", "summary.md"),
        ]))

    # ---- 给每章注入导航条（含上一章/下一章）----
    for i, p in enumerate(chapters):
        parts = [
            _link("📚 本书导航", "../README.md"),
            _link("📑 全书总览", "../summary.md"),
            _link("✨ 摘录", "../highlights.md"),
        ]
        if i > 0:
            parts.append(_link("← 上一章", chapters[i - 1].name))
        if i < len(chapters) - 1:
            parts.append(_link("下一章 →", chapters[i + 1].name))
        _inject_nav(p, "🧭 " + " · ".join(parts))


def main(argv: list[str] | None = None) -> int:
    config.enable_utf8_console()
    data = index.load()
    n = 0
    for entry in data["books"]:
        build_book_index(entry)
        n += 1
    print(f"已生成 {n} 本书的导航页与回跳导航条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
