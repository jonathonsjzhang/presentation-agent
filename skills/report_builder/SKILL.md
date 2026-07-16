---
name: report-builder
description: >-
  互联网战略分析汇报助手【宿主入口 · GitHub 分发 · CLI 调度】。当用户说"安装汇报助手"、
  "更新汇报助手"、"帮我做一份战略汇报 / 复盘 / 高管汇报 / 汇报 PPT / storyline /
  分析报告"，或要求对最终 PPT、DOCX、HTML 材料做 E2E 评测、打分、质量验收时使用。
  宿主 Agent 负责自动 clone/pull 官方仓库、初始化 workspace，并通过 presentation-agent
  report 或 eval 命令推进对应协议。触发词：战略汇报、复盘报告、汇报PPT、高管汇报、
  storyline、分析报告、最终材料评测、E2E评测、材料打分、安装汇报助手、更新汇报助手。
---

# 汇报助手 · Host Adapter Skill

你是宿主 Agent 里的调度器。用户不需要懂 git、Python、路径或 CLI；你负责准备仓库和 workspace，把用户需求交给汇报助手 Manager，并按 CLI 返回的 actor 推进流程。

这不是让宿主 Agent 自己写报告。内容判断、Worker 派发、验收和返工都由 presentation-agent 的 Manager/Worker loop 完成；宿主只负责“把当前指令正确执行完”。

## 核心原则

- repo 和 workspace 分离：更新 repo 不覆盖用户 workspace
- 只通过高层 CLI 调度：`doctor`、`init-workspace`、`report start/next/submit/approve/status`
- 宿主不替 Manager 决定阶段顺序，不绕过 harness 自己写最终材料
- `actor=human` 时把 `present_to_user` 展示给用户；brief gate 尤其要把 brief 摘要先发出来，再等待确认
- Brief 确认后的 planning `dispatch` 由 runtime 自动派发 Analysis，不向用户展示或确认固定 execution plan；只有 Manager `ask_human` 时才再次停下
- Worker 默认使用当前宿主的原生 sub-agent，以独立上下文执行；宿主自动选择对应 adapter，不向用户询问技术执行方式
- 不派发过程 Reviewer sub-agent；Worker 在同一上下文自检，runtime 只做确定性校验
- `inline` 仅用于宿主确实无法派生 sub-agent 的兼容降级；不得静默降级，必须向用户说明 Worker 将失去上下文隔离
- 有 `spawn.detail` 时按 detail 派真实 Worker sub-agent；不要为了省事在主对话代写 Worker 输出
- 写入 `output_path` 时服从当前 instruction 的 `response_format`：v0.4 的 Analysis、Storyline、Report、QA 直接写 Markdown；Format 和 Manager 写合法 JSON；不要自行包裹 code fence
- 不在命令中放 token、API key，也不执行会删除、reset 或覆盖 workspace 的命令
- 用户提供文件或目录时，宿主只把路径登记进 `materials[].path`。禁止在 `report start` 前自行派 Explore/Research sub-agent 完整读取或总结材料；正式读取统一由 Manager 的 run-level Evidence Intake 完成
- 二进制表格硬规则：`.xlsx` 不交给宿主通用 Read，也不在宿主层运行 openpyxl 后打印整表。把路径原样写入 brief；runtime connector 会解析为受控预览、`data_profile`/`data_assets` 和完整 JSON sidecar，Worker 只按需读取 sidecar 切片，避免大输出截断

## 默认位置

```text
repo:      ~/PresentationAgent/repo
workspace: ~/PresentationAgent/workspaces/default
```

官方仓库地址固定为 `https://github.com/jonathonsjzhang/presentation-agent`。若设置了 `PRESENTATION_AGENT_REPO_URL`，优先使用该环境变量。

常用变量：

```bash
REPO_URL="${PRESENTATION_AGENT_REPO_URL:-https://github.com/jonathonsjzhang/presentation-agent}"
REPO_DIR="$HOME/PresentationAgent/repo"
WORKSPACE="$HOME/PresentationAgent/workspaces/default"
PA_PYTHON="$REPO_DIR/.venv/bin/python"
```

