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

你是宿主 Agent 里的调度器。用户不需要懂 git、Python、路径或 CLI；你负责准备仓库和 workspace，把用户需求交给汇报助手 Manager，并按 CLI 返回的 actor 推进流程。

这不是让宿主 Agent 自己写报告。内容判断、Worker 派发、验收和返工都由 presentation-agent 的 Manager/Worker loop 完成；宿主只负责“把当前指令正确执行完”。

## 核心原则

- repo 和 workspace 分离：更新 repo 不覆盖用户 workspace
- 只通过高层 CLI 调度：`doctor`、`init-workspace`、`report start/next/submit/approve/status`
- 宿主不替 Manager 决定阶段顺序，不绕过 harness 自己写最终材料
- `actor=human` 时把 `present_to_user` 展示给用户；brief gate 尤其要把 brief 摘要先发出来，再等待确认
- Worker 默认使用当前宿主的原生 sub-agent，以独立上下文执行；宿主自动选择对应 adapter，不向用户询问技术执行方式
- Reviewer sub-agent 默认关闭；只有用户明确要求严格审查、调试质量问题或独立复核时，才使用 `review_mode=independent`
- `inline` 仅用于宿主确实无法派生 sub-agent 的兼容降级；不得静默降级，必须向用户说明 Worker 将失去上下文隔离
- 有 `spawn.detail` 时按 detail 派真实 sub-agent；不要为了省事在主对话代写 worker/reviewer 输出
- 写入 `output_path` 时只写一个合法 JSON 对象，不加 Markdown 前后文
- 不在命令中放 token、API key，也不执行会删除、reset 或覆盖 workspace 的命令

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
```

## 1. 准备或更新环境

### 首次安装

repo 不存在，或用户明确说“安装汇报助手”时：

```bash
mkdir -p "$HOME/PresentationAgent"
git clone "${PRESENTATION_AGENT_REPO_URL:-https://github.com/jonathonsjzhang/presentation-agent}" "$HOME/PresentationAgent/repo"
cd "$HOME/PresentationAgent/repo"
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" init-workspace
python -m presentation_agent.cli --root "$HOME/PresentationAgent/repo" derive-agents
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

### 日常检查

repo 已存在且用户只是要继续使用时，先跑 doctor：

```bash
cd "$HOME/PresentationAgent/repo"
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

若 `doctor` 返回 `ok=false`，先执行：

```bash
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" init-workspace
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

### 更新

用户说“更新汇报助手”时，必须真的更新 repo，并重新派生宿主指令，避免 WorkBuddy / Codex / Claude Code 仍使用旧 adapter：

```bash
cd "$HOME/PresentationAgent/repo"
git pull --ff-only
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" init-workspace
python -m presentation_agent.cli --root "$HOME/PresentationAgent/repo" derive-agents
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

若 `git pull --ff-only` 失败，说明 repo 有本地改动或分叉状态。不要 reset；把错误告诉用户，并询问是否允许切换到干净安装目录或由用户处理本地改动。

## 2. 发起汇报

用户提出汇报需求时，只做输入归集，不在宿主层替 Manager 完成任务定位。只要有可启动的需求线索，就先启动 Manager，让 Manager 在 brief gate 里补问研究目的、当前研究 hypo 和高可信论据。

最小 brief 只需要能表达用户想做什么；其余字段可留空，由 brief gate 汇总默认值并让用户确认：

| 字段 | 建议 | 说明 |
|---|---|---|
| `topic` | 可空 | 报告主题；可由 Manager 根据输入信息和论据总结 |
| `research_purpose` / `decision_goal` | 可空 | `research_purpose` 仅在用户明确提供时填写；brief gate 会主动问“项目研究目的是什么（如为了回答XX问题，或XX研究的延伸）” |
| `research_direction` / `expected_action` / `hypothesis` | 可空 | `research_direction` 仅在用户明确提供研究 hypo 时填写；brief gate 会主动问“当前的研究hypo是什么（如当前结论判断，或预期引导的讨论方向）” |
| `audience` | 可空 | 默认总办（`exec_office`） |
| `project_type` | 可空 | 默认“分析类”；可填“分析类/梳理类” |
| `delivery_targets` / `output_format` | 可空 | 默认文档；如用户要 PPT，则 brief 预设篇幅为 10 页 PPT |
| `report_length` | 可空 | 默认 3 页；PPT 默认 10 页 PPT |
| `materials` | 可空 | 文件路径、素材、已知结论或证据 |
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

这里的 Worker sub-agent 与 Reviewer sub-agent 是两项独立策略：Worker 隔离默认开启；Reviewer 默认关闭，仍使用 brief gate 的 `review_mode=schema_only`。只有用户明确要求严格审查、调试质量问题或独立复核时，才切换为 `review_mode=independent`。

启动：

```bash
cd "$HOME/PresentationAgent/repo"
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report start \
  --brief-file "<brief_file>" \
  --contract-profile "v0_3" \
  --spawn-adapter "<workbuddy|codex|claude>"
