# E2E 汇报材料评测

该目录保存与生产 Worker rubrics 解耦、可版本化冻结的 E2E 评测契约。

## 目录

```text
evals/
├── rubrics/
│   └── e2e_material_v0.2.json
├── regression/
│   ├── strategy_quality_v1.json
│   └── ds_quality_golden.v1.json
├── schemas/
│   └── e2e_judgement.v1.json
└── README.md
```

每个 evaluation run 会把 rubric 和 schema 复制为快照，因此后续更新 rubric 文件不会改变历史评测结果。

## 运行

```bash
python -m presentation_agent.cli eval start \
  --artifact outputs/example.pptx \
  --brief-file examples/raw_brief.json \
  --material examples/source.xlsx \
  --rubric v0.2
```

`start` 返回 Content Judge 的 `instruction_path` 和 `output_path`。宿主 Agent 按 instruction 写回 JSON 后：

```bash
python -m presentation_agent.cli eval submit --run <run-dir>
```

第一次 `submit` 会进入 Visual Judge；第二次完成聚合。也可以显式读取当前任务和结果：

```bash
python -m presentation_agent.cli eval next --run <run-dir>
python -m presentation_agent.cli eval status --run <run-dir>
python -m presentation_agent.cli eval result --run <run-dir>
```

## 格式适配

- PPT/PPTX：提取 slide 文本，并经 LibreOffice/Poppler 渲染为逐页 PNG。
- DOC/DOCX：提取正文文本，并经 LibreOffice/Poppler 渲染为逐页 PNG。
- HTML：提取可见文本，并经 Playwright 生成 `.unit` 截图或视口分片截图。
- 所有格式都会尝试生成 contact sheet；Visual Judge 同时获得 contact sheet 和逐页原图。

视觉快照缺失属于 blocking hard gate。系统不会把“只读取 PPT/DOCX/HTML 文本”伪装成完整视觉评测。

## Run 产物

```text
<eval-run>/
├── run_state.json
├── rubric_snapshot.json
├── judgement_schema_snapshot.json
├── deterministic_checks.json
├── prepared_artifact.json
├── prepared/
│   ├── artifact_text.txt
│   ├── evaluation_context.txt
│   ├── contact-sheet.png
│   └── pages/page-XXX.png
├── handoff/
│   ├── instruction_content.md
│   ├── output_content.json
│   ├── instruction_visual.md
│   └── output_visual.json
├── judgement_content.json
├── judgement_visual.json
└── final_report.json
```

## 扩展 rubric

新增版本时复制 `e2e_material_v0.2.json`，更新 `version` 和文件名即可。维度权重必须合计为 `1.0`；新增或删除维度时，需要同步更新 Judge schema 和 `runner.py` 的 job-to-dimension 映射。
