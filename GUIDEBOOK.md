# 汇报助手用户指南

> 适用平台：WorkBuddy / Codex / Claude Code 等具备终端能力的 AI Agent
> GitHub 仓库：`https://github.com/jonathonsjzhang/presentation-agent`

---

## 第一步：安装

在 Agent 终端中发送以下指令，即可一次性完成安装与初始化：

> "请 clone `https://github.com/jonathonsjzhang/presentation-agent`，按照仓库里 `skills/report_builder/SKILL.md` 的说明安装汇报助手并完成初始化。"

Agent 会自动 clone 仓库、读取 skill、初始化工作区并运行自检，完成后回复安装成功。此指令对所有平台通用，无需区分终端类型，也无需预先放置任何文件。

**更新**：发送"更新汇报助手"，Agent 拉取最新代码并重新初始化，历史汇报记录与记忆数据不受影响。

---

## 第二步：发起汇报

以自然语言提出需求。Agent 会先进入 Brief 确认，主动展示完整 Brief，再追问研究目的、当前研究 hypo，并让你填写哪些论据属于高可信；其他信息会根据原始输入总结，缺少时使用预设值再请你确认。

| 信息 | 含义 | 默认 / 示例 |
|---|---|---|
| 研究目的 | 项目研究目的是什么（如为了回答XX问题，或XX研究的延伸） | "AI 对广告行业的重塑会改变哪些竞争壁垒？" |
| 当前研究 hypo | 当前的研究hypo是什么（如当前结论判断，或预期引导的讨论方向） | "明年应加大 AI 广告产品投入" |
| 高可信论据 | 从 agent 整理的 evidence list 中填写编号、名称或原文片段 | 用于判断子论点可信度和引用优先级 |
| 报告主题 | Manager 根据输入信息和论据总结 | 可在确认时修改 |
| 听众 | 总办 / 董事会 / 业务负责人等 | 默认总办 |
| 项目类型 | 分析类 / 梳理类 | 默认分析类 |
| 交付形式 | 文档 / PPT / HTML | 默认文档 |
| 报告篇幅 | 交付物长度 | 默认 3 页；PPT 默认 10 页 |
| agent执行流程 | analysis（分析） → storyline（故事线） → report（报告产出） → format（可视化排版） | 默认全流程执行，不询问 worker 选择 |
| 是否发起review sub_agent | 是否启用独立 review sub-agent | 默认否（更高效） |

可同步补充保密要求、已有分析资料等。Agent 默认先生成完整文档；Analysis 完成后会给出 2-3 组主论点 + 分论点供你选择，如果都不好或你想自己修改，会回到同一个 Analysis agent 修订并再次确认；Storyline 完成后会展示一版故事线请你确认，如果不好或你想自己修改，会回到同一个 Storyline agent 修订并再次确认，确认后自动走到最终报告。文档完成后，再询问是否需要转为 PPT / HTML，或追加 QA list / 逐字稿。

**示例：**

> 用户：帮我分析 AI 对广告行业的重塑。汇报对象是 CEO 和 COO，要支撑"明年是否加大 AI 广告产品投入"这个决策，不提及具体客户名称。

---

## 第三步：按 Manager 计划审阅

Manager 默认按四个阶段执行：分析 → 故事线 → 报告产出 → 文档可视化。Evidence 由分析阶段按需内部调用，不单独成为进度节点。文档完成后，Agent 会询问是否继续生成 PPT、HTML、QA list 或逐字稿。每个配置的暂停点，Agent 会展示产出摘要并等待确认。你可以：

- 回复"继续"，进入下一阶段；
- 直接提出修改意见，Agent 在本阶段修正后重新提交。

提出的反馈会被自动记录为该阶段的经验，后续同类汇报自动参考，无需重复说明。

---

## 第四步：获取最终材料

默认先交付完整 DOCX。你确认后可以结束任务，也可以选择继续转译为 PPT / HTML，或生成 QA list / 逐字稿。产物位于工作区的 `runs/<run_id>/output/` 路径下。

---

## 第五步：触发 E2E 自动评测

自动评测用于判断最终 PPT、DOCX 或 HTML 是否已经达到可用于管理层汇报的质量。它独立于生产过程中的 Worker review，不修改原材料、最终文件或长期 memory。

### 对话中直接触发

最简单的方式是让 Agent 评测刚生成的材料：

> "请对刚才生成的最终材料执行 E2E 自动评测，并告诉我四个维度的得分、主要问题和修改建议。"

也可以指定文件和原始素材：

> "请用汇报助手的 E2E 自动评测功能评测 `/path/to/final.pptx`。Brief 是 `/path/to/brief.json`，原始材料包括 `/path/to/data.xlsx` 和 `/path/to/research.docx`。使用 v0.2 rubric。"

Agent 应读取仓库中的 `skills/evaluator/SKILL.md`，自动完成文件预处理、Judge 调度和结果聚合。用户不需要手动执行命令。

建议至少提供：

