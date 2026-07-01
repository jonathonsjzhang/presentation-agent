---
name: report_builder
description: >-
  互联网战略分析汇报助手【宿主入口 · GitHub 分发 · CLI 调度】。当用户说"安装汇报助手"、
  "更新汇报助手"、"帮我做一份战略汇报 / 复盘 / 高管汇报 / 汇报 PPT / storyline /
  分析报告"，或要求对最终 PPT、DOCX、HTML 材料做 E2E 评测、打分、质量验收时使用。
  宿主 Agent 负责自动 clone/pull 官方仓库、初始化 workspace，并通过 presentation-agent
  report 或 eval 命令推进对应协议。触发词：战略汇报、复盘报告、汇报PPT、高管汇报、
  storyline、分析报告、最终材料评测、E2E评测、材料打分、安装汇报助手、更新汇报助手。
---

# 汇报助手 · Host Adapter Skill

你是宿主 Agent 终端里的调度器。用户不需要懂 git、Python、路径或 CLI；你负责在后台安装、更新、初始化和调用汇报助手。本 skill 自包含——仓库地址已固化，无需用户额外提供。本 skill 适用于 WorkBuddy、Codex、Claude Code 等任意具备终端能力的宿主 Agent。

## 核心原则

- 不写死开发者本机路径。
- 不让用户手动执行 git 或 Python 命令。
- 官方仓库和用户数据分离：repo 可以更新，workspace 不覆盖。
- 只通过高层 CLI 调度：`doctor`、`init-workspace`、`report start/next/submit/approve/status`。
- Manager 定义任务、派发和验收 Worker；宿主不自行决定固定阶段顺序。
- 只在 CLI 返回 `actor=human` 时把 `present_to_user` 展示给用户。
- 用户在 Manager gate 给出反馈时，通过 `report feedback` 送回当前 run；可复用偏好再用 `feedback-text auto` 沉淀。

## 默认安装位置

```text
repo:      ~/PresentationAgent/repo
workspace: ~/PresentationAgent/workspaces/default
```

官方仓库地址固定为 `https://github.com/jonathonsjzhang/presentation-agent`。若设置了环境变量 `PRESENTATION_AGENT_REPO_URL`（企业内部批量部署场景），优先使用该变量。

以下命令示例中使用：

```bash
REPO_URL="${PRESENTATION_AGENT_REPO_URL:-https://github.com/jonathonsjzhang/presentation-agent}"
REPO_DIR="$HOME/PresentationAgent/repo"
WORKSPACE="$HOME/PresentationAgent/workspaces/default"
```

## 安装或检查

当用户第一次使用、说"安装汇报助手"，或当前机器找不到 `~/PresentationAgent/repo` 时：

```bash
mkdir -p "$HOME/PresentationAgent"
git clone "${PRESENTATION_AGENT_REPO_URL:-https://github.com/jonathonsjzhang/presentation-agent}" "$HOME/PresentationAgent/repo"
cd "$HOME/PresentationAgent/repo"
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" init-workspace
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

如果 repo 已存在：

```bash
cd "$HOME/PresentationAgent/repo"
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

`doctor` 输出 JSON，若 `ok=false`，优先执行：

```bash
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" init-workspace
```

然后再次 doctor。

## 最终材料 E2E 自动评测

当用户要求“评测 / 打分 / 验收最终材料是否够格”，且对象是已经生成的 PPT、DOCX 或
HTML 时，路由到仓库内的 `skills/evaluator/SKILL.md`，不要启动新的 `report start`，
也不要把生产流程里的 Worker review 当作 E2E 评分。

执行前先运行：

```bash
cd "$HOME/PresentationAgent/repo"
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  doctor
```

读取 `doctor` 返回的 `evaluation.formats`。目标格式的 `ready=false` 时，向用户报告
`evaluation.dependencies` 中缺失或不可启动的运行时，不得用纯文本评分冒充视觉评测。运行时就绪后，
完整读取并遵循 `skills/evaluator/SKILL.md`，由宿主 Agent 执行其
`eval start → next/submit → result` 协议。

路由边界：

- “帮我生成 / 修改一份材料” → `report` Manager/Worker loop。
- “检查某个生产环节产物” → 当前 Worker 的 `gen → review → revise` 闭环。
- “评价已经生成的最终 PPT / DOCX / HTML 是否够格” → `evaluator` E2E 协议。
- 同一请求既要求生成又要求最终评分时，先完成 `report`，再以最终文件启动独立 eval run；
  Judge 不继承生产 Agent 的自评、review、memory 或返工理由。

## 更新

当用户说"更新汇报助手"：

