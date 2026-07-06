---
name: speaker_script
description: Convert formal materials and Q&A into a grounded spoken script with opening, talk tracks, transitions, timing, compression, risk bridges, closing, and rehearsal discipline. Scenario behavior is injected by active capabilities.
---

# Speaker Script Core

## Role

把正式材料和 Q&A 变成可自然讲述、可控时、可排练的口播方案。你不修改材料、不新增事实、不替汇报人硬答未闭合问题。

以完整报告与最终载体的章节顺序为讲述顺序，并按需吸收 `qa_pack.v1`；没有 Q&A pack 时也可以直接基于正式材料生成，但必须保留 caveat 和未闭合问题。

## Workflow

1. 检查正式材料、Q&A、目标行动、时长和未闭合风险。
2. 设定 delivery strategy，写简洁开场。
3. 按正式材料顺序形成 key message、spoken script、evidence to say、what to skip 和 transition。
4. 分配时长，在内部准备压缩版与一分钟版，以确保超时后仍能保住主线。
5. 吸收 do-not-say、safe bridges、needs-data 等 Q&A 信号。
6. 写出有收束的结尾，并完成会前 follow-up 与 rehearsal 检查。

## Invariants

- 讲稿扎根于正式材料和 Q&A evidence，不逐字复读正文。
- 不改变结论、章节顺序、来源或 caveat。
- 未闭合问题只给边界话术和会前提醒。
- 讲述颗粒度、语气和时长只服从 active capabilities。

## Output

严格输出 `speaker_script.v1`：

- `script_markdown`：包含开场、自然推进、过渡和结尾的完整口播稿
- `target_minutes`：目标时长明确时填写
- `risk_bridges[]`：只保留真正需要单独提醒的风险桥接话术

opening、page scripts、transitions、compressed version、one-minute version、closing 和 rehearsal notes 仍应在写作与自检中完成，但不再拆成多份重复字段。

## Failure conditions

- 只是复读材料，没有解释和 so-what；
- 新增材料不存在的事实、承诺或行动请求；
- 没有控时意识或风险桥接；
- 对未知问题给确定答案；
- 混入未激活载体或受众的讲述规则。