| 输入 | 是否必需 | 作用 |
|---|---|---|
| 最终材料 | 必需 | 待评测的 `.pptx`、`.docx` 或 `.html` |
| Brief / 汇报要求 | 建议 | 判断材料是否符合受众、决策目标和格式要求 |
| 原始材料 | 建议 | 判断已有数据、论据和访谈是否被充分、准确使用 |
| Rubric 版本 | 可选 | 默认使用 `v0.2`；指定版本便于历史结果可比 |

### Agent 后台执行协议

宿主 Agent 使用以下命令启动评测。`--material` 可以重复传入：

```bash
python -m presentation_agent.cli \
  --root <repo-path> \
  --workspace <workspace-path> \
  eval start \
  --artifact <final.pptx|final.docx|final.html> \
  --brief-file <brief.json> \
  --material <source-1.xlsx> \
  --material <source-2.docx> \
  --rubric v0.2
```

命令会返回 `instruction_path` 和 `output_path`。Agent 在独立上下文中执行该 instruction，把严格 JSON 写入 output 后调用：

```bash
python -m presentation_agent.cli \
  --root <repo-path> \
  --workspace <workspace-path> \
  eval submit --run <eval-run>
```

第一次 `submit` 完成 Content Judge，并返回 Visual Judge instruction；Agent 执行后再次调用同一条 `eval submit`。第二次提交完成后读取结果：

```bash
python -m presentation_agent.cli \
  --root <repo-path> \
  --workspace <workspace-path> \
  eval result --run <eval-run>
```

如果对话中断，可通过以下命令恢复：

```bash
python -m presentation_agent.cli \
  --root <repo-path> \
  --workspace <workspace-path> \
  eval next --run <eval-run>
```

完整循环为：

```text
eval start
  → Content Judge 写回 JSON
  → eval submit
  → Visual Judge 查看全部截图并写回 JSON
  → eval submit
  → eval result
```

### 不同格式如何评测

- **PPT/PPTX**：提取 slide 文本，同时把每页渲染为 PNG；Visual Judge 必须逐页检查截图和 contact sheet。
- **DOC/DOCX**：提取正文，同时按真实分页渲染；重点检查章节层级、表格/图形、分页和连续阅读体验。
- **HTML**：提取可见文本，并通过浏览器生成模块截图或视口分片；重点检查首屏、导航、模块关系和滚动阅读节奏。

视觉截图是正式评测的硬门。截图缺失或 PPT/HTML 页面覆盖不完整时，`visual_snapshots_ready` / `visual_coverage_complete` 会失败，系统不会退化成只读文本后仍宣称材料通过。`--no-render` 只用于诊断，不应用于正式评测。

### 评分结果

默认 `v0.2` rubric 包含：

| 维度 | 权重 |
|---|---:|
| 信息密度 | 30% |
| Storyline | 30% |
| 表达精炼 | 20% |
| 信息呈现 | 20% |

每个维度按 0–5 分、0.5 分刻度评分。最终报告包含：

- 四个维度的得分、理由和具体页码证据；
- 加权总分及 100 分制换算；
- 最主要的三个问题和三个修改建议；
- 截图、格式和文件完整性 hard gates；
- `formal_ready`、`needs_revision` 或 `not_usable` 结论。

评测 run 默认保存在用户工作区的 `runs/evals/<eval-run>/`，其中 `final_report.json` 是最终结果，`prepared/pages/` 和 `contact-sheet.png` 是 Visual Judge 使用的视觉输入。

---

## 可定制维度

在提出需求时说明以下维度，Agent 会自动匹配对应的生成与审查配置：

| 维度 | 可选值 |
|---|---|
| 汇报对象 | 董事会、总办汇报、战略负责人、业务负责人和业务团队、外部分享 |
| 汇报性质 | 专题深度分析、信息快速同步 |
| 材料格式 | PPT、文档、HTML |

---

## 常见问题

**需要 Python 或 Git 吗？** 不需要。所有环境依赖与命令行操作由 Agent 在后台完成。

**需要申请模型 API Key 吗？** 不需要。汇报助手不调用模型，内容的生成与审阅由你当前使用的 AI Agent 的模型完成。

**中途断了怎么办？** 支持断点续传。下次对话中发送"继续上次汇报"即可从断点恢复。

**更新会影响历史数据吗？** 不会。程序（`~/PresentationAgent/repo/`）与数据（`~/PresentationAgent/workspaces/`）分离存放，更新仅改动程序文件。

**自动评测会修改材料或写入 memory 吗？** 不会。评测只读最终材料和输入上下文，结果写入独立 eval run。

**为什么 PPT/HTML 评测失败但文件可以打开？** 先检查评测结果中的视觉 hard gate。PPT/DOCX 截图依赖 LibreOffice/PDF 渲染，HTML 截图依赖 Playwright/Chromium；无法生成完整截图时系统会主动阻断视觉放行。

---

> 系统架构与技术细节请参阅 README 与 `docs/汇报助手系统设计方案.md`。
