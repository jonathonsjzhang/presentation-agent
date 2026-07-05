# Schema 快速参考卡片

> 聚焦"最常踩坑"的字段和枚举值。完整定义见 `skills/*/schemas/*.json`。

---

## report_charter.v2（planning 阶段）

**22 个 required 字段**，缺一不可：

| 字段 | 类型要求 | 说明 |
|---|---|---|
| `schema` | `"report_charter.v2"` | 固定值 |
| `topic` | string | 汇报主题 |
| `audience` | enum | 见下方 |
| `report_type` | enum | 见下方 |
| `delivery_targets` | `["document"]` | 固定值 |
| `decision_goal` | string | 决策目标 |
| `expected_action` | string | 期望行动 |
| `analysis_objective` | string | 分析目标 |
| `scope` | array of string | **是数组不是object** |
| `out_of_scope` | array of string | 可空数组 `[]` |
| `constraints` | array of string | 可空数组 `[]` |
| `success_criteria` | array of string | 至少1项 |
| `recommendation_granularity` | enum | 见下方 |
| `unsupported_specificity_policy` | enum | 见下方 |
| `material_inventory` | array of object | 每个 item 需 material_id/name/media_type/locator/availability |
| `existing_artifacts` | array of object | 可空数组 `[]` |
| `analysis_acceptance_criteria` | array of string | 至少1项 |
| `extension_policy` | object | 固定结构，见下方 |
| `global_state_seed` | object | 可空对象 `{}` |
| `blocking_questions` | array of string | 可空数组 `[]` |
| `assumptions` | array of string | 可空数组 `[]` |

### 关键 enum 值

```json
// audience: 必须用英文，不能写中文
"board" | "exec_office" | "strategy_lead" | "business_team" | "external"

// report_type
"deep_dive" | "business_progress" | "quick_sync"

// recommendation_granularity: 注意是 strategic_direction 不是 strategic_direction_only
"strategic_direction" | "strategic_choice" | "execution_plan"

// unsupported_specificity_policy: 注意是 forbid 不是 strict
"forbid" | "source_backed_only" | "allow"
```

### extension_policy 固定结构

```json
{
  "format_expansion": "offer_ppt_html_after_document",
  "qa_preparation": "optional_after_format",
  "speaker_script": "optional_after_format",
  "gate": "after_document_delivery"
}
```

---

## task_packet.v2（dispatch Worker 时）

### 常见约束

| 约束 | 说明 |
|---|---|
| `agent_id` | 仅限 `analysis`/`storyline`/`report`/`format`/`qa_preparation`/`speaker_script` |
| `input_artifacts` | **只能放 artifact_catalog 中的路径**（如 `raw_brief.json`），**不能放原始素材路径** |
| 原始素材 | 放 `context.raw_materials` 中 |

### agent_id 枚举

```
"analysis" | "storyline" | "report" | "format" | "qa_preparation" | "speaker_script"
```

---

## execution_plan.v1

**核心约束：tasks 必须恰好为 4 个**，按固定顺序：

| # | agent_id | 说明 |
|---|---|---|
| 1 | `analysis` | |
| 2 | `storyline` | |
| 3 | `report` | |
| 4 | `format` | |

- 不允许加 `evidence_harvester`（它是 analysis 的内部子任务）
- 每个 task 的 `status` 初始值：第一个 `"planned"`，其余 `"pending"`

---

## manager_decision.v1（planning + acceptance）

### phase 与 action 组合

| phase | 允许的 action |
|---|---|
| `planning` | 只能是 `"dispatch"` |
| `acceptance` | `"dispatch"` / `"revise"` / `"ask_human"` / `"complete"` |

### acceptance_report 约束

| 字段 | 约束 |
|---|---|
| `task_id` | **必须填当前被验收的 Worker 的 task_id**，不能填上一环节的 |
| `verdict` | `action=dispatch` 时必须是 `"accept"`；`action=revise` 时必须是 `"revise"` |

---

## 常见错误对照表

| 错误写法 | 正确写法 | 所在 schema |
|---|---|---|
| `"audience": "腾讯总办（exec_office）"` | `"audience": "exec_office"` | report_charter.v2 |
| `"scope": {"product": "..."}` | `"scope": ["..."]` | report_charter.v2 |
| `"recommendation_granularity": "strategic_direction_only"` | `"recommendation_granularity": "strategic_direction"` | report_charter.v2 |
| `"unsupported_specificity_policy": "strict"` | `"unsupported_specificity_policy": "forbid"` | report_charter.v2 |
| `task_packet.input_artifacts` 放了原始素材路径 | 原始素材放 `task_packet.context.raw_materials` | task_packet.v2 |
| `execution_plan.tasks` 有 5 个（加了 evidence_harvester） | 恰好 4 个：analysis/storyline/report/format | execution_plan.v1 |
| `acceptance_report.task_id` = 上一环节 | = 当前被验收的 Worker 的 task_id | manager_decision.v1 |
| `ask_human` 后调 `report approve` | `ask_human` 后应调 `report feedback` | harness |

---

## 状态机常见误区

| 场景 | 误区 | 正确操作 |
|---|---|---|
| `report submit` 后想改 decision | 直接编辑文件 → `report submit` | 先 `report feedback` 重置 → 编辑 → `report submit` |
| schema_only 模式 revise | 提交 `{"objections": []}` | 需要完整 Worker 产出 JSON（与 gen 步骤同格式） |