```bash
cd "$HOME/PresentationAgent/repo"
git pull
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" init-workspace
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

注意：

- 只更新 repo。
- 不删除、不 reset、不覆盖 workspace。
- 不对 `~/PresentationAgent/workspaces/` 做破坏性操作。

## 发起汇报

用户提出汇报需求时，只做忠实的输入归集并形成 `raw_brief.v1`，不要在宿主层替 Manager 完成任务定位。除非连主题都无法判断，否则先启动 Manager，由 Manager 判断阻塞问题。

| 字段 | 必填 | 说明 |
|---|---|---|
| `topic` | 是 | 汇报主题 |
| `audience` | 否 | 汇报对象，缺失时由 Manager 识别或追问 |
| `decision_goal` | 否 | 希望支撑的决策，由 Manager 正式定义 |
| `report_type` | 否 | `deep_dive` / `business_progress` / `quick_sync`，默认 `deep_dive` |
| `output_format` | 否 | `ppt` / `document` / `html`，默认 `ppt` |
| `context` | 否 | 背景 |
| `materials` | 否 | 素材、结论、证据、文件路径 |
| `constraints` | 否 | 页数、保密、口径、格式限制 |
| `user_intent` | 否 | 用户真实意图一句话 |

将 brief 写成 JSON 文件，例如：

```text
~/PresentationAgent/workspaces/default/artifacts/briefs/<slug>.json
```

然后启动：

先按当前宿主终端选择本次 run 的 sub-agent adapter：

| 当前宿主 | `--spawn-adapter` |
|---|---|
| WorkBuddy | `workbuddy` |
| Codex | `codex` |
| Claude Code | `claude` |
| 不支持 sub-agent 的其他终端 | `inline` |

```bash
cd "$HOME/PresentationAgent/repo"
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report start \
  --brief-file "<brief_file>" \
  --spawn-adapter "<workbuddy|codex|claude|inline>"
```

adapter 会写入本次 run 的 `manager_state.json`，后续 `report next/submit/approve` 无需重复传入。也可以通过环境变量 `PRESENTATION_AGENT_SPAWN_ADAPTER` 设置默认值。

若要修复一个已经以 `inline` 启动的旧 run，在下一次命令中显式传入一次即可更新并持久化：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report next --run "<run_id>" --spawn-adapter "workbuddy"
```

如果旧 run 正停在 plan gate，则对 `report approve` 使用同样参数。

CLI 会返回 JSON，记录：

- `run_id`
- `run_dir`
- 当前 `instruction.actor`
- 当前 `instruction.instruction_path`
- 当前 `instruction.output_path`

第一条指令一定属于 Manager planning。Manager 会输出 `report_charter`、`execution_plan` 和首个 `task_packet`。

## Manager / Worker 调度循环

持续执行：

```text
1. report next 返回当前 actor 和 instruction
2. 读取 instruction_path，在独立上下文中执行对应 Manager 或 Worker Skill
3. 把严格 JSON 写入 output_path
4. report submit
5. actor=manager/worker：继续 next/submit，不自行改变调度
6. actor=human：展示 present_to_user，等待用户决策
7. 用户确认：report approve
8. 用户要求调整或回答 Manager 问题：report feedback
```

Worker 指令已经包含 runtime 编译后的 core + audience + report type + format
能力，以及投影后的命名空间化 context。宿主只执行该指令，不自行选择、拼接
或复制 atomic capability 规则，也不要为了“补上下文”把历史 artifact 全量塞回 prompt。

## Sub-agent 派生（隔离上下文执行）

每个 Worker / Reviewer 步骤都必须在与主对话隔离的独立 sub-agent 上下文中执行，避免上下文积累导致的漂移。Manager planning / acceptance 由主对话 Agent 执行，因此 `actor=manager` 时没有 `spawn` 是正常行为；只有 `actor=worker` 才检查并执行 `instruction.spawn`。

### 如何识别"该派 sub-agent"

`report next` 的输出是一个 JSON，其中 `instruction` 即当前指令包。当后端 spawn adapter 非 inline 时，`instruction` 会带一个 `spawn` 注解块：

```json
{
  "instruction": {
    "actor": "worker",
    "step": "gen",
    "instruction_path": "<task_dir>/handoff/instruction_gen.md",
    "output_path": "<task_dir>/handoff/output_gen.json",
    "spawn": {
      "adapter": "workbuddy",
      "role": "worker",
      "status": "dispatched",
      "detail": {
        "spawn_request": "<task_dir>/spawn_request.json",
        "executor": "host_agent_tool",
        "subagent_type": "general-purpose"
      }
    }
  }
}
```

- `actor=worker` 且有 `instruction.spawn`、`status=dispatched` → 按 `spawn.role` 派一个真 sub-agent 去执行本步骤。
- `actor=worker` 且本次 run 的 adapter 为 `inline` → 本对话直接读 `instruction_path`、写 `output_path`。
- `actor=worker`、run adapter 非 `inline`，但 instruction 没有 `spawn` → 这是后端协议错误；先用 `report status` 检查 `manager.state.spawn_adapter`，不得静默降级为 inline。
- `actor=manager` → 由主对话 Manager 执行 planning / acceptance，不派生 sub-agent。

### 角色 → sub-agent 类型映射（终端无关契约）

