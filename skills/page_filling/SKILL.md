---
name: page_filling
description: Expand an approved storyline into evidence-grounded content units, proof chains, copy blocks, visual briefs, sources, gaps, and a draft render handoff. Scenario behavior is injected by active capabilities.
---

# Page Filling Core

## Role

把 storyline 的每个内容单元填成可正式制作的页面草稿。你的核心任务不是排版，而是把每页的**信息量**和**论证链**做扎实——让读者即使不看最终排版，也能看懂这一页要证明什么、凭什么、说到什么程度。

## Workflow

0. 确认每页的 `page_type` / `role_in_story`，参照 `references/page_archetypes.md` 中该页型的内容范式与「够厚」的期望。
1. 对每个 storyline unit 锁定 question、takeaway、evidence refs 与 role。
2. 写 headline、proof chain 和高密度 content blocks。数据型页面期望量化证据落到「数值 + 对比基线 + 口径」三要素。
3. 将可视化关系写成结构化 visual plan；数据不足时明确占位和补数任务。图表 brief 必须说明它要证明什么，不能只写「做柱状图」。
4. 继承 sources、confidence、caveat 和 gaps。影响结论强度的 caveat 必须保留且不能被反向改写。
5. 检查单元间重复、密度、可读性及下游格式化所需字段。

## Invariants

- 一个单元只服务一个 takeaway。
- 正文中的数字、事实和因果都可追溯。
- 图表 brief 不得假设不存在的数据。
- 不重排 storyline，不把 gap 藏进脚注。
- 颗粒度、密度和载体表现只服从 active capabilities。
- **量化结论必须落到「数值 + 对比基线 + 口径」三要素**（数据型页面期望，非数据页豁免）。
- **定性证据（用户原声/访谈引用）只服务机制说明或例证，不单独支撑量化结论**。
- **关键数据与 caveat 不可只停留在 JSON 深层字段，必须进入 format_handoff 的上屏意图**。

## Output

严格输出 `page_content.v2`（v1 超集），包含 pages、global_sources、global_data_gaps、open_questions、draft_material、format_handoff_summary 和必要的状态建议。数据型页面补 `evidence_steps[].quant`，对比型页面补 `comparison_matrix`，有用户研究则补 `qualitative_evidence`，每页标 `claim_strength`。

## Failure conditions

- 正文只是标题的同义改写；
- 证据不足却生成确定图表；
- 来源、口径、confidence 或 caveat 丢失；
- 混入未激活载体的结构规则；
- 量化结论只有概括表述（如「留存率显著更高」），缺乏具体数值和基线（数据页）；
- 对比型页面写成多段并列描述，未落到实体 × 维度矩阵（对比页）。

## 何时查阅 references（按需读，不要全量加载）

- 不确定一页该放哪些证据层次 → 读 `references/information_sufficiency.md`
- 要把零散证据串成论证 → 读 `references/argument_chain.md`
- 不确定这一页型该长什么样 / 该多厚 → 读 `references/page_archetypes.md`
- 写完后自检是否踩了高频坑 → 读 `references/gotchas.md`
- 想看人工稿 vs AI 稿的差距对照 → 读 `examples/retention_manual_vs_ai.md`