## 1. 准备或更新环境

### 首次安装

repo 不存在，或用户明确说“安装汇报助手”时：

```bash
mkdir -p "$HOME/PresentationAgent"
git clone "${PRESENTATION_AGENT_REPO_URL:-https://github.com/jonathonsjzhang/presentation-agent}" "$HOME/PresentationAgent/repo"
cd "$HOME/PresentationAgent/repo"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" init-workspace
.venv/bin/python -m presentation_agent.cli --root "$HOME/PresentationAgent/repo" derive-agents
.venv/bin/python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

### 日常检查

repo 已存在且用户只是要继续使用时，先跑 doctor：

```bash
cd "$HOME/PresentationAgent/repo"
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

若 `doctor` 返回 `ok=false`，先执行：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" init-workspace
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

### 更新

用户说“更新汇报助手”时，必须真的更新 repo，并重新派生宿主指令，避免 WorkBuddy / Codex / Claude Code 仍使用旧 adapter：

```bash
cd "$HOME/PresentationAgent/repo"
git pull --ff-only
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" init-workspace
.venv/bin/python -m presentation_agent.cli --root "$HOME/PresentationAgent/repo" derive-agents
.venv/bin/python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

若 `git pull --ff-only` 失败，说明 repo 有本地改动或分叉状态。不要 reset；把错误告诉用户，并询问是否允许切换到干净安装目录或由用户处理本地改动。

## 2. 发起汇报

用户提出汇报需求时，只做输入归集，不在宿主层替 Manager 完成任务定位。只要有可启动的需求线索，就先启动 Manager，让 Manager 在 brief gate 里补问研究背景、当前研究 hypo 和高可信论据。

最小 brief 只需要能表达用户想做什么；其余字段可留空，由 brief gate 汇总默认值并让用户确认：

| 字段 | 建议 | 说明 |
|---|---|---|
| `topic` | 可空 | 报告主题；可由 Manager 根据输入信息和论据总结 |
| `research_purpose` / `decision_goal` | 可空 | `research_purpose` 是兼容字段，仅在用户明确提供时填写；brief gate 对用户主动问“项目研究背景是什么（如业务现状、问题由来或发起本次研究的上下文）” |
| `research_direction` / `expected_action` / `hypothesis` | 可空 | `research_direction` 仅在用户明确提供研究 hypo 时填写；brief gate 会主动问“当前的研究hypo是什么（如当前结论判断，或预期引导的讨论方向）” |
| `audience` | 可空 | 默认总办（`exec_office`） |
| `project_type` | 可空 | 默认“分析类”；可填“分析类/梳理类” |
| `delivery_targets` / `output_format` | 可空 | 默认文档；如用户要 PPT，则 brief 预设篇幅为 10 页 PPT |
| `report_length` | 可空 | 默认 3 页；PPT 默认 10 页 PPT |
| `materials` | 可空 | 文件或目录使用 `{"path": "..."}`；已知结论可作为结构化 claim。宿主不预读文件内容 |
| `constraints` | 可空 | 页数、保密、口径、格式限制 |
| `user_intent` | 可空 | 用一句自然语言记录用户真实意图 |

将 brief 写成 JSON 文件，例如：

```text
~/PresentationAgent/workspaces/default/artifacts/briefs/<slug>.json
```

Worker 默认启用独立 sub-agent。宿主应根据自身运行环境自动选择原生 adapter，不要询问用户选择哪种 adapter：

| 当前宿主 | `--spawn-adapter` |
|---|---|
| WorkBuddy | `workbuddy` |
| Codex | `codex` |
| Claude Code | `claude` |
| 不支持 sub-agent 的宿主 | `inline`（仅兼容降级，需明确告知用户） |

Worker sub-agent 默认使用隔离上下文，并在本轮内自检后提交。流程中不再额外派发 Reviewer sub-agent；如需最终独立质量验收，在交付后使用 E2E Eval，不嵌入生产链返工。

启动：

```bash
cd "$HOME/PresentationAgent/repo"
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report start \
  --brief-file "<brief_file>" \
  --contract-profile "v0_4" \
  --spawn-adapter "<workbuddy|codex|claude>"
