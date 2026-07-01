# 三层 Agent 架构设计补充（Manager / 环节 Sub-Agent / Review Sub-Agent）

> 状态：设计补充文档 + **实现回填（§9 为已实现状态）**。针对 README 第八章 TODO #1「增加 Manager agent」与 TODO #2「多 Agent 和 Sub-agent 机制」。
> 关联文档：`docs/manager_agent_development_plan.md`（本地 harness 实现方案）、`README.md`、`configs/agents.json`
> 关联代码：`presentation_agent/spawn.py`（SpawnAdapter）、`presentation_agent/derive_agents.py`（单一事实源派生）、`presentation_agent/manager.py`（`_annotate_spawn`）。
> 定位：本文定义**架构与 Agent 边界**；`manager_agent_development_plan.md` 定义**代码落地**。两者互补，本文为上游规范。§1–§8 为设计，§9 为实现落地。
>
> **两条硬性设计目标（本次确认）：**
> 1. **主对话 Agent 本身即 Manager（L1）**——不引入独立进程的 Manager，对话窗口里的那个 Agent 就是总控，逐环节派生 sub-agent。对应 §5 的「形态 A」，定为默认且唯一起步形态。
> 2. **同一套框架跨终端适配 WorkBuddy / Claude Code / Codex**——三个 agent 终端任选其一作为宿主，都能用各自的原生机制调起 L2/L3 sub-agent。框架不绑定任何单一终端，详见 §8。

---

## 0. 一句话定义

汇报助手从「7 个环节在同一上下文里串行换 skill」升级为**三层 Agent 架构**：

- **L1 — Manager Agent**：唯一与人对话、掌控全局状态、逐环节调度、汇总转述的总控层。
- **L2 — 7 个环节 Sub-Agent（worker）**：每个环节是一个**独立上下文**的 sub-agent，由 Manager 派生，负责该环节的内容生产。
- **L3 — 每个环节配套的 Review Sub-Agent**：在对应 worker 产出后，以**干净只读上下文**审查产物，输出 P0/P1 异议。

层级关系：`L1 → 7×L2 → 每个 L2 各挂 1×L3`。这正是当前 `configs/agents.json` 里 `loop.reviewer = clean_context_review_sub_agent`、`loop_steps[].owner = review_sub_agent` 想表达、但此前由同一 Agent 模拟实现的结构——本次将其落为**真正独立上下文的 sub-agent**。

---

## 1. 为什么是三层（动机）

README TODO #2 指出当前痛点：

> 当前的多阶段生成和 review 实际由同一个 agent 进行，在不同阶段使用不同 skill，存在上下文积累，导致上下文漂移和执行效率、效果较差。

根因：7 个环节 + 每个环节的 review 全部跑在**同一条对话上下文**里。随着流程推进，上下文不断膨胀，导致：

1. **上下文漂移**——后段环节被前段无关细节干扰，偏离本环节职责。
2. **maker-checker 失效**——生产者和审查者是同一上下文，review 无法真正"换个脑子"独立审查。
3. **效率下降**——每一步都背着越来越长的历史，token 成本与延迟线性上升。

三层架构用「独立上下文的 sub-agent」根治这三点：每个 worker 和每个 reviewer 都是**干净起点**，prompt 自包含，互不污染。

---

## 2. 三层职责定义

### L1 — Manager Agent（编排层，唯一常驻）

| 维度 | 定义 |
|---|---|
| 数量 | 1，常驻整个汇报任务 |
| 上下文 | 长期持有：全局状态、各环节摘要、人审记录、调度决策 |
| 是否与人对话 | **是，且唯一**。所有 present、所有人审、所有反馈都经 Manager |
| 是否生产内容 | **否**。不写环节产物 JSON，只编排、汇总、转述 |
| 核心职责 | ① 维护全局状态黑板（`data/global/state.json`）<br>② 决定当前推进到哪个环节、是否满足前置依赖<br>③ 为每个环节 worker 装配自包含 instruction 包（prepare）<br>④ 派生 worker、派生 reviewer、驱动 P0 修订回环<br>⑤ 把「worker 产物 + reviewer 异议」摘要 present 给人，承接 approve/revise/stop/回上游<br>⑥ 反馈归因：把人的自然语言反馈分流写入 manager 或具体子 Agent memory |
| 落地形态 | 见 §5。起步形态 = 主对话 Agent 即 Manager |

