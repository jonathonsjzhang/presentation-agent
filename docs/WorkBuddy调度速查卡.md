# WorkBuddy 调度速查卡 · 汇报助手

> 用 WorkBuddy 调度这套 7-Agent 汇报助手的最小操作手册。
> 入口是 **`report_builder` skill**（inline 自执行），harness 只是被调度的工具。
> 最近更新：2026-06-23（补渲染产物展示链路）。

---

## 一句话怎么起

直接对 WorkBuddy 说人话即可，命中 `report_builder` skill 触发词：

> 「帮我做一份 **某 AI 产品战略复盘 PPT**，给 **集团战略负责人** 看，要支撑 **是否加大某新业务投入** 的决策。」

skill 会收敛 brief（topic / audience / decision_goal 三项必填），缺了会追问，齐了自动 `pipeline-init`。

---

## 调度链路（谁调谁）

```
你 → WorkBuddy
      │ 命中 report_builder skill
      ▼
宿主模型（我）亲自执行，不 spawn 外部 CLI
      │
      ├─ pipeline-init            写 brief，建 stage 1
      │
      └─ 7 阶段循环（每阶段都走 A→B→C→D）：
            A. step prepare       harness 吐指令包 instruction_*.md
            B. 我写 JSON          → output_*.json
            C. step commit        校验 schema + 推进状态
            │                     ★ agent4/agent5 commit 时自动渲染真实文件 ★
            D. pipeline-advance   推进到下一阶段
      │
      ▼
pipeline-status 回报 + present_files 展示真实 PPT/HTML
```

三层职责：**skill = 启动+调度协议**；**harness = 被调度的工具（CLI）**；**renderers = commit 阶段的产物引擎**。

---

## 整体跑 vs 分阶段停

| 你怎么说 | 行为 |
|---|---|
| 「整体跑 / 一口气跑完」 | 不等人，连续推进 7 阶段，最后统一回报 |
| 默认（不特别说） | 每阶段 done 后呈现 `human_review.md`，等你确认再 `advance` |
| 「这阶段重做」 | 不 advance，回到 B 重写当前阶段 JSON 后再 commit |

---

## 产物在哪（重点）

- **只有 agent4(page_filling) 和 agent5(format) 出真实文件。** 其余阶段产 JSON 中间件。
- **agent4 → 草稿版**：wireframe 低保真（灰度/简版式），快速校对结构。
- **agent5 → 正式版**：麦肯锡风格（全彩、带图表，vendored mck 引擎驱动）。
- 文件落在该 stage 的 `run_dir`，路径在 commit 返回的 **`rendered_files`** 字段。
- commit 返回 `render_result.status`：
  - `rendered` → 成功，present_files 展示给用户
  - `skipped_missing_dep` → 缺 python-pptx 等可选依赖，不报错，照常推进
  - `no_units` / `error` → 无可渲染单元 / 渲染异常，看 detail

---

## 7 阶段一览

| # | agent_id | 干什么 | 出真实文件 |
|---|---|---|---|
| 1 | （任务定位类）| 收敛 brief、定方向 | |
| … | … | 结构 / 证据 / storyline 等 | |
| 4 | `page_filling` | 内容填充 → **草稿版** PPT/HTML/docx | ✅ draft |
| 5 | `format` | 排版精修 → **正式版** PPT/HTML/docx | ✅ final |
| … | … | Q&A / 收尾 | |

> 阶段全清单以 `python -m presentation_agent.cli list-agents` 为准。

---

## 命令速查

```bash
HARNESS_ROOT=/Users/zhangsijing/Desktop/Coding/presentation_agent
cd $HARNESS_ROOT

# 初始化
python -m presentation_agent.cli pipeline-init --brief '<raw_brief JSON 单行>'

# 每阶段循环
python -m presentation_agent.cli step prepare  --run-dir <stage_dir>   # A 拿指令
#   （我写 output_*.json）                                              # B 产出
python -m presentation_agent.cli step commit   --run-dir <stage_dir>   # C 校验+渲染
python -m presentation_agent.cli pipeline-advance --run-dir <pipeline_dir>  # D 推进

# 查看
python -m presentation_agent.cli step status    --run-dir <stage_dir>
python -m presentation_agent.cli pipeline-status --run-dir <pipeline_dir>
python -m presentation_agent.cli list-agents
```

---

## 边界（别踩）

- 不绕过 harness 自己写正文；正文由各阶段 JSON 经 commit 产生。
- 必填字段（topic/audience/decision_goal）缺失必须追问，不臆造。
- output_*.json 只写纯 JSON 对象，不加 markdown/前后文。
- 命令里不放任何 token/apikey。
- 渲染失败（缺依赖）不阻断流程，按 `skipped_missing_dep` 继续。
