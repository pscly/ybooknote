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
3. **Map（逐章）**：按 `0meta/prompts/map.v1.md`（当前已按深度要求强化），逐章读 `NN.txt` → 写 `1notes/<书>/chapters/NN-<短标题>.md`；每章携带上一章「滚动摘要」作上下文。长书（如上百章）可分批处理。
4. **Highlights**：按 `0meta/prompts/highlights.v1.md`（当前已按深度要求强化），汇总跨章金句 → `1notes/<书>/highlights.md`。
5. **Reduce（缝合）**：按 `0meta/prompts/reduce.v1.md`（当前已按深度要求强化），汇总各章「作用/辩证位置」重建全书脉络 → `1notes/<书>/summary.md`；frontmatter 写 `tags` 与 `prompt_version: map.v1+reduce.v1`。
6. **置 drafted**：`python book.py status drafted <book>`。
7. **生成索引**：`python book.py readme`。
8. **交人工抽检**：提示用户检查 `summary.md` 与 chapters/；**对照 `0meta/quality-criteria.md` 判断是否达到「深刻 / very ok」标准**（张力可见、读者抵抗点被命名、代价与毒诚实呈现、可重读的刺）。质量达标后由**用户**执行 `python book.py status review <book>`（硬关卡，我不能代跳）。

## 当前笔记写作风格（深刻度要求，2026-06 当前版）

严格按照 `0meta/prompts/map.v1.md`、`reduce.v1.md`、`highlights.v1.md` 以及 `0meta/quality-criteria.md` 执行。

**核心目标**：笔记要让读者产生“原来如此但我之前没看见”的感受，带有可重读的“刺”，而不是干净的列表式总结或泛泛鸡汤。重点是揭示张力、命名读者内在抵抗、呈现代价与副作用、建立逻辑必然的辩证关系，让笔记本身值得反复阅读。

**Map 阶段关键要求**：
- 要点必须覆盖核心论证 + 最强的张力/反常识点（不要只复述“作者说了什么”）。
- 关键摘录的“点评”**必须同时回答两个问题**：
  1. 它直接挑战了读者什么默认假设或舒适区？
  2. 实践或接受它时，读者最常见的两种误用或内在抵抗是什么？
- “在全书论证链中的作用”必须写成**辩证位置**：本章继承或反转了前文什么；此刻对读者心智/性格提出什么具体、非可选的要求；它为后文必然埋下什么必须回答的问题。
- 滚动摘要要携带累积的 stakes、开放问题，以及读者此刻最可能卡住的地方（给下一章真正有用的上下文）。

**Reduce 阶段关键要求**：
- 一句话核心必须是“逻辑必然的钉子”（读完后最难被替换掉的那根）。
- 论证主线要写出作者最隐秘的假设 + 读者真正接受它必须付出的具体心智或品格代价。
- **必须新增两节**：
  - “全书最统一的意象 / 机制及其极限”（什么统一了全书？边界在哪里？）
  - “本书的『药』与『毒』”（认真服用会系统性改善什么；按本书自己逻辑被误读或过度延伸会必然产生什么坏结果）
- 可落地的启示必须能清晰回溯到书中具体机制或张力（不是外挂建议）。
- “适合谁 / 局限”要指出“哪些人会出于正确理由讨厌这本书”，以及最容易被驯化或滥用的点。

**Highlights 阶段**：宁缺毋滥，每条必须有“具体生活照见场景 + 会在这里暴露什么盲点 + 边界/风险”。

**特殊体裁指导**（内丹、经典哲学、浓缩格言类）：保留象征系统的内在一致性与身体-心性-宇宙对应关系，不要过早翻译成现代流行心理学语言。除非作者本人已在桥接，否则保持原有的“奇怪”与精确。

人工抽检时对照 `0meta/quality-criteria.md` 的八条标准和 checklist 执行。目标是“有刺、可重读、代价与毒诚实、逻辑必然”。

## 同步到 SiYuan（reviewed 之后）
- 跑 `python book.py sync <book>`：**全程脚本经内核 API 完成，正文从磁盘读、不进我的上下文**（无需我手动经 MCP 逐篇写）。
- 建出的**嵌套文档树**镜像本地多文档结构：
  - 父文档 `/ai辅助/<书名>` 📖：书信息 + 📎 epub 附件 + `#标签#`（取自 summary frontmatter `tags`）+ 📂 分类（`category`）。
  - 子文档：`全书总览` 📑、`摘录与金句` ✨、`分章笔记` 📚（目录文档）。
  - `分章笔记` 下**每章一个独立文档**（标题取章节 H1），顺序用内核 `changeSort` 锁定。
- **互链全用块引用 `((id "锚文本"))`**（双向，进反向链接面板/关系图）：父→各子文档；各子文档/各章→回父；章↔章（上/下一章）；分章笔记目录→各章。
- 标签写在父文档独立成段的 `#标签#`，左侧标签面板可点选筛选选书。
- 分类选书页：所有书同步后跑 `python 9scripts/sync_siyuan.py --shelf` 建/刷新顶层「📚 读书馆」，按 `category` 分组、每书一个块引用链接；id 存 `index.json` 顶层 `siyuan_shelf_id`，幂等。
- 回填仍由脚本自动完成（写回父 `siyuan_doc_id`、`siyuan_child_count`、状态→synced）；`--record <book> <id> [asset]` 仅在需手动补登时用。
- 幂等：父 `siyuan_doc_id` 存在则先删旧父子树（级联删除深层子文档）再重建，重复 sync 不产生重复文档/附件。
- 预览：`python 9scripts/sync_siyuan.py --plan <book>` 看树结构与章节清单（不写 SiYuan）。

## 书源
- 书源主库是 **Kavita**：`python book.py kavita` 看有哪些书/哪些已分析；`python book.py pull <id>` 下载并自动 ingest。
- 本地 `1books/**/*.epub` 与 `.cache/` 均 gitignore；**版权书不进 GitHub**，只分享 `1notes/`。

## 提交节奏（Git，P3）
在 ingest、drafted、synced 等里程碑由脚本/用户 commit，保证每步可 diff、可回滚。