**关键约束**：L2/L3 sub-agent 的执行结果对用户不可见。Manager 必须把每环节结果**主动转述**给人，这与现有「每环节 human review」节奏一致。

### L2 — 环节 Sub-Agent（生产层，7 个）

每个环节对应 `configs/agents.json` 里的一个 agent，按 `pipeline.stages` 顺序：

| # | id | name | 输入 schema | 输出 schema | skill 包 |
|---|---|---|---|---|---|
| 1 | `task_positioning` | 任务定位 | `raw_brief.v1` | `task_positioning.v1` | `skills/task_positioning` |
| 2 | `argument_synthesis` | 核心论点提炼 | `task_positioning.v1` | `argument_synthesis.v1` | `skills/argument_synthesis` |
| 3 | `storyline_design` | storyline 设计 | `argument_synthesis.v1` | `storyline.v1` | `skills/storyline_design` |
| 4 | `page_filling` | 单页内容填充 | `storyline.v1` | `page_content.v2` | `skills/page_filling` |
| 5 | `format` | format | `page_content.v2` | `formatted_material.v1` | `skills/format` |
| 6 | `qa_preparation` | Q&A 梳理 | `formatted_material.v1` | `qa_pack.v1` | `skills/qa_preparation` |
| 7 | `speaker_script` | 逐字稿 | `qa_pack.v1` | `speaker_script.v1` | `skills/speaker_script` |

| 维度 | 定义 |
|---|---|
| 数量 | 7，按需逐个派生（默认不常驻） |
| 上下文 | **独立、干净**。不继承主对话历史，只看 Manager 给的自包含包 |
| 输入 | Manager 装配的 instruction 包：角色 + 输入契约 + 上游 artifact + 输出 schema + rubrics + 注入的相关 memory |
| 产出 | 该环节 `output_schema` 规定的 artifact JSON（+ 必要的渲染产物，如 format 的 pptx/html） |
| 能力边界 | **可写文件、可调 connector/renderer**（写 output JSON、调 pptx_writer 等）。对应 sub-agent 类型 = `general-purpose` |
| 不该做 | 不与人直接对话、不跨环节越权读写、不自行审查自己（审查是 L3 的事） |

### L3 — Review Sub-Agent（审查层，每个环节 1 个）

对应 `agents.json` 里每个 agent 的 `loop.reviewer = clean_context_review_sub_agent`。

| 维度 | 定义 |
|---|---|
| 数量 | 7（与环节一一配对），每次审查时派生 |
| 上下文 | **干净、只读**。只看「本环节输入契约 + 本环节 worker 产物 + 本环节 rubrics」 |
| 产出 | P0（阻断性，必须修）/ P1（建议性）异议清单，结构化输出 |
| 能力边界 | **只读，物理上不能改产物**。对应 sub-agent 类型 = `Explore` 或 `Plan`（只读工具集） |
| 价值 | 用机制保证 maker-checker 隔离——reviewer 不可能"顺手改"，只能提异议，比"约定它别改"可靠 |

**为什么用只读 agent 类型**：这是三层架构的一个关键设计点。L3 选择 `Explore`/`Plan` 这类只读子 agent，从运行时层面杜绝了"审查者修改被审查对象"的污染，让 review 真正独立。

---

## 3. 单环节闭环（每个 L2 内部都跑这一圈）

