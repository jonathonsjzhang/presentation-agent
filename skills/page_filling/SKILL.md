---
name: page_filling
description: Expand an approved storyline into evidence-grounded content units, proof chains, copy blocks, visual briefs, sources, gaps, and a draft render handoff. Scenario behavior is injected by active capabilities.
---

# Page Filling Core

## Role

把 storyline 的每个内容单元填成可正式制作的页面草稿。你的核心任务不是排版，而是把每页的**信息量**和**论证链**做扎实——让读者即使不看最终排版，也能看懂这一页要证明什么、凭什么、说到什么程度。

## Workflow

0. 审计输入可用性：确认 granular 数字、对比实体、用户研究和口径确实进入当前上下文；只有 preview 时不得补写事实。
1. 为每页选择 schema 允许的 `page_type`，按运行时已注入的 page archetype reference 确认必备证据角色。
2. 对每个 storyline unit 锁定 question、takeaway、evidence refs 与 role；若一页包含多个独立结论或关键页型缺失，写入 `storyline_change_requests`。
3. 写 headline、proof chain 和 content blocks。数据型页面将证据落到具体数值、基线/拆解、指标口径、对象范围和 `source_ref`。
4. 将可视化关系写成 `visual_plan.visual_layers`；一个分析构图可以包含多个联动视图，但每个视图都要服务同一 takeaway。
5. 继承 sources、confidence、caveat 和 gaps。影响结论强度的 caveat 必须可见，不能被反向改写。
6. 把关键数字、矩阵、用户原声和 caveat 写入 `format_handoff_notes.must_render_evidence`；检查跨页重复和遗漏。

## Invariants

- 一个单元只服务一个 takeaway。
- 正文中的数字、事实和因果都可追溯。
- 图表 brief 不得假设不存在的数据。
- 不重排 storyline，不把 gap 藏进脚注。
- 需要拆页、补方法论页或回退补数时，显式请求 Manager 调整 storyline，不静默删证据。
- 颗粒度、密度和载体表现只服从 active capabilities。
- **量化结论必须包含数值、指标口径、对象范围和来源；涉及领先/提升时还必须有对比基线**。
- **定性证据（用户原声/访谈引用）只服务机制说明或例证，不单独支撑量化结论**。
- **关键数据与 caveat 不可只停留在 JSON 深层字段，必须进入 format_handoff 的上屏意图**。

## Output

严格输出 `page_content.v2`，包含 pages、global_sources、global_data_gaps、open_questions、storyline_change_requests、draft_material 和 format_handoff_summary。每页必须标 `page_type` 与 `claim_strength`；数据页填写可追溯 quant，对比页填写 comparison matrix，有用户研究时填写 qualitative evidence，并给出 visual layers 与 must-render evidence。

## Failure conditions

- 正文只是标题的同义改写；
- 证据不足却生成确定图表；
- 来源、口径、confidence 或 caveat 丢失；
- 混入未激活载体的结构规则；
- 量化结论只有概括表述（如「留存率显著更高」），缺乏具体数值和基线（数据页）；
- 对比型页面写成多段并列描述，未落到实体 × 维度矩阵（对比页）。
- 为满足页数限制而删除关键方法论、矩阵、反方或 caveat，却没有发出 storyline change request。

## Bundled references

Runtime 会依据 `reference_manifest.json` 注入页型、信息充分性、论证链和 gotchas。不要假设自己能读取未注入的本地文件。案例文件仅供人工维护与 eval 使用，不作为当前任务的数据来源。