| `spawn.role` | 能力 | WorkBuddy 类型 | 结果交付 |
|---|---|---|---|
| `worker` | 可写（产内容、写产物） | `general-purpose` | 直接写 `output_gen.json` / `output_revise.json` |
| `reviewer` | 只读（仅出审查结论） | `Explore` | 返回 JSON，由宿主转写 `output_review.json` |

`subagent_type` 和 `result_delivery` 已由后端在 `spawn.detail` 给出，直接采用，不要自己换算。Reviewer 必须用只读类型，从机制上保证 maker-checker 隔离；它不直接写文件，宿主只负责把其返回的 JSON 原样写入 `instruction.output_path`。

> 其他宿主方言：Claude Code adapter 输出 `Task` 工具参数（worker=general-purpose，reviewer=只读 Explore / `disallowedTools` 去写）；Codex adapter 输出 `spawn_agent` + `wait_agent` 参数（worker=worker，reviewer=explorer / `sandbox_mode=read-only`）。宿主直接读取 `spawn.detail`，不要自行猜测映射。

### 派生 sub-agent 的 prompt 必须自包含

被派的 sub-agent 没有主对话历史，其全部依据只有指令包与输入文件。派生时把这三个绝对路径交给它（取自 `instruction` / `spawn.detail`）：

- 指令包：`instruction.instruction_path`（已内嵌完整 SKILL.md、rubrics、上游产物，自包含）
- 任务输入：`<task_dir>/input.json`
- 写回路径：`instruction.output_path`（worker 写 gen/revise，reviewer 写 review）

并向它强调：worker 只写 `output_path` 一个合法 JSON 对象（不裹 markdown）；reviewer 只读不改产物，只返回 `{"objections": [...]}`，无命中则返回 `{"objections": []}`，随后由宿主写入 `output_path`。

### 单环节闭环（实跑验证的状态机推进）

一个 Worker 环节内部由 StepRunner 驱动 `gen → review → revise → done`，**review 是状态机的正式一步，不是可选项**。因此一个环节通常要派 2 次：

```text
1. report next → instruction.spawn.role=worker → 派 worker(general-purpose) 写 output_gen.json
2. report submit → 状态机推进到 review 步骤
3. report next → instruction.spawn.role=reviewer → 派 reviewer(Explore) 返回审查 JSON，宿主写入 output_review.json
4. report submit → 若 review 通过则 finalize artifact、record_worker_completed；
                   若有 P0 objections 则进入 revise，回到步骤 1 的 worker 修订
5. actor 切回 manager → 进入 Manager 验收阶段
```

宿主只需循环 `next → 按 role 派 sub-agent → submit`，状态机推进与产物验收全部由后端完成，宿主不改变调度顺序。

### 框架级不变量（保持跨终端可移植）

- **派生深度 = 1**：被派的 worker/reviewer 内部**不得再下派子 agent**（Codex 限制 sub-agent 深度=1）。L3 reviewer 由 Manager/宿主层派，绝不由 worker 自己派。
- **写作用域限 task_dir**：worker 的写操作只落在 `spawn.detail` 给出的 `invariants.write_scope`（即 task_dir）内。

宿主不支持 sub-agent 时，仍须只把当前 instruction 提供的上下文作为本轮依据，不引入主对话历史。

命令：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report next --run "<run_id>"

python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report submit --run "<run_id>"

python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report approve --run "<run_id>"

python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report feedback --run "<run_id>" --text '<用户原话>'
```

若模型输出先写到了别的文件：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report submit --run "<run_id>" --output-file "<output_json>"
```

## 自动记录可复用反馈

当用户反馈包含可跨项目复用的质量标准或偏好时，不要让用户另填表。使用多目标自动归因：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  feedback-text auto \
  --text '<用户原话>' \
  --scene human_review_chat \
  --run-state '<run_dir>/manager_state.json'
```

同一条反馈可以同时写入 Manager 和专业 Worker memory。一次性项目事实只通过 `report feedback` 进入当前 run，不写长期 memory。

## 成功经验与版本对比

用户明确认可某个产物、结构或表达时，记录 success memory：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  success-memory <agent_id> \
  --dimension '<维度>' \
  --pattern '<值得复用的成功模式>' \
  --why '<为什么有效，可留空>' \
  --scene success_review
```

需要从 v1/final 修改中沉淀经验时：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  compare-reflect <agent_id> \
  --before '<早期版本路径>' \
  --after '<后期或最终版本路径>' \
  --dimension '<维度，可省略>' \
  --lesson '<可复用经验，可省略>'
```

## 状态查询

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report status --run "<run_id>"
```

全部阶段完成后，把状态、关键产物路径和每阶段摘要告诉用户。

## 边界

- 不绕过 harness 自己写最终材料。
- 不在宿主层替 Manager 做任务定位、阶段选择或产物验收。
- 写入 output_path 时只写 JSON 对象，不加 markdown、前言或结语。
- 不在命令里放 token / API key。
- 不执行会覆盖用户 workspace 的命令。
- 不使用开发者本机路径。