这一圈复用现有 `loop_steps` 五步（`start / workflow / review / stop_check / human_review`），只是把 `workflow` 和 `review` 的 owner 从「同一 Agent 换 skill」替换为「派生独立 sub-agent」：

```text
Manager(prepare 自包含包)
   │
   ▼
L2 worker (general-purpose, 写 output JSON)        ← loop_steps.workflow
   │
   ▼
L3 review (Explore 只读, 出 P0/P1)                  ← loop_steps.review (clean_context_review_sub_agent)
   │
   ▼
stop_check (L1 schema/P0 硬门 + L2 LLM sanity)     ← loop_steps.stop_check
   │
   ├─ 命中 P0 ──► 回 L2 worker 修订（≤ max_revision_rounds，默认 2）
   │
   ▼
human_review (Manager 转述 → 人 approve/revise/stop/回上游)  ← loop_steps.human_review
```

与 `agents.json` 字段的精确对应：

- `loop.workflow_owner = skill` → L2 worker 加载的 skill 包
- `loop.reviewer = clean_context_review_sub_agent` → L3 review sub-agent（只读）
- `loop.stop_checker = schema_and_p0_gate` → stop_check 的 L1 确定性硬门
- `loop.p0_revision_policy = auto_revise_until_clear_or_max_rounds` → P0 修订回环
- `loop.human_review_required = true` → 每环节出口的人审节点
- `max_revision_rounds`（默认 `pipeline.default_max_revision_rounds = 2`）→ 修订上限

---

## 4. 三层与 WorkBuddy Sub-Agent 协议的映射

WorkBuddy 宿主侧通过 **`Agent` 工具 + 共享任务列表 + SendMessage** 提供真正独立上下文的 sub-agent。三层架构与该协议的对应关系：

| 架构层 | WorkBuddy 机制 | sub-agent 类型 | 调度方式 |
|---|---|---|---|
| L1 Manager | 主对话 Agent（形态 A）/ `TeamCreate` 常驻 teammate（形态 B） | — | 常驻 |
| L2 worker | `Agent` 工具派生子进程 | `general-purpose`（可写） | 前台阻塞串行（环节有序依赖） |
| L3 review | `Agent` 工具派生子进程 | `Explore` / `Plan`（只读） | 前台阻塞（紧跟 worker 之后） |
| 跨层协调 | 共享任务列表（`TaskCreate/Update/List`，`owner` 认领、`blockedBy` 依赖）+ `SendMessage`（点对点 / resume 续跑） | — | 黑板 + 点对点 |

**两个天然咬合点（非巧合，是设计契合）**：

1. **自包含 prompt**：WorkBuddy sub-agent 不继承主对话历史，要求 prompt 必须自包含；而 harness 的 `step prepare` 本就把「角色 + 输入 + 输出规范 + rubrics + memory」装配成自包含 instruction 包。两者无缝对接。
2. **harness 不改一行**：三步协议 `prepare → commit → advance` 保持不变，变的只是「谁执行 commit 那一步的产物生成」——从「主 Agent 自己在同一上下文写」变成「Manager 用 `Agent` 工具派生干净 worker 去写」。改动只在宿主侧调度逻辑（`skills/report_builder/SKILL.md`）。

---

## 5. Manager 的两种落地形态

### 形态 A（推荐起步，轻量）

- 主对话 Agent 本身即 Manager。
- 逐环节**前台串行**派生 worker（general-purpose）和 reviewer（Explore 只读）。
- 改动仅在 `skills/report_builder/SKILL.md` 增加一段「派生 sub-agent 执行环节」的调度规则。
- 优点：实现成本最低、串行依赖天然满足、无需团队机制。

### 形态 B（后续升级，团队）

- `TeamCreate` 建常驻 Manager，worker 用 `name` 寻址。
- 靠共享任务列表的 `blockedBy` 编排环节依赖。
- 适用场景：需要并行时（如 `multi_candidate` 同环节跑 3 个候选、`page_filling` 多页并行填充）。
- `agents.json` 里多个环节的 `optional_features.multi_candidate.enabled_by_default = true`，正是形态 B 的并行触发点。

