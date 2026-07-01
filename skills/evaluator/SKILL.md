---
name: evaluator
description: Run the host-self-executed E2E material evaluation protocol for PPT, DOCX, or HTML deliverables.
---

# E2E 汇报材料评测 Skill

本 Skill 是薄宿主适配器。评分标准、格式预处理、状态推进和聚合逻辑位于仓库的 `evals/` 与 `presentation_agent/evaluation/`，不要在宿主侧复制或改写。

## 目标

评测一个已经生成的 PPT、DOCX 或 HTML 是否把既有 raw material 转化成可供目标受众理解、讨论和决策的正式汇报材料。

## 协议

```bash
python -m presentation_agent.cli eval start \
  --artifact <final.pptx|final.docx|final.html> \
  --brief-file <brief.json> \
  --material <source-1.xlsx> \
  --material <source-2.docx>

python -m presentation_agent.cli eval next --run <eval-run>
python -m presentation_agent.cli eval submit --run <eval-run>
python -m presentation_agent.cli eval status --run <eval-run>
python -m presentation_agent.cli eval result --run <eval-run>
```

## 宿主执行规则

1. `eval start` 会冻结 rubric 快照、抽取文本并按格式生成视觉快照。
2. 读取命令返回的 `instruction_path`。
3. 在干净上下文中执行当前 Judge 指令，只把严格 JSON 写到 `output_path`。
4. 调用 `eval submit`。若返回下一条 instruction，重复第 2–4 步。
5. `status=completed` 后读取 `final_report.json`。

## 上下文隔离

- 不把生产 Agent 的自评、review、memory 或返工理由交给 Judge。
- Content Judge 只评信息密度、Storyline 和表达精炼。
- Visual Judge 必须实际查看所有截图，只评信息呈现。
- PPT 不得只读提取文本；必须逐页查看 slide PNG。
- DOCX 必须查看渲染页，不能只按段落文本判断。
- HTML 必须查看页面/模块截图，不能只按 HTML 源码判断。

## 安全边界

- Eval run 是只读评测，不写入生产 memory。
- 不修改候选材料和原始素材。
- 不在评测时引入 rubric 之外的新维度。
- 分数只能使用 0–5、0.5 分刻度。