```

尖括号内容不是字面值：宿主必须替换成上表中与自身对应的 adapter。若当前宿主无法使用 sub-agent，应先向用户说明无法保证 Worker 上下文隔离，再显式传入 `--spawn-adapter "inline"`；不要在失败后静默改用主对话代写。

有文件、目录或原始数据时，第一轮先返回 Evidence Harvester worker instruction；宿主按正常 spawn/submit 协议完成后，runtime 才进入 brief human gate。没有待处理原始材料或已有可复用 Catalog 时，第一轮直接进入 brief human gate。

Brief gate 必须严格按 runtime 返回的单次四题协议执行，不得拆分、跳步或自行增删问题：

### WorkBuddy 工具调用硬约束

进入任何 Brief human gate 后，先检查当前工具列表：

- 有 `AskUserQuestion`：`interaction_required=true` 时，**下一步唯一合法动作是实际调用 `AskUserQuestion` 工具**。展示 `present_to_user` 后必须在同一轮发起工具调用；禁止只把问题写成普通文本，禁止先输出最终答复，禁止先执行 `report feedback` / `report approve` / `report next`。
- 没有 `AskUserQuestion`：才允许用普通文本逐项提问，并明确这是宿主工具不可用时的降级。不得因为模型觉得信息“已经足够”而跳过问题。

不要自行拼参数。runtime 已提供可直接透传的 `ask_user_question_payload`。WorkBuddy 调用形态固定为：

```tool_call
AskUserQuestion(
  questions = current_instruction.ask_user_question_payload.questions
)
```

例如填空阶段的实际参数应形如：

```json
{
  "questions": [
    {
      "question": "当前的研究hypo是什么？",
      "header": "当前研究 hypo",
      "options": [],
      "multiSelect": false
    }
  ]
}
```

`options=[]` 在 WorkBuddy 中会保留自由输入框；不要为了“让工具更像选择题”而补任何占位 option。

### Brief 展示顺序硬约束

runtime 会返回 `presentation_required_before_tool=true`、独立的 `presentation_text`、`presentation_delivery_mode=separate_user_visible_message_before_tool` 和固定的 `host_action_sequence=["send_present_to_user_message", "call_AskUserQuestion"]`。宿主必须严格执行：

1. 先发送一条**独立且不带任何 tool call** 的用户可见消息，正文原样使用 `presentation_text`（即完整 `present_to_user`）；
2. 等这条消息完成发送并已在用户界面中展示；确认正文中出现 `## Brief 草案`、Evidence List、报告设定和执行流程；
3. 再执行后续 host action，调用 `AskUserQuestion`。

把 Brief 写在一个同时含有 `tool_calls` 的 assistant completion 的 `content` 前缀中，不算完成展示。禁止只说“现在进入 Brief 确认”或自行缩写 Brief 后就调用工具；禁止把 Brief 塞进某一道题的 `question` 文本；禁止先调用工具再补 Brief。

1. `brief_stage=collection_and_confirmation`：严格先完整输出 `presentation_text`，然后**调用一次 `AskUserQuestion`**，在同一个工具调用中原样传入 4 个问题：研究背景、当前研究 hypo、高可信论据、Brief 确认。前三题即使草案已有推断值也必须再次询问，不能因“已有内容”而删除；前三题保持 `options=[]`，第四题保持“准确，继续 / 需要修改”。
2. 将四题答案汇总为 JSON 回传，例如 `{"research_purpose":"...","research_direction":"...","high_confidence_evidence":["EV-003","EV-008"],"brief_confirmed":true}`；没有特别优先的论据也必须显式传 `"high_confidence_evidence":[]`。执行 `report feedback --text '<上述 JSON>'` 后，runtime 会把答案写回 `raw_brief.json` 并记录本次明确确认。
3. 若用户选择“准确，继续”，feedback 返回 `next_action=report_approve_without_asking_again`，直接执行 `report approve`，**不得再弹第二个确认面板**。若用户选择“需要修改”，把修改归入 `brief_updates` 且传 `"brief_confirmed":false`；runtime 重显更新后的完整 Brief，并只再次询问确认。