> 建议演进路径：**先形态 A 验证机制 → 有并行需求时局部升级到形态 B**。

---

## 6. 与现有配置/实现的对齐清单

落地本架构时需要对齐的点（实现细节见 `manager_agent_development_plan.md`）：

- [ ] `configs/agents.json`：补 Manager agent 定义（读哪些 state、怎么决策派谁、反馈归因路由）。
- [ ] `skills/report_builder/SKILL.md`：增加「Manager 派生 L2 worker / L3 review sub-agent」的调度协议段落。
- [ ] L2 worker 派生时固定使用可写 sub-agent 类型（general-purpose）。
- [ ] L3 review 派生时固定使用只读 sub-agent 类型（Explore/Plan），从机制保证 maker-checker 隔离。
- [ ] Manager 负责把不可见的 sub-agent 结果转述给人（present + 人审）。
- [ ] Manager memory 与 7 个环节 memory 分流：`data/agents/manager/` vs `data/agents/{agent_id}/`。

---

## 7. 名词对照（避免歧义）

| 本文用语 | agents.json 字段 | README 用语 |
|---|---|---|
| L2 环节 Sub-Agent / worker | `agents[].id` + `loop.workflow_owner=skill` | 7 个环节 Agent |
| L3 Review Sub-Agent | `loop.reviewer=clean_context_review_sub_agent` / `loop_steps[review].owner=review_sub_agent` | review sub-agent |
| L1 Manager | （待补，本次新增） | Manager agent |
| 自包含 instruction 包 | `step prepare` 产物 | prepare 指令包 |
| P0 修订回环 | `loop.p0_revision_policy` | 自动修订 |

---

## 8. 跨终端适配（WorkBuddy / Claude Code / Codex 通用）

### 8.1 设计目标

同一套三层框架，必须在三个 agent 终端上都能跑通——任选其一作为宿主，主对话 Agent 都能作为 Manager 调起 L2 worker 和 L3 review sub-agent。框架不绑定任何单一终端。

这件事的地基**已经存在**：README §5 已确立「harness 不调模型，宿主调 harness」，且 `skills/report_builder/SKILL.md` 已定位为对三家通用的自包含 skill。本次只需把「宿主侧怎么派 sub-agent」也抽象成跨终端通用的一层。

### 8.2 核心判断：三者是「同一抽象的三种方言」

调研三家 sub-agent 协议后的结论——四件关键能力三家全部具备，差别只在**配置格式 + 调用动词**：

| 能力维度 | WorkBuddy | Claude Code | Codex CLI |
|---|---|---|---|
| 派生 sub-agent | `Agent` 工具（`subagent_type`） | `Task` 工具（`subagent_type`） | `spawn_agent` / `wait_agent` / `close_agent` |
| 自定义 agent 放哪 | `.workbuddy/agents/` | `.claude/agents/*.md`（YAML frontmatter） | `.codex/agents/*.toml` + `[agents]` config |
| 内置可写角色 | `general-purpose` | `general-purpose` | `worker` / `default` |
| 内置只读角色 | `Explore` / `Plan` | `Explore` / `Plan`（或 `disallowedTools`） | `explorer` / `sandbox_mode=read-only` |
| reviewer 只读怎么锁 | 选只读类型 | `tools` 白名单 / `disallowedTools` | `sandbox_mode = "read-only"` |
| 前台串行 / 后台并行 | 默认前台 / `run_in_background` | 默认前台 / 后台 | `wait_agent` 阻塞 / 并行≤6、深度≤1 |
| 项目级指令文件 | `SKILL.md`（已通用） | `CLAUDE.md` + `SKILL.md` | `AGENTS.md` + `SKILL.md` |

