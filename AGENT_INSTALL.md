# Agent 安装汇报助手说明

本文写给 Codex / Claude Code / WorkBuddy 等宿主 Agent。用户不需要手动执行这些命令；由宿主 Agent 代为执行。

## 默认路径

```text
repo:      ~/PresentationAgent/repo
workspace: ~/PresentationAgent/workspaces/default
```

## 安装

如果 `~/PresentationAgent/repo` 不存在：

```bash
mkdir -p "$HOME/PresentationAgent"
git clone "$PRESENTATION_AGENT_REPO_URL" "$HOME/PresentationAgent/repo"
cd "$HOME/PresentationAgent/repo"
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" init-workspace
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

若 `PRESENTATION_AGENT_REPO_URL` 未设置，向用户索要 GitHub 仓库地址。

## 检查

```bash
cd "$HOME/PresentationAgent/repo"
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

`doctor` 输出 JSON。若 `ok=false`，先执行：

```bash
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" init-workspace
```

然后再次运行 `doctor`。

## 更新

```bash
cd "$HOME/PresentationAgent/repo"
git pull
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" init-workspace
python -m presentation_agent.cli --workspace "$HOME/PresentationAgent/workspaces/default" doctor
```

不得删除或覆盖 `~/PresentationAgent/workspaces/`。