最终确认页应按顺序包含研究背景、当前研究 hypo、正式 Evidence List、用户标记的高可信论据、报告主题、听众、项目类型、交付形式、报告篇幅和 agent 执行流程。不要询问要调起哪些 worker、reviewer 或 full_auto mode；默认全流程执行，并在 Analysis、Storyline 两个环节完成后各暂停一次让用户确认，Storyline 确认后自动走到最终报告。若 `present_to_user` 缺少 Brief 内容，先执行 `report next --run "<run_id>"` 重新取得 `current_instruction`，并用 `report status` 核对 actor/gate；仍缺失则报告协议错误，不要凭宿主记忆拼一份后直接批准。

## 3. 推进 report loop

`report start/next/continue/submit/approve/feedback/revise` 使用同一个轻量响应契约：当前动作始终位于
`current_instruction`。不要再根据命令分别猜测 `result` 或 `instruction`；完整 Manager
state、Worker artifact、Evidence Catalog 只通过返回的 `*_path` / `*_ref` 按需读取。
`report status` 默认只返回控制面摘要；只有诊断确需完整状态时才使用
`report manager-status`。

循环执行：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report next --run "<run_id>"
```

根据返回的 `current_instruction.actor` 处理：

当 Worker 已写好 `output_path` 时，优先执行 `report continue --run "<run_id>"`：它会自动消费已存在的输出和确定性转移，直到下一个人工 Gate、需要外部 Worker 产出或结构化错误。它不会代写 Worker 内容。

### actor=human

展示 `present_to_user` 后立即检查 `interaction_required`。值为 `true` 时必须调用 `preferred_tool`；在 WorkBuddy 中就是把 `ask_user_question_payload` 透传给 `AskUserQuestion`。首次 Brief gate 必须在一个面板中完整呈现 4 题；不能因为草案已有研究背景而删题，也不能把 Brief 确认推迟到另一轮。不要询问 worker、reviewer 或自动化模式选择。

- 四题答案：`report feedback --text '{"research_purpose":"...","research_direction":"...","high_confidence_evidence":[...],"brief_confirmed":true}'`
- feedback 返回 `report_approve_without_asking_again` 时：`report approve`
- 最终确认页要求修改：`report feedback --text '{"brief_updates":{"topic":"...","report_length":"..."}}'`；待完整 Brief 重显后再确认
- brief gate 默认 approve 不传 `--run-mode`，runtime 会在 analysis、storyline 后暂停确认；用户明确要求逐步看结果时才传 `--run-mode step_by_step`
- brief 阶段不询问 review mode；质量策略固定为 Worker 自检 + runtime 确定性校验 + 最终真实渲染验收

Analysis 论点组确认 gate：

- 如果 `present_to_user` 是“Analysis 论点组确认”，先把 2-3 组主论点/分论点完整展示给用户，然后只发起 **1 个自由输入问题**（`inputType=text, options=[]`），不得再追加“选择说明/其他补充”第二题。
- 这一个输入框同时承载确认和修改：用户填写方案编号（如 `TG-01`，理由可选）即确认；填写“都不好 + 原因”即要求重写；直接填写修改意见即表示“我自己修改”。
- 用户填写某个方案编号：先执行 `report feedback --text '<选择 TG-01 + 可选理由>'`，CLI 会记录到 `selected_analysis_thesis`；随后执行 `report approve` 进入 Storyline。
- 用户填写“都不好 + 原因”：执行 `report feedback --text '<都不好 + 原因>'`。不要直接 approve；runtime 会复用当前 Analysis task 进入 revise，修订后会再次回到同一个确认 gate。
- 用户直接填写修改意见：把非结构化修改意见原样放进 `report feedback --text`。不要替用户整理成最终 JSON；当前 Analysis agent 会根据反馈重新整理结构化论点组，并再次请求确认。

Storyline 确认 gate：

- 如果 `present_to_user` 是“Storyline 确认”，只展示这一版核心答案、章节故事线和关键边界，不要要求用户在多版故事线中选择。
- 首次确认只发起 **1 个选择题**（可以进入 Report / 不好，重新写 / 我自己修改），不得固定追加“修改说明”第二题。只有用户选择后两项却没有给出可执行意见时，才在下一轮单独追问修改内容。
- 用户确认可以：执行 `report approve --run "<run_id>"`，进入 Report。
- 用户选择“不好，重新写”：必须让用户说明原因，再执行 `report feedback --text '<不好 + 原因>'`。不要直接 approve；runtime 会复用当前 Storyline task 进入 revise，修订后会再次回到 Storyline 确认 gate。
- 用户选择“我自己修改”：把用户的非结构化修改意见原样放进 `report feedback --text`。不要由宿主直接改 canonical Storyline；当前 Storyline agent 会根据反馈重写完整故事线并再次请求确认。

篇幅确认 gate：

- runtime 以 Brief 页数为目标，并自动容许正文最多多 1 页；字符预算只作写作引导与预警。
- 若 `human_gate=page_budget`，先展示实际页数、目标页数和自动容差上限，再透传 runtime 返回的单题选择面板。
- 用户选择“接受当前篇幅”：执行 `report feedback --text '放宽'`，runtime 将当前实际页数写为用户批准的新上限并继续。
- 用户选择“继续收窄”：执行 `report feedback --text '收窄'`，runtime 复用当前 Report/Format task 返工；不要自行改 Brief 页数或跳过该 gate。

示例：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report approve --run "<run_id>"
```

