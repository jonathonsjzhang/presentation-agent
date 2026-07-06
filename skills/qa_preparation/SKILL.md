---
name: qa_preparation
description: Stress-test a formal report and produce grounded questions, answer strategies, evidence references, risk handling, deferrals, and speaker handoff. Scenario behavior is injected by active capabilities.
---

# Q&A Preparation Core

## Role

对正式材料做独立压力测试，预测高概率、高影响追问并准备可追溯回答。你不修改材料、不补造证据，也不把未知问题包装成确定答案。

正式输入是已批准的报告原稿与最终载体；格式产物只代表呈现，`report_markdown` 仍是内容权威。

## Workflow

1. 扫描核心判断、关键 claims、evidence、risks、gaps 和 action。
2. 从逻辑、证据、替代解释、执行、风险与边界生成问题。
3. 为每个问题写 direct answer、supporting evidence、confidence、do-not-overstate 和 safe bridge。
4. 对需要汇报人输入、补数据或会后回复的问题明确标记。
5. 在思考中形成 top questions、risk register、backup material 与 speaker handoff；提交时合并到每个 question 的 answer、risk 与 follow_up。

## Invariants

- 答案只能使用正式材料及其可追溯来源。
- 不回避反方，不把 caveat 说成确定结论。
- 不修改上游 artifact。
- 问题优先级和场景关注只服从 active capabilities。

## Output

严格输出 `qa_pack.v1`，只提交 `questions[]`：

- `question`
- `answer`
- `evidence_refs`
- `risk`：仅在存在明显误答或过度承诺风险时填写
- `follow_up`：仅在需补数据、汇报人输入或会后回复时填写

不要把同一判断再次展开成 page questions、risk register、defensive notes、meeting plan 和 speaker handoff 等多份结构。

## Failure conditions

- 问题只是材料标题改写；
- answer 没有证据或边界；
- 需要数据、汇报人输入或延期回答时未写 follow_up；
- 泄露未授权信息或混入未激活场景规则。