```

尖括号内容不是字面值：宿主必须替换成上表中与自身对应的 adapter。若当前宿主无法使用 sub-agent，应先向用户说明无法保证 Worker 上下文隔离，再显式传入 `--spawn-adapter "inline"`；不要在失败后静默改用主对话代写。

第一轮通常会进入 brief human gate。必须先把 CLI 返回的 `instruction.present_to_user` 原样展示给用户，它里面应按顺序包含研究目的、当前研究 hypo、论据列表、报告主题、听众、项目类型、交付形式、报告篇幅、agent 执行流程和“是否发起 review sub_agent：否（更高效）”；不要只发结构化问题，也不要只说“请确认 brief”。如果返回的 `instruction.questions` 存在，宿主应在展示完 Brief 后按 WorkBuddy/AskUserQuestion 风格发起结构化提问：两个文本题分别收集“项目研究目的是什么（如为了回答XX问题，或XX研究的延伸）”和“当前的研究hypo是什么（如当前结论判断，或预期引导的讨论方向）”，一个文本填空题让用户填写高可信论据编号、名称或原文片段。高可信论据不要做成多选题，也不要把 evidence list 截断成少量可选项。不要询问要调起哪些 worker，也不要询问是否发起 review sub_agent 或 full_auto mode；默认全流程执行，不发起 review sub_agent，并在 Analysis、Storyline 两个环节完成后各暂停一次让用户确认，Storyline 确认后自动走到最终报告。用户回答、修改或补充后用 `report feedback --text '<用户原话或结构化答案摘要>'` 回传；用户确认继续后再 approve。若 `present_to_user` 缺少 brief 摘要，先执行 `report status --run "<run_id>"` 检查状态，仍缺失时把 `raw_brief.json` 的主要内容整理给用户看，再请用户确认。

## 3. 推进 report loop

循环执行：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report next --run "<run_id>"
```

根据返回的 `actor` 处理：

### actor=human

展示 `present_to_user`，等待用户决定。brief gate 时必须先展示 brief 摘要；若 `questions` 存在，展示后再用结构化提问收集研究目的、当前研究 hypo 和高可信论据填空，再问是否继续。不要询问 worker 选择或 review sub_agent 选择，不要把确认问题和 brief 内容拆开。

- 用户确认继续：`report approve`
- 用户回答研究目的/当前研究 hypo、填写高可信论据，或要求修改补充信息：`report feedback --text '<用户原话或结构化答案摘要>'`
- brief gate 默认 approve 不传 `--run-mode`，runtime 会在 analysis、storyline 后暂停确认；用户明确要求逐步看结果时才传 `--run-mode step_by_step`
- brief 阶段不要主动询问 review sub_agent；只有用户明确要求严格质量审查、调试质量问题或最终验收时，才使用 `--review-mode independent`

Analysis 论点组确认 gate：

- 如果 `present_to_user` 是“Analysis 论点组确认”且 `questions` 包含“论点组选择”，先把 2-3 组主论点/分论点完整展示给用户，并用结构化提问让用户选择。
- 用户选择某个方案编号（如 `TG-01`）：先执行 `report feedback --text '<选择 TG-01 + 用户说明>'`，CLI 会记录到 `selected_analysis_thesis`；随后在用户明确表示可以后再执行 `report approve` 进入 Storyline。
- 用户选择“都不好，重新写”：必须让用户说明原因，再执行 `report feedback --text '<都不好 + 原因>'`。不要直接 approve；runtime 会复用当前 Analysis task 进入 revise，修订后会再次回到同一个确认 gate。
- 用户选择“我自己修改”：把用户的非结构化修改意见原样放进 `report feedback --text`。不要替用户整理成最终 JSON；当前 Analysis agent 会根据反馈重新整理结构化论点组，并再次请求确认。