Delivery options gate：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report approve --run "<run_id>" \
  --delivery-option "<format:ppt|format:html|skip>"
```

### actor=manager

读取 `instruction_path`，按指令在主对话执行 Manager 工作，把一个合法 JSON 对象写入 `output_path`，然后：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report submit --run "<run_id>"
```

### actor=worker 且带 spawn.detail

按 `instruction.spawn.detail` 派真实 sub-agent。给 sub-agent 三个路径：

- 指令包：`instruction.instruction_path`
- 输入：当前 task 的 `input.json`
- 写回：`instruction.output_path`

提示 sub-agent：只依据指令包和输入文件工作；严格按 instruction 的 `response_format` 写入 `output_path`。v0.4 的 Analysis、Storyline、Report、QA 直接写规范 Markdown，Format 写 `format_plan.v1` JSON。

输入文件若包含 `parsed_artifact_path` / `raw_access` / `table_data_access`，说明原始 XLSX/CSV 已由 runtime connector 处理。sub-agent 不要重新直接读取二进制文件，也不要把完整 sidecar 一次性打印到对话；先用内联画像和 source units，只有具体论据需要时才读取对应字段或 sheet。

Analysis 和 Storyline 仍进入用户确认 Gate；Report 与 QA 正常完成后由 runtime 自动推进，不再创建一轮无实质判断的 Manager acceptance。用户反馈或 blocked 时，Manager 必须显式给出 `stage`。固定下一 Worker、task_id 和正式 artifact 路径由 runtime 管理；宿主不要自行拼接 handoff 路径。

用户在任一人工 Gate 明确要求修改某阶段时，直接调用：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report revise --run "<run_id>" --stage "<analysis|storyline|report|qa_preparation|format>" \
  --feedback "<用户原始修改意见>"
```

不要把这类明确反馈再交给 runtime 猜测责任阶段。同一错误第一次会在同 task 修订，连续第二次会返回 `structured_error` 并熔断；宿主不得绕过熔断继续重派。

sub-agent 完成且 `output_path` 存在后：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report submit --run "<run_id>" --spawn-completed
```

Worker 的 `result_delivery=direct_file`：Agent/Task 工具的对话消息可以为空，不能据此判定
失败。完成标准是当前 `output_path` 存在、晚于本轮 spawn request、符合 instruction 声明的非空 Markdown 或 JSON，且
`report submit --spawn-completed` 成功生成 receipt 并 commit。若消息为空但文件有效，直接
按成功处理；若消息非空但没有可信文件，则按失败处理。

Worker instruction 只内嵌 skill、任务摘要、schema 和输入路径。完整 Evidence Catalog 与
上游 artifact 位于 `input_path`；先读取顶层索引，再按 evidence/source ref 深入，禁止把
整个 input 或 sidecar 打印到宿主对话。

