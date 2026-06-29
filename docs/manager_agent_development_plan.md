# Manager Agent 架构与实现

## 1. 定位

Manager 是汇报项目的控制面 Agent，不是固定流水线外的一层日志包装。

它直接面向用户并对最终结果负责：

- 定义汇报任务；
- 制定执行计划；
- 选择和派发专业 Worker；
- 验收 Worker 产物；
- 决定通过、返工、重新规划或向用户升级；
- 汇总最终交付物。

责任关系：

```text
用户验收 Manager
Manager 验收 Worker
Worker checker 验收专业 schema / rubrics
```

原 `task_positioning` 能力已并入 Manager planning。旧 Agent 定义仅用于兼容历史 run 和低层调试，不属于新的高层 report 流程。

## 2. 双层 Loop

Manager 外层 loop：

```text
planning
  -> plan human gate
  -> dispatch Worker
  -> Worker completed
  -> acceptance
      -> dispatch
      -> revise
      -> ask_human
      -> complete
  -> final human gate
```

Worker 内层 loop：

```text
gen -> review -> stop_check
  -> revise
  -> return to Manager acceptance
```

Manager 不替 Worker 生产专业内容；Worker 完成后也不直接进入用户审批。

## 3. 运行模块

实现位于 `presentation_agent/manager.py`：

| 模块 | 职责 |
|---|---|
| `ManagerAgentRuntime` | 读取 Manager Skill 和 memory，生成 planning/acceptance 指令，校验 `manager_decision.v1` |
| `ManagerOrchestrator` | 维护控制面状态，执行 dispatch/revise/ask_human/complete |
| `WorkerExecutor` | 根据 task packet 创建隔离任务目录，并使用现有 `StepRunner` 驱动 Worker |

`PipelineStepper` 不再控制高层 `report` 流程，仍保留为六 Worker 固定顺序的兼容/调试入口。

## 4. Manager Skill

```text
skills/manager/
├── SKILL.md
├── rubrics.json
└── schemas/
    ├── manager_context.v1.json
    ├── report_charter.v1.json
    ├── execution_plan.v1.json
    ├── task_packet.v1.json
    ├── acceptance_report.v1.json
    └── manager_decision.v1.json
```

Manager 的模型决策由 Skill 定义，Python 只校验和执行结构化 action。

## 5. 输入输出

Manager 输入 `manager_context.v1`：

- `phase`: `planning` 或 `acceptance`；
- 原始 brief、report charter 和 execution plan；
- 可用 Worker 能力；
- 当前 task 和 Worker artifact/review；
- 已接受 artifact 目录；
- 用户反馈；
- Manager memory。

Planning 输出：

- `report_charter`：受众、决策目标、目标 action、范围、约束、成功标准和全局 state；
- `execution_plan`：任务、依赖、人工 gate 和完成标准；
- 首个 `task_packet`。

Acceptance 输出：

- `acceptance_report`；
- `action`: `dispatch | revise | ask_human | complete`；
- 需要继续执行时的 `task_packet`。

## 6. Task Packet

每个 Worker 只接收本任务需要的上下文：

```json
{
  "task_id": "argument-001",
  "agent_id": "argument_synthesis",
  "objective": "形成可决策的核心论点和证据链",
  "input_artifacts": ["raw_brief.json"],
  "context": {},
  "constraints": [],
  "deliverables": {},
  "acceptance_criteria": [],
  "dependencies": [],
  "memory_dimensions": [],
  "revision_of": null,
  "revision_feedback": []
}
```

runtime 将 `report_charter`、`manager_task`、raw brief 和引用 artifact 组装成 Worker `input.json`。每次任务使用独立目录：

```text
run_dir/tasks/<task_id>_<agent_id>/
```

## 7. 状态与文件

```text
run_dir/
├── raw_brief.json
├── report_charter.json
├── manager_plan.json
├── manager_state.json
├── manager_decisions.jsonl
├── state.json
├── manager/
│   ├── handoff/
│   └── decisions/
└── tasks/
    └── <task_id>_<agent_id>/
```

`manager_state.json` 是控制面真相源，记录：

- `current_actor`: `manager | worker | human`；
- `manager_phase`;
- 当前任务和全部任务状态；
- pending human gate；
- accepted artifacts；
- run 内用户反馈。

## 8. Memory

Manager memory 只保存任务定义、拆解、调度、验收、返工、人审偏好和跨阶段一致性经验。

专业经验仍属于对应 Worker。`MemoryRouter` 支持多目标归因，例如“结论太软，Manager 不该放过”同时写入：

- `argument_synthesis`：结论质量经验；
- `manager`：验收标准经验。

一次性项目事实只通过 `report feedback` 写入当前 run，不进入长期 memory。

## 9. CLI

```bash
report start
report next
report submit
report approve
report feedback
report status
```

调用方始终执行当前 CLI 返回的 `actor + instruction`：

```text
next -> execute instruction -> submit
```

只有 `actor=human` 时需要用户参与。计划和最终交付调用 `approve`；修改意见或问题回答调用 `feedback`。

## 10. 当前边界

当前版本已完成：

- Manager Skill 和结构化决策；
- task positioning 吸收；
- Manager planning/acceptance loop；
- Worker 动态派发和任务目录隔离；
- Manager plan/final human gate；
- run 内反馈回流；
- 多目标 memory 路由。

后续增强项：

- 宿主原生 sub-agent adapter，实现模型会话级物理隔离；
- 多 task 并行派发与汇合；
- 更强的跨 artifact 确定性验收工具；
- Manager 决策评测集与回放。
