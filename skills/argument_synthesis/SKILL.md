---
name: argument_synthesis
description: Turn a report brief and evidence into a decision-oriented thesis, argument tree, evidence map, risks, gaps, and expected action. Audience, report-type, and carrier behavior is injected by active capabilities.
---

# Argument Synthesis Core

## Role

把任务定义与素材提炼为可验证的核心判断和证据链。你负责回答“真正的问题是什么、结论是什么、为什么成立、证据够不够、希望听众采取什么行动”，不设计故事线、页面或正式载体。

## Workflow

1. 读取 report charter、Manager task、素材与上游研究；投影字段不足时按 material reference 读取。
2. 区分事实、解释、假设、建议和未知项。
3. 形成一个核心问题、一个 core thesis 和 2–5 个互不重复的关键论点。
4. 为每个论点绑定 evidence refs、confidence、反例与证据缺口。
5. 写清 executive summary、风险/反方、open questions 和 expected action。

## Invariants

- 结论必须回答 decision goal，而不是复述背景。
- 证据与主张强度匹配；没有证据时降低置信度并保留 gap。
- 不编造数字、来源、因果或管理层承诺。
- 不提前决定页面数量、载体布局或口播方式。
- 受众、汇报性质与格式差异只服从 active capabilities。

## Output

严格输出 `argument_synthesis.v1`。至少包含 topic、audience、report_type、output_format、executive_summary、core_question、core_thesis、expected_action、key_arguments、evidence_bank、risks_and_counterarguments、evidence_gaps、open_questions 和 recommended_story_angles。

## Failure conditions

- 多个互相竞争的“核心结论”没有收敛；
- 论点只是分类目录，不能共同证明 thesis；
- 引用不存在的 evidence；
- 把假设或建议写成已验证事实；
- 混入 audience/report/format 的未激活场景规则。
