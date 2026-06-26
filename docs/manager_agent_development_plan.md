# Manager Agent 开发方案

## 1. 目标

Manager Agent 不是新的内容生产 Agent，而是嵌入现有汇报助手系统的项目总控层。它负责计划、调度、跨阶段一致性检查、memory 归因和进度可观测；7 个专业 Agent 仍然通过现有 `StepRunner` / `PipelineStepper` 执行。

本轮开发目标是完成最小可行版本：

- 保持现有 `report start / next / submit / approve / status` 外部协议不变。
- 在 report 流程中新增 Manager 状态、计划和决策记录。
- 新增 Manager 专属 memory：`data/agents/manager/`。
- 新增反馈归因路由，支持把自然语言反馈写入 manager 或具体子 Agent memory。
- 新增轻量跨阶段检查，先记录风险，不自动回滚。

暂不实现真并行、复杂 DAG、自动 backtrack、自动改写 skill 或自动跳过 human review。

## 2. 架构定位

现有架构：

```text
Host Agent
  -> report_builder skill
  -> CLI report commands
  -> PipelineStepper / StepRunner
  -> 7 stage agents
```

加入 Manager 后：

```text
Host Agent
  -> report_builder skill
  -> CLI report commands
  -> ManagerController
  -> PipelineStepper / StepRunner
  -> 7 stage agents
```

ManagerController 不绕过 harness：

- 初始化阶段仍使用 `PipelineStepper.init_pipeline()`。
- 推进阶段仍使用 `PipelineStepper.advance_stage()`。
- 单阶段指令与提交仍使用 `StepRunner.prepare()` / `StepRunner.commit()`。
- 子 Agent 专业经验仍使用 `MemoryStore(agent_id)`。
- Manager 调度经验使用 `MemoryStore("manager")`。

## 3. 新增模块

```text
presentation_agent/
├── manager.py          # ManagerController：计划、状态、决策记录
├── memory_router.py    # MemoryRouter：用户反馈归因和 memory 分流
└── cross_review.py     # CrossStageReviewer：跨阶段一致性检查
```

后续可以补充：

```text
skills/manager/
├── SKILL.md
├── rubrics.json
└── schemas/
    ├── manager_plan.v1.json
    ├── task_packet.v1.json
    └── manager_decision.v1.json
```

第一版先不让 Manager 生成内容，所以 Manager skill 包可以作为后续增强项。

## 4. 运行文件

每次 report run 下新增：

```text
run_dir/
├── manager_state.json
├── manager_plan.json
├── manager_decisions.jsonl
├── pipeline_state.json
└── stage_*/
```

`manager_state.json` 记录当前 Manager 视角：

```json
{
  "version": "manager_state.v1",
  "run_id": "report-...",
  "mode": "manager_sequential_v1",
  "status": "running",
  "current_stage": "task_positioning",
  "risk_flags": [],
  "memory_used": [],
  "last_decision": {
    "decision": "start",
    "reason": "report run initialized"
  }
}
```

`manager_plan.json` 记录本次执行计划：

```json
{
  "version": "manager_plan.v1",
  "mode": "sequential_with_manager",
  "stages": ["task_positioning", "..."],
  "human_review_required": true,
  "initial_strategy": {
    "principle": "串行主干，保留后续局部并行扩展点"
  }
}
```

`manager_decisions.jsonl` 追加每次调度、提交、跨阶段检查和推进决策，便于复盘与版本管理。

## 5. Memory 交互规则

Manager 只做 memory 路由和项目级经验沉淀，不接管现有 memory 系统。

四类状态必须分清：

| 层级 | 文件 | 作用 |
|---|---|---|
| run_state | `stage_*/run_state.json` | 单阶段状态机 |
| global state | `run_dir/state.json` | 本次汇报全局约束 |
| agent memory | `data/agents/{agent_id}/memory.json` | 专业 Agent 长期经验 |
| manager memory | `data/agents/manager/memory.json` | 调度、返工、跨阶段和人审偏好经验 |

写入边界：

- 流程、调度、阶段顺序、返工、用户人审偏好 -> `manager`
- 标题、leadline、故事线、结构 -> `storyline_design`
- 论点、结论、action、证据强度 -> `argument_synthesis`
- 页面、图表、信息密度、来源标注 -> `page_filling`
- 版式、可读性、PPT/HTML/DOCX 适配 -> `format`
- 追问、风险、回答策略 -> `qa_preparation`
- 话术、节奏、演讲表达 -> `speaker_script`

一次性项目事实只写入 run/global state，不进入长期 memory。

## 6. CLI 接入

第一版保持现有外部命令不变：

```bash
report start
report next
report submit
report approve
report status
```

内部接入 Manager：

- `report start`：初始化 Manager 状态和计划。
- `report submit`：提交后记录决策；若阶段 done，执行跨阶段检查。
- `report approve`：记录 approve 和 advance 决策。
- `report status`：附带 Manager 状态。

调试命令：

```bash
report manager-status --run <run_id>
report manager-plan --run <run_id>
```

反馈命令增强：

```bash
feedback-text auto --text "..." --run-state "<stage_dir>/run_state.json"
```

`auto` 表示由 `MemoryRouter` 判断写入哪个 Agent 的 memory。

## 7. 分期

### Phase 1: Manager 外壳

- 新增 `ManagerController`。
- 写入 `manager_state.json` / `manager_plan.json` / `manager_decisions.jsonl`。
- `report` 命令内部接入 Manager。

### Phase 2: MemoryRouter

- 新增 `MemoryRouter`。
- `feedback-text auto` 支持自动归因。
- 路由结果写入 learning event。

### Phase 3: CrossStageReviewer

- 新增轻量跨阶段检查。
- 阶段 done 后、human review 前记录 cross-stage result。
- 第一版只 warn/block 记录，不自动回滚。

### Phase 4: 真正多 Agent

- Manager 生成 task packet。
- 每个子 Agent 使用独立上下文执行。
- page filling 支持按页面拆分。
- Q&A 和 speaker script 支持局部并行。

## 8. 版本管理原则

- 所有 Manager 改动在独立分支开发。
- 不覆盖用户 workspace 和已有 memory。
- 不改动现有 report 外部协议，降低宿主 skill 迁移成本。
- README 中已有 TODO 不作为实现代码的唯一来源；实现以本开发文档为准。
- 每个阶段改动配套单元测试，确保现有 step/pipeline 行为不回退。
