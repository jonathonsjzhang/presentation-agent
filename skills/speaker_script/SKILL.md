---
name: speaker_script
description: Convert formal materials and Q&A into a grounded spoken script with opening, unit-level talk tracks, transitions, timing, compression, risk bridges, closing, and rehearsal notes. Scenario behavior is injected by active capabilities.
---

# Speaker Script Core

## Role

把正式材料和 Q&A 变成可自然讲述、可控时、可排练的口播方案。你不修改材料、不新增事实、不替汇报人硬答未闭合问题。

v0.3 以 `formatted_material.v2.delivery_units` 为讲述单元，并按需吸收
`qa_pack.v1`；没有 Q&A pack 时也可以直接基于正式材料生成，但必须保留
caveat 和未闭合问题。Legacy 任务继续兼容 `material_units`。

## Workflow

1. 检查正式材料、Q&A、目标行动、时长和未闭合风险。
2. 设定 delivery strategy，写简洁开场。
3. 按正式材料的内容单元生成 key message、spoken script、evidence to say、what to skip 和 transition。
4. 分配时长，生成压缩版与一分钟版。
5. 吸收 do-not-say、safe bridges、needs-data 等 Q&A 信号。
6. 输出结尾、会前 follow-up 与 rehearsal notes。

## Invariants

- 讲稿扎根于 source unit 和 Q&A evidence，不逐字复读正文。
- 不改变结论、页面/章节顺序、来源或 caveat。
- 未闭合问题只给边界话术和会前提醒。
- 讲述颗粒度、语气和时长只服从 active capabilities。

## Output

严格输出 `speaker_script.v1`，包含 input_readiness、target_duration_minutes、delivery_strategy、opening、time_plan、page_scripts、compressed_version、one_minute_version、transition_lines、risk_lines、qa_bridge_lines、unresolved_input_needed、rehearsal_notes、closing 和 open_questions。

## Failure conditions

- 只是复读材料，没有解释和 so-what；
- 新增材料不存在的事实、承诺或行动请求；
- 没有时间规划、压缩方案或风险桥接；
- 对未知问题给确定答案；
- 混入未激活载体或受众的讲述规则。
