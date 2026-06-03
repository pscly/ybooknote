"""epub 解析（确定性，非 AI）：读元数据、按 spine 抽章为纯文本。

供 ingest.py 调用。解析失败不抛到顶层，交调用方记 last_error。
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import epub

warnings.filterwarnings("ignore", category=UserWarning, module="ebooklib")
warnings.filterwarnings("ignore", category=FutureWarning, module="ebooklib")
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# 字符数低于此值的文档视为封面/版权页等噪声，跳过
_MIN_CHAPTER_CHARS = 20


@dataclass
class BookMeta:
    title: str
    author: str = ""
    language: str = ""


@dataclass
class Chapter:
    idx: int
    title: str
    filename: str
    chars: int


@dataclass
class ExtractResult:
    meta: BookMeta
    chapters: list[Chapter] = field(default_factory=list)
    total_chars: int = 0


def _first_meta(book, name: str) -> str:
    try:
        vals = book.get_metadata("DC", name)
        if vals and vals[0] and vals[0][0]:
            return str(vals[0][0]).strip()
    except Exception:
        pass
    return ""


def read_meta(epub_path: str | Path, fallback_title: str = "") -> BookMeta:
    book = epub.read_epub(str(epub_path))
    title = _first_meta(book, "title") or fallback_title or Path(epub_path).stem
    return BookMeta(
        title=title,
        author=_first_meta(book, "creator"),
        language=_first_meta(book, "language"),
    )


def _doc_title(soup: BeautifulSoup, default: str) -> str:
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        if t:
            return t
    for tag in ("h1", "h2", "h3"):
        el = soup.find(tag)
        if el:
            t = el.get_text(" ", strip=True)
            if t:
                return t
    return default


def _ordered_documents(book):
    """按 spine 顺序返回 ITEM_DOCUMENT，spine 缺失时退化为文档迭代顺序。"""
    docs = []
    seen = set()
    for entry in (book.spine or []):
        idref = entry[0] if isinstance(entry, (tuple, list)) else entry
        item = book.get_item_with_id(idref)
        if item is not None and item.get_type() == ebooklib.ITEM_DOCUMENT:
            docs.append(item)
            seen.add(item.get_id())
    if not docs:
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            if item.get_id() not in seen:
                docs.append(item)
    return docs


def extract(epub_path: str | Path, out_dir: str | Path, fallback_title: str = "") -> ExtractResult:
    """抽章到 out_dir/NN.txt，返回 ExtractResult（含 manifest 所需信息）。"""
    book = epub.read_epub(str(epub_path))
    meta = BookMeta(
        title=_first_meta(book, "title") or fallback_title or Path(epub_path).stem,
        author=_first_meta(book, "creator"),
        language=_first_meta(book, "language"),
    )

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # 清旧缓存，保证可重建幂等
    for old in out.glob("*.txt"):
        old.unlink()

    result = ExtractResult(meta=meta)
    n = 0
    for raw_idx, item in enumerate(_ordered_documents(book), start=1):
        try:
            html = item.get_content().decode("utf-8", errors="ignore")
        except Exception:
            continue
        soup = BeautifulSoup(html, "lxml")
        for bad in soup(["script", "style"]):
            bad.decompose()
        text = soup.get_text("\n", strip=True)
        text = "\n".join(line for line in (l.strip() for l in text.splitlines()) if line)
        if len(text) < _MIN_CHAPTER_CHARS:
            continue
        n += 1
        title = _doc_title(soup, f"Section {n:02d}")
        fname = f"{n:02d}.txt"
        (out / fname).write_text(text, encoding="utf-8")
        result.chapters.append(Chapter(idx=n, title=title, filename=fname, chars=len(text)))
        result.total_chars += len(text)

    return result
