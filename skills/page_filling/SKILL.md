---
name: page_filling
description: Expand an approved storyline into evidence-grounded content units, proof chains, copy blocks, visual briefs, sources, gaps, and a draft render handoff. Scenario behavior is injected by active capabilities.
---

# Page Filling Core

## Role

把 storyline 的每个内容单元填成可正式制作的 dummy content。你负责行动标题、proof chain、正文块、图表 brief、来源、缺口和 draft handoff，不改变故事线与核心结论。

## Workflow

1. 对每个 storyline unit 锁定 question、takeaway、evidence refs 与 role。
2. 写 headline、proof chain 和高密度 content blocks。
3. 将可视化关系写成结构化 visual plan；数据不足时明确占位和补数任务。
4. 继承 sources、confidence、caveat 和 gaps。
5. 检查单元间重复、密度、可读性及下游格式化所需字段。

## Invariants

- 一个单元只服务一个 takeaway。
- 正文中的数字、事实和因果都可追溯。
- 图表 brief 不得假设不存在的数据。
- 不重排 storyline，不把 gap 藏进脚注。
- 颗粒度、密度和载体表现只服从 active capabilities。

## Output

严格输出 `page_content.v1`，包含 pages、global_sources、global_data_gaps、open_questions、draft_material、format_handoff_summary 和必要的状态建议。

## Failure conditions

- 正文只是标题的同义改写；
- 证据不足却生成确定图表；
- 来源、口径、confidence 或 caveat 丢失；
- 混入未激活载体的结构规则。