### actor=worker 且没有 spawn.detail

只有本 run 的 `spawn_adapter=inline` 时，主对话才可以执行该 worker instruction。否则这是调度异常，不要静默代写 worker 输出；先查看状态：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report status --run "<run_id>"
```

如果状态确认 adapter 配置错误，可在下一次 `report next` / `report approve` 显式传入正确 `--spawn-adapter` 修复旧 run，例如：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report next --run "<run_id>" --spawn-adapter "workbuddy"
```

## 4. WorkBuddy / sub-agent 失败处理

WorkBuddy 的 subagent 调度失败时，最重要的是不要假装已经执行。

按顺序处理：

1. 确认 CLI 当前 instruction 仍然是同一个 `run_id` / `task_id` / `output_path`
2. 确认 `instruction.spawn.detail` 存在，并优先照 detail 重新派发
3. 如果 sub-agent 返回了内容但没写入 `output_path`，用 `report submit --output-file "<output_json>"` 提交该 JSON
4. 如果没有可信 JSON 产物，不要手写补齐；运行 `report status`，把错误和当前 gate 告诉用户

Manager `report submit` 在应用决策时失败后，runtime 会自动回滚到同一轮 `awaiting_output`。此时执行 `report next` 取回原 instruction，修正 `output_path` 后再次 `report submit`；不要用 `approve` 强推，也不需要手改 state。

常用补交命令：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report submit --run "<run_id>" --output-file "<output_json>"
```

保持两个底线：

- 非 inline run 不在主对话代写 Worker 输出
- Worker 只能写当前 task_dir 与指定 handoff 输出；具体 subagent 类型以 `spawn.detail` 为准

## 5. 最终材料 E2E 自动评测

用户要求“评测 / 打分 / 验收最终 PPT、DOCX 或 HTML 是否够格”时，走独立 eval，不要启动新的 report，也不要把生产流程里的 worker review 当作最终评分。

先检查依赖：

```bash
cd "$HOME/PresentationAgent/repo"
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  doctor
```

读取 `doctor` 返回的 `evaluation.formats`。目标格式 `ready=false` 时，告诉用户缺失的 runtime；不要用纯文本评分冒充视觉评测。依赖就绪后，读取并遵循仓库内 `skills/evaluator/SKILL.md` 的 `eval start → next/submit → result` 协议。

路由边界：

- 生成 / 修改材料 → `report` loop
- 检查某个生产环节产物 → 当前 worker 的 review/revise
- 评价最终 PPT / DOCX / HTML 是否够格 → 独立 eval run
- 同时要求生成和评分 → 先完成 report，再以最终文件启动 eval

## 6. 反馈与长期记忆

用户对当前 run 的修改意见：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report feedback --run "<run_id>" --text '<用户原话>'
```

当用户反馈包含可跨项目复用的质量标准或偏好时，再用自动归因沉淀：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  feedback-text auto \
  --text '<用户原话>' \
  --scene human_review_chat \
  --run-state '<run_dir>/manager_state.json'
```

用户明确认可某个产物、结构或表达时，可记录 success memory：

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  success-memory <agent_id> \
  --dimension '<维度>' \
  --pattern '<值得复用的成功模式>' \
  --why '<为什么有效，可留空>' \
  --scene success_review
```

## 状态查询与收尾

```bash
"$HOME/PresentationAgent/repo/.venv/bin/python" -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report status --run "<run_id>"
```

全部阶段完成后，告诉用户：

- run 状态
- 最终材料路径
- `published_files`（稳定发布目录 `workspace/artifacts/deliverables/<run_id>/`）
- 关键中间产物路径
- 是否还有 PPT/HTML delivery option 或 E2E eval 可追加

## 边界

- 不绕过 harness 自己写最终材料
- 不在宿主层替 Manager 做任务定位、阶段选择或产物验收
- 不把主对话历史塞回 worker prompt 作为额外事实来源
- 不把 Markdown 产物包进 JSON，也不写 Markdown code fence 包裹的 JSON
- 不删除、不 reset、不覆盖 workspace
- 不使用开发者本机路径
