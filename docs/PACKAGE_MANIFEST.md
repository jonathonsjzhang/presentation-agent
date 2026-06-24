# 打包清单

archive 给别人时，以下全选、以下排除。

## ✅ 必须包含

### 引擎（不改）
```
presentation_agent/
├── __init__.py
├── cli.py
├── pipeline.py
├── step.py
├── loop.py
├── review.py
├── memory.py
├── launch.py
├── models.py
├── io.py
├── input_loader.py
├── skill_package.py
├── web.py
├── web_static/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── skills/
│   ├── __init__.py
│   ├── base.py
│   ├── generic.py
│   ├── registry.py
│   └── storyline.py
├── llm/
│   ├── __init__.py
│   ├── types.py
│   ├── schema.py
│   ├── client.py
│   ├── factory.py
│   └── adapters/
│       ├── __init__.py
│       ├── mock.py
│       ├── cli.py
│       └── inline.py
└── connectors/
    ├── __init__.py
    ├── base.py
    ├── registry.py
    ├── csv.py
    ├── docx.py
    └── xlsx.py
```

### Skill 包（行为定义）
```
skills/
├── _shared/
│   └── report_context.md
├── task_positioning/
│   ├── SKILL.md
│   ├── rubrics.json
│   └── schemas/
│       ├── raw_brief.v1.json
│       └── task_positioning.v1.json
├── argument_synthesis/
│   ├── SKILL.md
│   ├── rubrics.json
│   └── schemas/
│       ├── task_positioning.v1.json
│       └── argument_synthesis.v1.json
├── storyline_design/
│   ├── SKILL.md
│   ├── rubrics.json
│   └── schemas/
│       ├── argument_synthesis.v1.json
│       └── storyline.v1.json
├── page_filling/
│   ├── SKILL.md
│   ├── rubrics.json
│   └── schemas/
│       ├── storyline.v1.json
│       └── page_content.v1.json
├── format/
│   ├── SKILL.md
│   ├── rubrics.json
│   └── schemas/
│       ├── page_content.v1.json
│       └── formatted_material.v1.json
├── qa_preparation/
│   ├── SKILL.md
│   ├── rubrics.json
│   └── schemas/
│       ├── formatted_material.v1.json
│       └── qa_pack.v1.json
├── speaker_script/
│   ├── SKILL.md
│   ├── rubrics.json
│   └── schemas/
│       ├── formatted_material.v1.json
│       ├── qa_pack.v1.json
│       └── speaker_script.v1.json
└── report_builder/
    └── SKILL.md
```

### 配置文件
```
configs/
├── agents.json
└── llm.json
```

### 宿主集成
```
.claude/agents/report-builder.md
.codex/prompts/report-builder.md
```

### 示例 & 入口
```
examples/raw_brief.json
pyproject.toml
```

### 文档
```
README.md
GUIDEBOOK.md
汇报助手系统设计方案.md
docs/loop_engineering_notes.md
```

### 测试（可选）
```
tests/
├── test_cli_adapter.py
├── test_connectors.py
├── test_fixtures_valid.py
├── test_format_adaptation.py
├── test_launch.py
├── test_llm.py
├── test_loop.py
├── test_memory_maintain.py
├── test_multi_candidate.py
├── test_pipeline.py
├── test_state.py
├── test_step.py
└── fixtures/llm/
    ├── generate__task_positioning.json
    ├── generate__argument_synthesis.json
    ├── generate__storyline_design.json
    ├── generate__page_filling.json
    ├── generate__format.json
    ├── generate__qa_preparation.json
    └── generate__speaker_script.json
```

---

## ❌ 排除（不要打包）

| 排除项 | 原因 |
|---|---|
| `artifacts/` | 你自己跑过的产物，含你公司数据 |
| `data/` | 全局状态与 memory，含你公司数据 |
| `outputs/` | 临时输出 |
| `tmp/` | 临时文件 |
| `.workbuddy/` | WorkBuddy 内部文件 |
| `.git/` | Git 仓库 |
| `node_modules/` | JS 依赖（仅用于 ad-hoc pptx 生成，非 harness 核心） |
| `package.json` / `package-lock.json` | 同上 |
| `generate_ds_report.js` | ad-hoc 脚本 |
| `examples/*.docx` / `examples/*.xlsx` | **你自己的战略分析素材，含你公司数据** |
| `loop_engineering_x.pdf` | 大 PDF，非必要 |
| `20251226_Barbara Prompt & Rubrics.docx` | 内部文件 |
| `*.pptx` | 临时产出物 |
| `.learnings/` | 个人笔记 |

---

## 一行打包命令

```bash
cd /Users/zhangsijing/Desktop/Coding/presentation_agent
tar -czf presentation_agent_dist.tar.gz \
  --exclude='artifacts' \
  --exclude='data' \
  --exclude='outputs' \
  --exclude='tmp' \
  --exclude='.workbuddy' \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='package.json' \
  --exclude='package-lock.json' \
  --exclude='generate_ds_report.js' \
  --exclude='*.pptx' \
  --exclude='*.pdf' \
  --exclude='examples/*.docx' \
  --exclude='examples/*.xlsx' \
  --exclude='.learnings' \
  --exclude='20251226*' \
  presentation_agent/ skills/ configs/ .claude/ .codex/ examples/raw_brief.json \
  tests/ docs/ GUIDEBOOK.md README.md pyproject.toml \
  汇报助手系统设计方案.md
```
