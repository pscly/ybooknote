"""SiYuan 内核 API 客户端（本地 HTTP，用 .env 的 SIYUAN_API_URL/TOKEN）。

服务端建文档/设图标/传附件，正文从磁盘读取，不经过 Claude 上下文 —— 支撑批量树同步。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

from lib import config

TIMEOUT = 90


def _base() -> str:
    return (config.env("SIYUAN_API_URL") or "http://127.0.0.1:6806").rstrip("/")


def _auth() -> dict:
    return {"Authorization": "Token " + (config.env("SIYUAN_TOKEN") or "")}


def _post(api: str, payload: dict | None = None, files=None, data=None):
    url = _base() + api
    if files is not None:
        r = requests.post(url, headers=_auth(), files=files, data=data, timeout=TIMEOUT)
    else:
        r = requests.post(url, headers={**_auth(), "Content-Type": "application/json"},
                          json=payload or {}, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    if j.get("code") != 0:
        raise RuntimeError(f"{api} failed: {j.get('msg')}")
    return j.get("data")


def sql(stmt: str):
    return _post("/api/query/sql", {"stmt": stmt})


def create_doc(notebook: str, hpath: str, markdown: str) -> str:
    """按 hpath 建文档（自动建缺失的祖先），返回新文档 id。"""
    return _post("/api/filetree/createDocWithMd",
                 {"notebook": notebook, "path": hpath, "markdown": markdown})


def set_icon(doc_id: str, icon: str) -> None:
    _post("/api/attr/setBlockAttrs", {"id": doc_id, "attrs": {"icon": icon}})


def prepend_block(parent_id: str, markdown: str) -> str | None:
    """在 parent_id（文档或块）内最前插入 markdown 块，返回新块 id。"""
    res = _post("/api/block/prependBlock",
                {"dataType": "markdown", "data": markdown, "parentID": parent_id})
    return _first_block_id(res)


def append_block(parent_id: str, markdown: str) -> str | None:
    """在 parent_id（文档或块）内末尾追加 markdown 块，返回新块 id。"""
    res = _post("/api/block/appendBlock",
                {"dataType": "markdown", "data": markdown, "parentID": parent_id})
    return _first_block_id(res)


def _first_block_id(res):
    """prepend/appendBlock 返回事务数组，取首个 doOperation 的块 id。"""
    try:
        return res[0]["doOperations"][0]["id"]
    except (TypeError, IndexError, KeyError):
        return None


def upload_asset(file_path: str, assets_dir: str = "/assets/") -> str | None:
    p = Path(file_path)
    with open(p, "rb") as f:
        res = _post("/api/asset/upload", files={"file[]": (p.name, f)}, data={"assetsDirPath": assets_dir})
    succ = (res or {}).get("succMap", {})
    return next(iter(succ.values()), None)


def doc_box_path_by_id(doc_id: str):
    rows = sql(f"SELECT box, path FROM blocks WHERE id='{doc_id}' AND type='d' LIMIT 1")
    if rows:
        return rows[0]["box"], rows[0]["path"]
    return None, None


def remove_doc_by_id(doc_id: str) -> bool:
    box, path = doc_box_path_by_id(doc_id)
    if box and path:
        _post("/api/filetree/removeDoc", {"notebook": box, "path": path})
        return True
    return False


def doc_id_by_hpath(notebook: str, hpath: str):
    rows = sql(f"SELECT id FROM blocks WHERE box='{notebook}' AND hpath='{hpath}' AND type='d' LIMIT 1")
    return rows[0]["id"] if rows else None


def paths_by_ids(ids: list[str]) -> dict:
    """批量取文档 .sy 路径：返回 {id: path}。"""
    if not ids:
        return {}
    in_list = ",".join(f"'{i}'" for i in ids)
    rows = sql(f"SELECT id, path FROM blocks WHERE id IN ({in_list}) AND type='d'")
    return {r["id"]: r["path"] for r in (rows or [])}


def change_sort(notebook: str, paths: list[str]) -> None:
    """按给定 .sy 路径顺序锁定同级文档排序（笔记本转自定义排序，仅影响所列文档相对次序）。"""
    if paths:
        _post("/api/filetree/changeSort", {"notebook": notebook, "paths": paths})
