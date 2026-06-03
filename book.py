#!/usr/bin/env python3
"""顶层 CLI —— AI 读书笔记库。

子命令分派到 9scripts/ 下各脚本（按需惰性导入，未实现的命令不影响其它命令）。

  python book.py <command> [args]

命令：
  ingest                 扫 1books/_inbox（及散落 epub）入库为 pending
  list                   列出全部书目与状态
  status <state> <book>  推进状态机（pending/analyzing/drafted/reviewed/synced/failed）
  status review <book>   = status reviewed <book>（人工抽检关卡，仅 drafted 可进）
  readme                 重新生成 README.md
  kavita                 列出 Kavita 整库并标注是否已分析
  pull <kavita-id...>    从 Kavita 下载并自动 ingest
  sync <book>            幂等同步到 SiYuan（决策+记账；正文与附件经 MCP 写入）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "9scripts"))

from lib import config  # noqa: E402

USAGE = __doc__


def main(argv: list[str]) -> int:
    config.enable_utf8_console()
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]

    if cmd == "ingest":
        import ingest
        return ingest.main(rest)
    if cmd == "list":
        import status
        return status.print_list()
    if cmd == "status":
        import status
        # 允许 `status review <book>` 作为 `status reviewed <book>` 的别名
        if rest and rest[0] == "review":
            rest = ["reviewed"] + rest[1:]
        return status.main(rest)
    if cmd == "readme":
        import gen_readme
        return gen_readme.main(rest)
    if cmd == "kavita":
        import kavita
        return kavita.main(["list", *rest])
    if cmd == "pull":
        import kavita
        return kavita.main(["pull", *rest])
    if cmd == "sync":
        import sync_siyuan
        return sync_siyuan.main(rest)

    print(f"未知命令: {cmd}\n")
    print(USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
