# Agent 使用汇报助手说明

本文写给 Codex / Claude Code / WorkBuddy 等宿主 Agent，用于调度 7-Agent 汇报流水线。

## 1. 收敛 brief

用户发起汇报任务后，整理为 `raw_brief.v1` JSON 文件。至少确认：

- `topic`
- `audience`
- `decision_goal`

建议写入：

```text
~/PresentationAgent/workspaces/default/artifacts/briefs/<slug>.json
```

## 2. 启动 report run

```bash
cd "$HOME/PresentationAgent/repo"
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report start \
  --brief-file "<brief_file>"
```

记录返回的：

- `run_id`
- `run_dir`
- `instruction.instruction_path`
- `instruction.output_path`

## 3. 逐阶段循环

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report next --run "<run_id>"
```

读取 `instruction_path`，按指令生成严格 JSON，写入 `output_path`。然后：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report submit --run "<run_id>"
```

如果 CLI 返回 `step != done`，继续 `report next / report submit`。

如果 CLI 返回 `step == done`，把 `present_to_user` 展示给用户，等待用户确认。

用户确认后：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report approve --run "<run_id>"
```

## 4. 记录 human review 反馈

用户在阶段评审中提出质量反馈时，自动记录：

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  feedback-text <agent_id> \
  --text '<用户原话>' \
  --scene human_review_chat \
  --run-state '<stage_dir>/run_state.json'
```

记录后再按用户反馈修正。回复中简短说明：已把反馈记入本阶段 memory。

## 5. 状态查询

```bash
python -m presentation_agent.cli \
  --workspace "$HOME/PresentationAgent/workspaces/default" \
  report status --run "<run_id>"
```

## 6. 边界

- 不绕过 harness 直接编完整报告。
- 必填 brief 字段缺失时追问。
- 写入 `output_path` 时只写 JSON 对象。
- 不删除 workspace。
- 不在命令中写入 token 或 API key。
