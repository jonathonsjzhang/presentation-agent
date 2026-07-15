---
name: analysis
description: Analyze raw internet-strategy materials or an Evidence Catalog into traceable findings and 2–3 genuinely different thesis options for human selection. Use in the Analysis stage to determine what the evidence supports, what remains uncertain, why it matters, and which alternative answers are worth taking into Storyline.
---

# Analysis Core

## Role

把参考材料想明白，并把结果收敛为两类产物：一组可追溯的 `findings`，以及 2–3 组供用户选择的 `thesis_options`。

Analysis 负责发现、比较、解释和挑战观点；Storyline 在用户选定论点组后，才决定唯一主线、章节故事与标题。不要在 Analysis 阶段预写报告。

## 核心准则

### 一、先广泛发现，再开始收敛

先理解任务、材料和用户希望验证的 hypo，再扫描事实、趋势、差异、异常、冲突与机制线索。框架用于发现遗漏和建立可比关系，不用于预设结论；材料不支持原始 hypo 时，应改变判断而不是替它寻找佐证。

### 二、判断是证据与挑战共同作用后的净结论

- 每个 finding 都要区分材料直接支持的观察、由观察推导的解释，以及仍待验证的假设。
- 反证、替代解释和方法限制若会改变结论，应直接收窄 `claim`、降低 `confidence` 或把判断改写为 hypothesis；不能用 `challenges` 为过强主张补免责声明。
- `so_what` 说明这一判断改变了对当前问题的什么理解。它可以指出决策含义，但不能越过证据直接生成战略方案。
- 引用必须真实可回查。相关性、访谈和个案不能单独证明因果或总体规律；证据来源的数量不等于独立性。

### 三、候选论点必须是真正不同的选择

`thesis_options` 不是同一结论的不同措辞。不同选项应在核心解释、判断重点或决策含义上存在实质差异，并各自由一组 findings 支撑。

不要为了显得完整而制造对立。如果证据尚不足以形成多个成熟答案，可以把选项写成不同的解释路径或决策姿态，并明确哪些只能支持验证、不能支持直接投入。用户需要看见真实的选择空间，而不是被迫在几套伪结论中选择。

### 四、Analysis 停在论点组，不进入故事线

Analysis 可以判断哪些 findings 能共同形成一个更高层主张，但不选择最终 apex，不安排章节顺序，不写 Executive Summary，也不决定正文与附录。`thesis_options` 表达“可以讲什么”，Storyline 决定“选定后怎样讲清楚”。

## Workflow

### 1. 界定问题与证据边界

明确本轮要解释、判断或支持的决策，以及哪些相邻问题不在范围内。区分用户希望证明的观点与材料已经支持的事实。

核对证据准备度：已有 Evidence Catalog 就复用；只有 Raw Materials 时按运行协议请求或调用证据整理；两者都没有时记录阻塞。确认关键材料和口径已覆盖后再分析。

### 2. 发现、比较和追问

浏览全量证据，寻找重要的变化、差异、结构、异常、冲突和定性机制线索。根据问题选择必要的时间、分群、竞品、基准或因子比较；对关键现象继续追问“为什么、发生在谁身上、在什么条件下成立”。

追问到证据能够支持的最深一层就停止。复杂任务可参考 `references/analysis_method.md` 中的 finding 类型、竞争性解释和 confidence 校准方法，不需要把方法清单写入产物。

### 3. 形成 findings

删除重复、琐碎和与当前问题无关的内容。每个 finding 只保留一个清楚、可检验的判断，并提交：

- `claim`：证据与挑战共同作用后的净判断；
- `evidence_refs`：真实证据引用；
- `confidence`：在当前声明边界内的可信度；
- `so_what`：它改变了什么认识或选择；
- `challenges`：仅保留仍会实质改变判断的反证、替代解释或边界。

不能成立的候选判断应删除或降为 open issue，而不是用更多文字包装。

### 4. 形成 thesis options

把能够共同回答本轮问题的 findings 组合成 2–3 组候选论点。每组包含一个 `main_thesis` 和 2–4 个 `sub_theses`：

- 每个 sub-thesis 必须引用真实 finding，置信度不得高于依赖的 findings；
- `best_for` 说明该组选项最适合支持什么讨论或判断；
- `evidence_strength` 说明当前证据能支持到哪里；
- `tradeoffs` 说明选择这一视角会突出和弱化什么。

不要替用户排序或选择“最佳答案”，也不要把分论点排成章节。用户反馈“都不好”或提供新方向时，在同一证据边界内重组 options；除非新增材料，否则不要制造新事实。

### 5. 完成交接

仅把会影响用户选择或下游判断、且当前材料无法解决的问题写入 `open_issues`。对需要直接看数据才能理解的核心论据，写入 `visual_evidence_candidates`，说明要看见什么、为什么重要以及对应的 finding/evidence；不决定图表样式或版式。

## Output

### `contract_profile=v0_3`

按 `analysis.v1` schema 提交单个 JSON 对象：

- `findings[]`
- `thesis_options[]`
- `visual_evidence_candidates[]`
- 必要时的 `open_issues[]`

不额外输出执行过程、质量检查、章节、页面或格式设计。runtime 负责 agent、schema、路径、状态和 coverage 等 bookkeeping。

## v0.4 简化交接

当 runtime 声明 `contract_profile=v0_4` 时，提交可独立阅读的 `analysis.md`，至少包含：

- `# Analysis`
- `## 核心发现`
- `## 竞争性解释与边界`
- `## 候选论点组`
- `## 待验证问题`

自然文本仍须保留判断、证据引用、置信度、会改变判断的挑战和 so what；候选论点组仍给出 2–3 组真实选择。不要为方便机器处理而拆散完整分析。