> 结论：**不必为每家写一套框架**。只需在 `SKILL.md` 里定义一个与终端无关的「sub-agent 能力契约」，让每个宿主用自己的方言去满足它。

一个重要约束差异（落地时必须注意）：

- **Codex 深度限制为 1**（一层 sub-agent），并行上限 6。本架构是「主对话 Agent(Manager) → L2/L3」**正好一层**派生，落在限制之内；但意味着 **L2 worker 内部不能再派生子 sub-agent**——这对三家都应作为统一约束，保持框架可移植。
- **Codex 子 agent 非交互审批**：需要新审批的写操作会失败并回传父流程。因此 worker 的写操作应限定在工作区内（写 output JSON / 渲染产物），避免触发交互审批。

### 8.3 抽象层：SKILL.md 里的「能力契约」

在 `skills/report_builder/SKILL.md` 中定义两个**终端无关的原语**（伪指令，由宿主用自己的机制实现）：

```text
SPAWN_WORKER(stage_id, instruction_pack):
    语义：派生一个【可写】的干净上下文 sub-agent，
         喂入 instruction_pack（= step prepare 的产物），
         令其产出该 stage 的 output JSON，前台等待返回。
    约束：可写工作区；不得再向下派生；prompt 必须自包含。

SPAWN_REVIEWER(stage_id, worker_output, rubrics):
    语义：派生一个【只读】的干净上下文 sub-agent，
         仅喂入 输入契约 + worker_output + rubrics，
         令其产出 P0/P1 异议清单，前台等待返回。
    约束：只读，物理上不能改产物（机制级 maker-checker 隔离）。
```

SKILL.md 同时给出三家的**映射速查表**，宿主读到契约后按自己所在终端执行：

| 契约原语 | WorkBuddy | Claude Code | Codex |
|---|---|---|---|
| `SPAWN_WORKER` | `Agent(subagent_type="general-purpose", prompt=pack)` 前台 | `Task(subagent_type="general-purpose", prompt=pack)` 前台 | `spawn_agent(role="worker", instructions=pack)` → `wait_agent` |
| `SPAWN_REVIEWER` | `Agent(subagent_type="Explore", prompt=...)` 前台 | `Task(subagent_type="Explore"/只读 agent, ...)` | `spawn_agent(role="explorer"/`sandbox_mode=read-only`)` → `wait_agent` |
| 结果转述 | Manager `present_files` / 文本摘要 | 主线程汇总摘要 | 父流程 consolidated response |

> 关键：契约只描述「要一个可写worker / 要一个只读reviewer，前台等结果」这一**语义**，不写死任何终端的工具名。终端差异收敛在这张速查表里，新增终端只需加一行。

### 8.4 角色定义的三套等价文件

7 个环节 worker + 7 个 review reviewer 的角色定义，在三个终端各有等价载体。**单一事实源仍是 `configs/agents.json`**（schema、rubrics、工具边界），三套终端文件由它派生（可脚本生成）：

```text
configs/agents.json   ← 单一事实源（schema / rubrics / 可写或只读）
      │  派生
      ├── .workbuddy/agents/<stage>.md        + <stage>_review.md
      ├── .claude/agents/<stage>.md           + <stage>_review.md   (YAML frontmatter, tools/disallowedTools)
      └── .codex/agents/<stage>.toml          + <stage>_review.toml (sandbox_mode=read-only for reviewer)
```

要点：
- **可写 worker**：三家都给可写工具集 / `workspace-write`。
- **只读 reviewer**：WB/CC 用只读 agent 类型或 `disallowedTools=[Edit,Write]`；Codex 用 `sandbox_mode="read-only"`。三种写法语义等价。
- 文件可由 `agents.json` 自动生成，避免三套手工维护漂移（列入后续实现项）。

### 8.5 不变量（三终端都必须满足）

无论宿主是谁，以下不变量恒成立，保证框架可移植：

