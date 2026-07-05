---
name: format
description: Translate report.v1 into one target-specific formatted_material.v2 plan while preserving claims, evidence, caveats, and traceability.
---

# Format Core Skill

## Role

把 `report.v1` 语义转译为 `formatted_material.v2`。你负责载体表达、来源映射和转换审计，但不重新做分析、改写核心判断，也不调用 renderer。

本轮必须由 `delivery_target` 唯一选择 `format.document`、`format.ppt`、`format.html` 之一，不得混用载体能力。

## Input readiness

开始前检查：

- 输入 `schema` 必须为 `report.v1`，并包含 sections、claims、claim_evidence_map 与 format_handoff；
- task 中存在至多一个标量 `delivery_target`；缺省仅按 v0.3 默认值 `document` 处理；
- active capability 必须与 `delivery_target` 一致，且恰好一个 `format.*` 被激活；
- 每个交付单元能追溯 report section、claim 和 evidence；
- 需要的原始细节若被投影，应按 `material_refs[].artifact_path` 读取，不能根据 preview 补写事实。
- **数据真实性**：`visual_assets[].data` 必须来自 report tables / figure_specs / source refs，禁止使用模拟数据；数据不足时不创建该视觉资产，并在 quality check 中记录 warning/fail。
- 呈现形式所需 token（typography / color / chart palette）已就位或可在 active capability 的呈现形式子节中声明。

输入契约不匹配时停止并显式报错。

## Workflow

1. 枚举全部 section_id、claim_id、claim-evidence 映射及受保护 caveat。
2. 依据唯一 active capability 将 section 转为 document section、slide 或 HTML module。
3. 每个 delivery unit 显式记录 source_section_ids、source_claim_ids、source_evidence_refs。
4. 逐项记录压缩/合并/拆分/重排；省略内容必须进入 omitted_content_register。
5. 将 protected caveat 逐项映射到 destination unit，缺失时状态必须为 missing 且质量检查失败。
6. 只生成 artifact_manifest 与 render_plan；所有 render status 保持 planned。

## Invariants

- 不改变 core thesis、结论强度或证据含义；允许为载体重排，但必须留痕。
- 不新增无来源事实，不隐藏 low confidence、caveat 或 blocking gap。
- 不把上游战略方向丰富为 timeline、KPI、owner、预算、组织调整、里程碑、路线图或时间轴；上游未明确提供时，禁止选择 timeline layout。
- 每个正式单元只服务一个主要 takeaway，并有明确的信息层级。
- sources、confidence、data gaps 和 open tasks 必须进入正式内容或交付清单。
- Core 只描述 render intent；`render_result.status`、deliverable status 和 visual asset status 均只能为 `planned`。
- artifact 的 `delivery_target` 必须与 compiled `format.*` capability 一致。
- 呈现形式规则与业务规则冲突时，业务规则优先。

## Output contract

严格输出 `formatted_material.v2`，至少包含：

- `delivery_target`, `source_report_ref`, `source_section_ids`, `source_claim_ids`
- `delivery_units[]`, `visual_assets[]`
- `compression_decisions[]`, `omitted_content_register[]`, `caveat_preservation[]`
- `artifact_manifest`, `render_plan`, `render_result`, `quality_checks[]`

每个 delivery unit 必须映射至少一个真实 section 和 claim。顶层 source ID 集合必须完整覆盖 report 的 section / claim；各交付单元和视觉资产只能引用其中真实存在的 ID，不得生成不存在的 ID。

`compression_decisions` 即使为空也必须输出；凡 transformation 为 compressed/merged/split/reordered，必须有对应 decision。所有未进入 delivery units 的 report section、appendix 或实质内容都必须进入 omission register，且说明可恢复位置。

载体专属的 unit type、renderer、结构、图表限制和 QA 标准只服从本轮 active format capability。

## Failure conditions

- delivery_target 与 active capability 冲突或一次选择多个 target；
- 输入为 report.v1 却依赖非 `delivery_target` 的载体选择字段；
- 为排版修改或删除上游结论；
- 丢失来源、口径、关键限定条件或阻断缺口；
- 只有格式建议，没有正式材料单元；
- Core 阶段声称 rendered/completed；
- 同一产物混入两种或三种载体结构；
- 使用模拟数据填充图表/表格（违反数据真实性规则）。
