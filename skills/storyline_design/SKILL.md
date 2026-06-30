---
name: storyline_design
description: Convert an approved argument into a coherent report narrative, title-read path, content-unit sequence, evidence placement, appendix plan, and open questions. Scenario behavior is injected by active capabilities.
---

# Storyline Design Core

## Role

把 argument synthesis 变成可连读、可验收的叙事骨架。你决定内容单元的顺序、问题、结论标题、证据职责和转场，不撰写完整正文、不做正式设计。

## Workflow

1. 锁定 core thesis、expected action、关键论点与证据边界。
2. 选择一条主叙事角度，并说明未选角度的取舍。
3. 设计 opening、主体推进、风险/边界和 closing。
4. 每个内容单元只回答一个问题、给一个 takeaway，并绑定 evidence refs。
5. 做 title-read test、重复检查、证据覆盖检查和 appendix 分流。

## Invariants

- 标题连读能够独立讲清“问题—判断—证据—行动”。
- 不改变上游 thesis、证据含义、confidence 或 gap。
- 内容单元的颗粒度和长度只服从 active format/report capabilities。
- 不编造页面正文、数据或图表结果。

## Output

严格输出 `storyline.v1`，包括 topic、audience、report_type、output_format、selected_story_angle、story_arc、title_read_test、pages、appendix_plan 和 open_questions。

## Failure conditions

- 结构是素材目录而非论证推进；
- 多个单元重复同一 takeaway；
- 标题是主题词、问题句或无 so-what 的描述；
- evidence refs 与上游不一致；
- 混入未激活场景的颗粒度和载体规则。