1. **harness 三步协议不变**：`prepare → commit → advance`，纯 Python、零模型依赖。
2. **派生只有一层**：Manager → L2/L3，worker/reviewer 不再下派（迁就 Codex 深度=1）。
3. **worker 可写、reviewer 只读**：reviewer 的只读由终端机制强制，而非约定。
4. **自包含 instruction 包**：每个 sub-agent 只看 `step prepare` 的产物，不依赖主对话历史。
5. **结果由 Manager 转述**：sub-agent 结果对用户不可见，统一经 Manager present + 人审。
6. **worker 写操作限定工作区内**：避免触发 Codex 非交互审批失败。

### 8.6 跨终端落地清单（补充 §6）

- [x] `skills/report_builder/SKILL.md`：写入 §8.3 的 `SPAWN_WORKER`/`SPAWN_REVIEWER` 能力契约 + 三家映射速查表。（已固化）
- [x] 编写 `agents.json → 三套终端 agent 文件` 的生成脚本（`agents.workbuddy/` / `.claude/agents/pipeline/` / `.codex/agents/`）。（见 §8.7，`presentation_agent/derive_agents.py` + CLI `derive-agents`）
- [x] 在 SKILL.md 写明「派生只有一层、worker 写操作限工作区」两条迁就 Codex 的统一约束。（已固化）
- [x] 各终端各跑一次单环节 worker→review→P0 闭环（§3）做可移植性验证。（WorkBuddy adapter 下已端到端跑通 t1→t2 含 P0 返工，见 §8.8）

---

## 9. 实现落地（从设计到代码，本节为已实现状态）

> 状态：**已实现**。§8 的能力契约、派生脚本、跨终端方言均已落为代码并有测试与端到端验证覆盖。本节是 §8 的「实现回填」，描述真实代码而非设计意图。

### 9.1 SpawnAdapter：能力契约的代码化（`presentation_agent/spawn.py`）

§8.3 的 `SPAWN_WORKER`/`SPAWN_REVIEWER` 两个终端无关原语，落为一个 **SpawnAdapter 抽象层**，在 `WorkerExecutor.prepare()` 的唯一插入点按 adapter 分流：

| adapter | 行为 | 用途 |
|---|---|---|
| `inline`（默认） | no-op，宿主主对话 Agent 在当前上下文按 instruction 自己写产物 | 零回退，保持现有行为 |
| `workbuddy` | 物理写出 `spawn_request.json`（`role` + `subagent_type`），宿主据此用 `Agent` 工具派生 | WorkBuddy 宿主 |
| `cli` | 按方言生成 `claude -p` / `codex exec` 命令；`execute=False` 仅 emit spawn_request，`execute=True` 真 `subprocess.run`（带 `shutil.which` 守护） | Claude Code / Codex 宿主 |

`CLISpawnAdapter` 内含 `CLI_DIALECTS` 命令模板（claude / codex 各自的 worker / reviewer 命令），`_detect_dialect()` 方言推断，以及 worker/reviewer 的只读区分：

- **worker**：`claude -p "{prompt}"` / `codex exec "{prompt}"`（可写）。
- **reviewer**：`claude -p "{prompt}" --disallowedTools Write,Edit,Bash,NotebookEdit` / `codex exec --sandbox read-only "{prompt}"`（只读，机制级 maker-checker）。

WorkBuddy adapter 的角色映射：worker → `subagent_type=general-purpose`（可写）；reviewer → `subagent_type=Explore`（只读）。

### 9.2 单一事实源派生（`presentation_agent/derive_agents.py` + CLI `derive-agents`）

§8.4 的「三套等价文件由 `agents.json` 派生」落为 `derive_agents.py`。`configs/agents.json` 是唯一事实源，派生出三套终端文件：

