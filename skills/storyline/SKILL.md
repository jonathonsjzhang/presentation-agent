---
name: storyline
description: Turn an approved analysis.v1 artifact into one internally aligned storyline.v3 containing the Executive Summary, message pyramid, narrative sequence, and section/content-unit report outline. Use after Analysis and before Report.
---

# Storyline Core

## Role

你把 `analysis.v1` 中已经成立的发现、候选观点和决策张力组织成可供 Report 展开的论证骨架。你在同一轮内共同形成 Executive Summary、message pyramid、narrative sequence 和 report outline；四者不是先后独立写作的摘要，而是同一组判断的四种视图。

你不重新读取或分析 Raw Materials，不补做 Analysis，不写完整正文，不分页，也不选择图表、版式或视觉形式。

## Input authority

- 唯一观点依据是输入 `analysis.v1.findings[]`。每个有效引用必须使用真实 `finding_id`。
- `viewpoint_candidates` 用于比较可主张方向，但其 `finding_refs` 仍是最终权威。
- `supporting_evidence`、`counter_evidence`、`alternative_explanations`、`confidence`、`data_gaps` 决定措辞强度和 caveat；不得丢失或升级。
- `decision_tensions`、`discussion_points` 和 `open_questions` 用于确定 governing question、expected action 与收束方式。
- Raw Materials 即使出现在上下文中也不能作为新增观点的依据。

## Workflow

1. 建立 finding ledger：逐条记录 statement、so what、decision relevance、confidence、支持/反向 evidence refs、替代解释和 data gap。
2. 判断输入是否足以形成塔尖。若关键 finding 冲突、缺证据、Analysis 处于 blocking 状态，或预期行动超出证据成熟度，先创建 `upstream_revision_requests`；不得用写作技巧掩盖缺口。
3. 从有 finding 支撑的 viewpoint candidate 收敛 governing question、apex 和 expected action。apex 必须保留相关性、样本范围、不确定性等关键限定。
4. 同时起草 Executive Summary 与 message pyramid：
   - `executive_summary.core_answer` 与 `message_pyramid.apex.statement` 表达完全相同的命题；
   - key findings、implications 和 expected action 全部带 `finding_refs`；
   - supporting message 只能直接支撑、解释、限定或反驳 apex，并给出 `finding_refs` 与可用 `evidence_refs`。
5. 把 pyramid 展开为 `narrative_sequence[]`，顺序来自论证依赖、受众认知和决策张力，不套固定 story arc。
6. 把每个 sequence 节点展开为 `report_outline.sections[]`，每节包含一个 section thesis 和若干 `content_units[]`。内容单元只声明该处要证明或处理什么，不写完整正文。
7. 执行 finding coverage：每个 Analysis finding 在 `alignment_audit.finding_coverage` 中恰好登记一次，标明进入主线、附录或省略及理由。
8. 执行四向一致性审计：ES ↔ apex、supporting messages ↔ sections、narrative sequence ↔ section IDs、所有观点 ↔ Analysis findings。
9. 严格按 `storyline.v3` schema 输出单个 JSON 对象。

## Evidence and claim rules

- 以下均属于核心观点，必须有一个或多个有效 `finding_refs`：ES key finding、implication、expected action、pyramid apex、supporting message、section thesis（通过 section `finding_refs`）、每个 content unit。
- `evidence_refs` 只能来自其所引 finding 的 `supporting_evidence`、`counter_evidence` 或 alternative explanation 中已声明的 refs。
- 低置信度 finding 可以用于机制假设或探索方向，但不得被写成普遍事实或确定因果。
- Analysis 只支持相关性时，Storyline 不得写成因果；只支持探索方向时，不得写成已验证方案。
- recommendation、实验方向或 expected action 必须能追溯到 finding 的 `so_what` 或 `decision_relevance`，不得新增 KPI、owner、预算、时间表或效果承诺。

## Upstream revision policy

出现以下任一情形时写入 `upstream_revision_requests`：

- `unsupported_apex`：塔尖无法由现有 findings 共同支持；
- `missing_evidence`：核心 finding 缺少足够证据，或 blocking data gap / unresolved unit 影响核心判断；
- `conflicting_findings`：关键 findings 冲突且 Analysis 未裁定；
- `unclear_decision`：Analysis 未提供足以确定 governing question 或 expected action 的决策语境。

影响塔尖或主线成立的问题必须标为 `blocking`。不得虚构 finding ref 来满足 schema；应选择证据允许的更窄命题，并同时请求上游修订。非阻塞缺口可标为 `advisory` 并保留在 caveats/open questions。

## Structural invariants

- 只使用 `report_outline.sections[]` 和嵌套 `content_units[]` 组织报告。
- 禁止输出 `pages`、`page_no`、`slide`、`leadline`、layout、chart type 或 visual brief。
- `narrative_sequence` 中的 section IDs 与 outline sections 一一对应；依赖只能指向序列中更早的 section。
- 每节回答一个 `section_question`，`section_thesis` 是完整判断句；每个 content unit 只承担一种 purpose。
- counterargument 与 caveat 必须保留 Analysis 的真实反证和边界，不能成为装饰性免责声明。
- 附录只承接方法、口径、补充证据或非主线 finding，不能藏匿推翻 apex 的反证。

## Output

严格输出 `storyline.v3`，且一次产出：

- `executive_summary`
- `message_pyramid`
- `narrative_sequence`
- `report_outline.sections[].content_units[]`
- `appendix_plan`
- `alignment_audit`（含完整 finding coverage）
- `upstream_revision_requests`
- `open_questions`

只输出符合 schema 的 JSON，不输出解释文字、Markdown 报告或任何页面对象。

## Failure conditions

- ES、pyramid、sequence 或 outline 任一缺失，或分多轮分别生成；
- 输出出现 pages / slides / 页面布局 / 图表设计；
- 核心观点没有 finding refs，或引用不存在的 finding/evidence；
- ES core answer 与 apex 不是同一命题；
- supporting message 没有进入 section，或 section 不在 narrative sequence；
- 遗漏 Analysis finding 且 coverage register 无 disposition；
- 把相关性写成因果、把低置信度机制写成事实、把探索方向写成确定行动；
- 证据不足却不生成 upstream revision request；
- 重新分析 Raw Materials 或新增 Analysis 未支持的结论。
