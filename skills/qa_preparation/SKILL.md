---
name: qa_preparation
description: Stress-test a formal report and produce grounded questions, answer strategies, evidence references, risk handling, deferrals, and speaker handoff. Scenario behavior is injected by active capabilities.
---

# Q&A Preparation Core

## Role

对正式材料做独立压力测试，预测高概率、高影响追问并准备可追溯回答。你不修改材料、不补造证据，也不把未知问题包装成确定答案。

v0.3 的正式输入是 `formatted_material.v2`：以 `delivery_units`、来源映射、
`caveat_preservation`、`omitted_content_register` 和质量检查为权威。Legacy
任务仍可读取 `formatted_material.v1.material_units`，不得混淆两套字段。

## Workflow

1. 扫描 headline、关键 claims、evidence、risks、gaps 和 action。
2. 从逻辑、证据、替代解释、执行、风险与边界生成问题。
3. 为每个问题写 direct answer、supporting evidence、confidence、do-not-overstate 和 safe bridge。
4. 对需要汇报人输入、补数据或会后回复的问题明确标记。
5. 形成 top questions、risk register、backup material 与 speaker handoff。

## Invariants

- 答案只能使用正式材料及其可追溯来源。
- 不回避反方，不把 caveat 说成确定结论。
- 不修改上游 artifact。
- 问题优先级和场景关注只服从 active capabilities。

## Output

严格输出 `qa_pack.v1`，包含 top_questions、risk_register、backup_material_plan、speaker_script_handoff、defensive_notes、meeting_handling_plan、data_gaps_to_close 和 pre_meeting_followups。

## Failure conditions

- 问题只是材料标题改写；
- answer strategy 没有证据或边界；
- 未标记 needs_data / needs_presenter_input / should_defer；
- 泄露未授权信息或混入未激活场景规则。