```text
configs/agents.json   ← 单一事实源（schema / rubrics / 可写或只读）
      │  derive-agents
      ├── agents.workbuddy/          (subagent_type: general-purpose / Explore)
      ├── .claude/agents/pipeline/   (YAML frontmatter, tools allow-list / reviewer 只读)
      └── .codex/agents/             (sandbox_mode = read-only for reviewer)
```

要点（与设计一致并已被测试守护）：

- **只派生 6 个 stage 级 sub-agent**（argument_synthesis / storyline_design / page_filling / format / qa_preparation / speaker_script），每个含 worker + reviewer 两个角色 → 6×2×3 = **36 个文件**。
- **不碰手写的 orchestrator**（`.claude/agents/report-builder.md` / `.codex/prompts/report-builder.md`）——派生集里不应出现 `report-builder`。
- `task_positioning` 是 legacy，不在 `pipeline.stages` 里，**不参与派生**。
- 每个派生文件带 `AUTOGEN_BANNER`，提示勿手改。
- 提供 `--dry-run` 先看派生计划（不写盘）。
- `.claude/` 与 `.codex/` 在本仓被 gitignore，派生产物为生成物不入库；`agents.workbuddy/` 未跟踪。

### 9.3 review-step 的物理只读 spawn 修复（`manager.py:_annotate_spawn`）

端到端验证（§8.8）暴露过一个架构缺口并已修复：`ManagerOrchestrator.prepare()` 在 StepRunner 处于 `awaiting_*` 子步（review / revise）时**短路返回裸 instruction，不经 `WorkerExecutor.prepare()`**，导致非 inline adapter 下 **review 步骤不刷新 reviewer 的 `spawn_request.json`**，只读 maker-checker 在 CLI 路径上没有物理生效（停留在上一个 worker 请求）。

修复：在短路分支新增 `self._annotate_spawn(task_dir, instruction)`：

- adapter 为 `inline` 时 **no-op**（零回退）。
- 非 inline 时，去掉 `awaiting_` 前缀得到子步名，复用 `WorkerExecutor._build_spawn_request` + `adapter.spawn()`，对 instruction 注解 spawn 并**物理刷新磁盘 `spawn_request.json`**。
- role 判定沿用 WorkerExecutor 规则：`review_output` → reviewer **只读 Explore**；`revise_output` 不以 `review` 开头 → worker **可写 general-purpose**（返工本就是写作，正确）。

真实状态机路径验证（workbuddy adapter）：dispatch 后 `spawn_request` = worker/general-purpose → commit_gen 后 StepRunner 进入 `awaiting_review_output` → `prepare()` 把 `spawn_request.json` 刷新为 **role=reviewer / subagent_type=Explore / instruction_review.md**。修复后只读隔离在 CLI 路径也物理成立。

### 9.4 测试与验证状态

| 范围 | 结果 |
|---|---|
| `test_spawn_adapter`（CLISpawnAdapter） | 13 passed |
| `test_derive_agents`（派生脚本守护） | 7 passed |
| `test_manager`（含新增 `_annotate_spawn` 3 测） | 11 passed |
| 全量回归 | 115 passed / 2 skipped / 1 failed（唯一失败为 `test_loop` codex CLI 未装的环境性，非回归） |

### 9.5 §8.5 不变量的实现对照

| 不变量 | 实现保证 |
|---|---|
| harness 三步协议不变 | SpawnAdapter 只在 `prepare()` 插入，`commit/advance` 未改 |
| 派生只有一层 | spawn_request 注入 `max_depth: 1` |
| worker 可写 / reviewer 只读 | 三家方言均机制级强制（general-purpose vs Explore / tools allow-list vs disallowedTools / workspace-write vs sandbox read-only） |
| 自包含 instruction 包 | spawn 喂入的是 `step prepare` 产物 |
| 结果由 Manager 转述 | 验收（acceptance）仍是 L1 Manager 步 |
| worker 写操作限工作区 | spawn_request 的 `write_scope` 限定 task_dir |
