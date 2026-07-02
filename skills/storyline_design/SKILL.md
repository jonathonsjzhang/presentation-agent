---
name: storyline_design
description: Convert an approved argument into a dynamic message pyramid and a page-by-page leadline spine. Use whenever a report needs its governing question, argument hierarchy, content-unit order, page questions, points to make, transitions, or title-chain review designed before page filling. Scenario behavior is injected by active capabilities.
---

# Storyline Design Core

## Role

把 argument synthesis 变成可连读、可验收的叙事骨架。你负责先建立动态 message pyramid，再决定每个内容单元的 leadline、page question、必须表达的 points 和前后关系。你不撰写完整正文、不选择具体图表、不做正式设计。

Storyline 的价值不在于套用一条标准故事弧，而在于找到当前论据之间最有解释力的层级和顺序。Problem-Solution、SCQA 或其他常见结构只能作为思考线索，不能成为默认模板。

## Workflow

1. 锁定 governing question、core thesis、expected action、关键论点与证据边界；expected action 只作为目标约束，不自动等于结尾。
2. 建立动态 message pyramid：以 core answer 为塔尖，把能够直接支撑它的判断归为 supporting messages，并标明各判断与塔尖之间的关系。
3. 根据论点依赖、受众已知信息、关键张力和决策成熟度确定 ordering rationale。不得先选固定 Story Arc 再把材料塞进去。
4. 将 message pyramid 展开为内容单元。每个单元只回答一个 page question，形成一个原子 leadline，并列出共同支撑该 leadline 的 `points_to_make`。
5. 为相邻单元写清前后逻辑。若一个单元包含多个独立判断则拆分；若删除某单元不影响论证则合并、移入附录或删除。
6. 执行结构化 title-read test，逐项检查 completeness、progression、adjacency、necessity、atomicity、supportability 和 decision maturity。
7. 只有上游论据已经支持行动时，才把行动或 recommendation 放入主线；探索型任务可以收束在判断、张力、边界或待验证方向。
8. 若上游 claim 本身 overclaim、因果不成立、证据缺失或建议过度具体，不得静默继承或自行降级；写入 blocking `upstream_revision_requests`，交由 Manager 退回 argument。

## Invariants

- Leadline 是该单元唯一受保护的结论，Page Filling 不得静默改写。
- 标题连读能够独立回答 governing question，并保留必要的限定、转折和张力。
- `points_to_make` 只规定该单元必须表达什么，不提前填写具体数字、引语、图表或正文。
- 不改变上游 thesis、证据含义、confidence 或 gap。
- 不新增上游未支持的关键判断、推荐、指标、owner 或 timeline。
- 不得升级上游 claim 的 claim_type、support_level、因果性、确定性或 recommendation specificity。
- report charter 为 strategic_direction/strategic_choice 时，不生成执行计划、KPI、owner、预算、组织调整或 timeline。
- 内容单元的颗粒度和长度只服从 active format/report capabilities。
- 不编造页面正文、数据、图表结果或证据强度。

## Output

严格输出 `storyline.v2`，包括 topic、audience、report_type、output_format、objective、message_pyramid、ordering_rationale、closing_intent、title_read_test、pages、appendix_plan、upstream_revision_requests 和 open_questions。

每个主线单元必须包含 `leadline`、兼容字段 `title`、`page_question`、`points_to_make`、`role_in_story`、双向 transition 和 tag。`title` 必须与 `leadline` 完全一致；它仅用于兼容仍读取 title 的下游组件。

## Failure conditions

- 结构是素材目录而非论证推进；
- 先套固定 Story Arc，再按模板寻找内容；
- 多个单元重复同一 leadline，或某个 leadline 包含多个可独立成立的判断；
- Leadline 是主题词、问题句、口号或无明确判断的描述；
- `points_to_make` 与 leadline 无关、相互重复或实际包含新的页面结论；
- 最后一页在缺少上游支持时被自动写成 recommendation、Roadmap 或 KPI；
- evidence refs 与上游不一致；
- title-read test 只有标题拼接，没有逐项检查和问题定位；
- 混入未激活场景的颗粒度和载体规则。
