"""Kavita OPDS 书目前门：列整库 + 与 index 差集 + 选书下载进 _inbox（随后自动 ingest）。

Kavita OPDS 层级：/libraries -> /libraries/{id}(系列列表) -> /series/{id}(可下载 epub)。
下载直链已内嵌 apiKey，无需额外鉴权。仅读不改 Kavita 库。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ingest as ingest_mod
from lib import config, hashing, index
from lib.textutil import sanitize_dirname

ATOM = "{http://www.w3.org/2005/Atom}"
ACQ_REL = "http://opds-spec.org/acquisition"
TIMEOUT = 30


def _base() -> str:
    base = config.env("KAVITA_OPDS_URL")
    if not base:
        raise SystemExit("未配置 KAVITA_OPDS_URL（见 .env）")
    return base.rstrip("/")


def _host() -> str:
    p = urlparse(_base())
    return f"{p.scheme}://{p.netloc}"


def _abs(href: str) -> str:
    if href.startswith("http"):
        return href
    return _host() + href


def _get_feed(url: str) -> ET.Element:
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return ET.fromstring(r.content)


def _entries(root: ET.Element):
    return root.findall(f"{ATOM}entry")


def _next_link(root: ET.Element) -> str | None:
    for l in root.findall(f"{ATOM}link"):
        if l.get("rel") == "next" and l.get("href"):
            return _abs(l.get("href"))
    return None


def _subsection_href(entry: ET.Element) -> str | None:
    for l in entry.findall(f"{ATOM}link"):
        if l.get("rel") == "subsection" and l.get("href"):
            return _abs(l.get("href"))
    return None


def iter_series() -> list[dict]:
    """遍历所有书库下的系列，返回 [{id, title, href}]。"""
    series: list[dict] = []
    libs = _get_feed(_base() + "/libraries")
    for lib in _entries(libs):
        href = _subsection_href(lib)
        if not href:
            continue
        url = href
        while url:
            feed = _get_feed(url)
            for e in _entries(feed):
                sid = (e.findtext(f"{ATOM}id") or "").strip()
                title = (e.findtext(f"{ATOM}title") or "").strip()
                shref = _subsection_href(e)
                if sid and shref:
                    series.append({"id": sid, "title": title, "href": shref})
            url = _next_link(feed)
    return series


def series_downloads(series_id: str) -> list[dict]:
    """返回某系列下的可下载 epub：[{title, href, filename}]。"""
    feed = _get_feed(_base() + f"/series/{series_id}")
    out: list[dict] = []
    for e in _entries(feed):
        for l in e.findall(f"{ATOM}link"):
            rel = l.get("rel") or ""
            if ACQ_REL in rel and (l.get("type") or "").startswith("application/epub"):
                href = _abs(l.get("href"))
                fname = unquote(href.rsplit("/", 1)[-1]) or f"series-{series_id}.epub"
                out.append({"title": (e.findtext(f'{ATOM}title') or '').strip(), "href": href, "filename": fname})
    return out


def cmd_list() -> int:
    data = index.load()
    analyzed = {}
    for b in data["books"]:
        kid = (b.get("kavita") or {}).get("id")
        if kid is not None:
            analyzed[str(kid)] = b["status"]

    series = iter_series()
    print(f"Kavita 共 {len(series)} 个系列：\n")
    print(f"{'系列ID':<8} {'已分析':<10} 标题")
    print("-" * 72)
    for s in series:
        st = analyzed.get(s["id"])
        flag = f"✅ {st}" if st else "—"
        print(f"{s['id']:<8} {flag:<10} {s['title'][:50]}")
    print("\n下载分析：python book.py pull <系列ID> [<系列ID> ...]")
    return 0


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, timeout=TIMEOUT, stream=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
        if total:
            print(f"     下载完成 {done/1048576:.1f}MB / {total/1048576:.1f}MB")
        else:
            print(f"     下载完成 {done/1048576:.1f}MB")


def cmd_pull(series_ids: list[str]) -> int:
    if not series_ids:
        print("用法: python book.py pull <系列ID> [<系列ID> ...]（ID 见 book.py kavita）")
        return 2
    pulled: list[tuple[str, str]] = []  # (sha, series_id)
    for sid in series_ids:
        downloads = series_downloads(sid)
        if not downloads:
            print(f"系列 {sid}: 未找到可下载 epub，跳过。")
            continue
        for d in downloads:
            safe = sanitize_dirname(d["filename"]) or f"series-{sid}.epub"
            if not safe.lower().endswith(".epub"):
                safe += ".epub"
            dest = config.INBOX_DIR / safe
            print(f"系列 {sid}: 下载 {d['filename']}")
            try:
                _download(d["href"], dest)
                pulled.append((hashing.sha256_file(dest), sid))
            except Exception as exc:
                print(f"     失败: {exc}")

    if not pulled:
        print("没有成功下载任何文件。")
        return 1

    # 自动 ingest（脚本治理：移动/抽章/写 index）
    print("\n=== 自动 ingest ===")
    ingest_mod.main([])

    # 回填 kavita 关联（按 sha 匹配 ingest 产生的条目）
    data = index.load()
    for sha, sid in pulled:
        entry = index.find_by_hash(data, sha)
        if entry:
            entry["kavita"] = {"id": sid, "downloaded": True}
            entry["updated_at"] = index.now_iso()
    index.save(data)
    print("已回填 kavita 关联。运行 `python book.py list` 查看。")
    return 0


def main(argv: list[str] | None = None) -> int:
    config.enable_utf8_console()
    parser = argparse.ArgumentParser(description="Kavita 书目前门")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("list", help="列出整库系列并标注是否已分析")
    p_pull = sub.add_parser("pull", help="下载并 ingest")
    p_pull.add_argument("ids", nargs="*", help="系列 ID")
    args = parser.parse_args(argv)

    if args.cmd == "pull":
        return cmd_pull(args.ids)
    return cmd_list()


if __name__ == "__main__":
    raise SystemExit(main())
