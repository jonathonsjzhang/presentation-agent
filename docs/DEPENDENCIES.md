# 汇报助手 依赖声明

> 本文档声明汇报助手运行所需的外部依赖、版本要求与安装方式。

## 核心依赖（必需）

| 依赖 | 最低版本 | 用途 | 安装方式 |
|---|---|---|---|
| Python | 3.10+ | Harness 运行时 | `pyenv install 3.10` 或系统自带 |
| Git | 2.30+ | 仓库 clone / pull | 系统自带或 `brew install git` |

以上为最低运行要求。Harness 本身不依赖任何第三方 Python 包（纯 stdlib）。

## 渲染器依赖（可选，按需安装）

汇报助手支持三种输出格式。安装对应渲染器后方可生成对应格式的材料：

| 格式 | 依赖 | 安装方式 |
|---|---|---|
| **PPT** | `python-pptx` | `pip install python-pptx` |
| **DOCX** | `python-docx` | `pip install python-docx` |
| **HTML** | 无（自包含模板） | 不需要额外依赖 |

> 缺失可选依赖不会导致运行崩溃——渲染器会返回 `skipped_missing_dep` 状态。

## E2E 评测依赖（仅在评测时需要）

自动评测需要生成材料的视觉快照，依赖以下外部工具：

| 依赖 | 用途 | 安装方式 | 备注 |
|---|---|---|---|
| **LibreOffice** | PPT/DOCX → PDF → 逐页 PNG | `brew install libreoffice` (macOS) | `soffice` 命令需在 PATH 中 |
| **Playwright** | HTML → 浏览器截图 | `npx playwright install chromium` | 需要 Node.js 18+ |
| **Node.js** | Playwright 运行环境 | `nvm install 18` 或系统自带 | |

可通过 `doctor` 命令检查评测依赖的就绪状态：

```bash
python -m presentation_agent.cli doctor
```

输出中的 `evaluation.formats` 字段报告各格式的 `ready` 状态及缺失依赖。

## 可选的辅助工具

| 依赖 | 用途 | 安装方式 |
|---|---|---|
| **GitHub CLI** (`gh`) | PR、issue、CI 操作 | `brew install gh` |
| **Node.js** | DOCX JS 渲染（备选路径） | `nvm install 20` |

## 环境变量

| 变量 | 用途 | 默认值 |
|---|---|---|
| `PRESENTATION_AGENT_REPO_URL` | 企业内部批量部署时覆盖仓库地址 | `https://github.com/jonathonsjzhang/presentation-agent` |
| `PRESENTATION_AGENT_WORKSPACE` | 指定 workspace 路径 | `~/PresentationAgent/workspaces/default` |
| `PRESENTATION_AGENT_SPAWN_ADAPTER` | 默认 sub-agent 适配器 | `inline` |
