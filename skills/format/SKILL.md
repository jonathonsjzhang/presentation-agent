---
name: format
description: Convert approved page content into a render-ready formal deliverable while preserving conclusions, evidence, sources, gaps, and downstream traceability. Carrier-specific PPT, document, or HTML behavior is injected by the active format capability.
---

# Format Core Skill

## Role

把 `page_content.v2` 转为 `formatted_material.v1`。你负责正式表达、信息层级、来源与缺口呈现、renderer handoff 和下游交接，但不重新做论点、故事线、Q&A 或逐字稿。

本 Skill 只定义三种载体共有的稳定职责。本轮只能执行 compiled package 中唯一激活的 `format.*` capability；不要自行加载或混用其他载体流程。

## Input readiness

开始前检查：

- 存在 `pages[]` 或 `draft_material.material_units[]`；
- 目标格式已在 report charter 与 active capability 中确定；
- 每个上游单元能追溯 page takeaway、证据、来源和 data gap；
- 需要的原始细节若被投影，应按 `material_refs[].artifact_path` 读取，不能根据 preview 补写事实。

输出 `input_readiness.status = ready | partial | blocked`。输入不完整时可以生成 provisional spec，但必须把缺口写进对应单元和 `open_design_tasks`，不得把 deliverable 标为 completed。

## Stable workflow

1. 审计输入，记录无法保真的内容或 renderer 阻断。
2. 逐页读取 `must_render_evidence`、`on_screen_numbers`、comparison matrix、qualitative evidence、visual layers 和 caveat。
3. 依据唯一 active `format.*` capability 生成正式单元；一个分析构图可以包含多个联动视图，不把复杂证据强行退化为单图 + prose。
4. 填写 `evidence_trace`：逐项记录已上屏证据、被省略证据及理由。
5. 保持每个单元与 `source_page_no`、结论、证据和缺口的映射。
6. 建立 `artifact_manifest`、`render_plan` 与 `quality_checks`。
7. 把弱证据、风险页、caveat 和 speaker note seed 交给 Q&A / speaker。

## Invariants

- 不改变 core thesis、故事线顺序、结论强度或证据含义。
- 不新增无来源事实，不隐藏 low confidence、caveat 或 blocking gap。
- 每个正式单元只服务一个主要 takeaway，并有明确的信息层级。
- sources、confidence、data gaps 和 open tasks 必须进入正式内容或交付清单。
- `must_render_evidence` 中的项目必须上屏；确因版面省略时写入 `omitted_evidence_refs` 和具体理由，不能静默丢失。
- comparison matrix 优先转为表格、热力图、散点或多面板，不得退化为按实体分段的 prose。
- qualitative evidence 仅用于机制、例证或反例，并保留 attribution 与 source ref。
- Agent 只描述 render intent；`render_result=rendered` 只能由真实 renderer 回填。
- artifact 的 `format` 必须与 compiled `format.*` capability 一致。

## Output contract

严格输出 `formatted_material.v1`，至少包含：

- `agent_id`, `schema`, `topic`, `audience`, `format`
- `input_readiness`
- `artifact_manifest`
- `render_plan`
- `material_units[]`, `appendix_units[]`
- `style_tokens`
- `source_policy`, `gap_policy`, `redaction_policy`
- `format_decisions[]`
- `open_design_tasks[]`
- `downstream_handoff`
- `quality_checks[]`

每个 `material_unit` 至少包含：

- `unit_id`, `source_page_no`, `unit_type`, `headline`
- `layout_or_structure`
- `finalized_content`
- `visual_object`
- `evidence_trace`
- `source_display`
- `gap_display`
- `speaker_note_seed`
- `question_risk_tags[]`
- `quality_status`

载体专属的 unit type、renderer、结构、图表限制和 QA 标准只服从本轮 active format capability。

## Failure conditions

- artifact 格式与 active capability 冲突；
- 为排版修改或删除上游结论；
- 丢失来源、口径、关键限定条件或阻断缺口；
- 只有格式建议，没有正式材料单元；
- 未真实渲染却声称 completed；
- 同一产物混入两种或三种载体结构。