Storyline 确认 gate：

- 如果 `present_to_user` 是“Storyline 确认”，只展示这一版核心答案、章节故事线和关键边界，不要要求用户在多版故事线中选择。
- 用户确认可以：执行 `report approve --run "<run_id>"`，进入 Report。
- 用户选择“不好，重新写”：必须让用户说明原因，再执行 `report feedback --text '<不好 + 原因>'`。不要直接 approve；runtime 会复用当前 Storyline task 进入 revise，修订后会再次回到 Storyline 确认 gate。
- 用户选择“我自己修改”：把用户的非结构化修改意见原样放进 `report feedback --text`。不要替用户改 `storyline.v3` JSON；当前 Storyline agent 会根据反馈重新整理一版结构化故事线，并再次请求确认。

示例：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report approve --run "<run_id>"
```

Delivery options gate：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report approve --run "<run_id>" \
  --delivery-option "<format:ppt|format:html|skip>"
```

### actor=manager

读取 `instruction_path`，按指令在主对话执行 Manager 工作，把一个合法 JSON 对象写入 `output_path`，然后：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report submit --run "<run_id>"
```

### actor=worker 且带 spawn.detail

按 `instruction.spawn.detail` 派真实 sub-agent。给 sub-agent 三个路径：

- 指令包：`instruction.instruction_path`
- 输入：当前 task 的 `input.json`
- 写回：`instruction.output_path`

提示 sub-agent：只依据指令包和输入文件工作；worker 只写 `output_path` 一个合法 JSON；reviewer 只返回 `{"objections": [...]}` 或 `{"objections": []}`。

sub-agent 完成且 `output_path` 存在后：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report submit --run "<run_id>" --spawn-completed
```

### actor=worker 且没有 spawn.detail

只有本 run 的 `spawn_adapter=inline` 时，主对话才可以执行该 worker instruction。否则这是调度异常，不要静默代写 worker 输出；先查看状态：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report status --run "<run_id>"
```

如果状态确认 adapter 配置错误，可在下一次 `report next` / `report approve` 显式传入正确 `--spawn-adapter` 修复旧 run，例如：

```bash
python -m presentation_agent.cli \
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

常用补交命令：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report submit --run "<run_id>" --output-file "<output_json>"
```

保持两个底线：

- 非 inline run 不在主对话代写 worker/reviewer 输出
- reviewer 只读，worker 可写；具体 subagent 类型以 `spawn.detail` 为准，不自行猜测

## 5. 最终材料 E2E 自动评测

用户要求“评测 / 打分 / 验收最终 PPT、DOCX 或 HTML 是否够格”时，走独立 eval，不要启动新的 report，也不要把生产流程里的 worker review 当作最终评分。

先检查依赖：

```bash
cd "$HOME/PresentationAgent/repo"
python -m presentation_agent.cli \
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
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report feedback --run "<run_id>" --text '<用户原话>'
```

当用户反馈包含可跨项目复用的质量标准或偏好时，再用自动归因沉淀：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  feedback-text auto \
  --text '<用户原话>' \
  --scene human_review_chat \
  --run-state '<run_dir>/manager_state.json'
```

用户明确认可某个产物、结构或表达时，可记录 success memory：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  success-memory <agent_id> \
  --dimension '<维度>' \
  --pattern '<值得复用的成功模式>' \
  --why '<为什么有效，可留空>' \
  --scene success_review
```

## 状态查询与收尾

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report status --run "<run_id>"
```

全部阶段完成后，告诉用户：

- run 状态
- 最终材料路径
- 关键中间产物路径
- 是否还有 PPT/HTML delivery option 或 E2E eval 可追加

## 边界

- 不绕过 harness 自己写最终材料
- 不在宿主层替 Manager 做任务定位、阶段选择或产物验收
- 不把主对话历史塞回 worker prompt 作为额外事实来源
- 不写 markdown 包裹的 JSON 到 `output_path`
- 不删除、不 reset、不覆盖 workspace
- 不使用开发者本机路径
