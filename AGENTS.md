# AGENTS.md —— AI 引擎作业流程

本仓库是「看书 + AI 总结」工具库。**AI（Claude Code）只生成 md 内容；一切移动/哈希/状态/索引/commit/同步记账由 `9scripts/` 下的确定性脚本完成**（硬约束见 `设计方案.md` 第 0 节 P1/P2/P3）。

## 角色边界（务必遵守）
- ✅ 我可以做：读 `1books/<书>/.cache/chapters/*.txt`，在 `1notes/<书>/` 下写 md；经 SiYuan MCP 写文档正文与上传附件。
- 🚫 我不可以做：手动移动/删除/重命名文件、手改 `0meta/index.json`、手写 `README.md`、绕过状态机。
- 状态推进一律走 `python book.py status <state> <book>`；索引由脚本维护。

## 一本书的处理流程（Map-Reduce 两段式）

前置：该书已 `ingest`（status=pending），`1books/<书>/.cache/chapters/` 有分章纯文本与 `chapters.json`。

1. **置 analyzing**：`python book.py status analyzing <book>`。
2. **读清单**：读 `.cache/chapters/chapters.json` 拿章节顺序与标题。
3. **Map（逐章）**：按 `0meta/prompts/map.v1.md`，逐章读 `NN.txt` → 写 `1notes/<书>/chapters/NN-<短标题>.md`；每章携带上一章「滚动摘要」作上下文。长书（如上百章）可分批处理。
4. **Highlights**：按 `0meta/prompts/highlights.v1.md` 汇总跨章金句 → `1notes/<书>/highlights.md`。
5. **Reduce（缝合）**：按 `0meta/prompts/reduce.v1.md`，汇总各章「作用」重建全书脉络 → `1notes/<书>/summary.md`；frontmatter 写 `tags` 与 `prompt_version: map.v1+reduce.v1`。
6. **置 drafted**：`python book.py status drafted <book>`。
7. **生成索引**：`python book.py readme`。
8. **交人工抽检**：提示用户检查 `summary.md`；质量达标后由**用户**执行 `python book.py status review <book>`（硬关卡，我不能代跳）。

## 同步到 SiYuan（reviewed 之后）
- 跑 `python book.py sync <book>`：脚本读 index 给出 CREATE/UPDATE 决策。
- 我据决策经 SiYuan MCP：在 `books笔记 / ai辅助` 下建/更文档、设 📖 图标、写正文；`siyuan_asset` 为空时把 `source.epub` 传为附件并在文首插入「📎 原书」链接；回收 `doc_id` 与 asset 路径。
- 回填：`python 9scripts/sync_siyuan.py --record <book> <doc_id> <asset>`（写回 id、状态→synced、commit）。
- 幂等：是否新建由 `siyuan_doc_id` 决定；重复 sync 不产生重复文档/附件。

## 书源
- 书源主库是 **Kavita**：`python book.py kavita` 看有哪些书/哪些已分析；`python book.py pull <id>` 下载并自动 ingest。
- 本地 `1books/**/*.epub` 与 `.cache/` 均 gitignore；**版权书不进 GitHub**，只分享 `1notes/`。

## 提交节奏（Git，P3）
在 ingest、drafted、synced 等里程碑由脚本/用户 commit，保证每步可 diff、可回滚。
