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

以自然语言提出需求。Agent 会先完整展示 Brief 草案，再在 WorkBuddy 中调起一次 `AskUserQuestion` 面板，固定包含研究背景、当前研究 hypo、高可信论据三个纯填空题，以及“Brief 是否准确”确认题。即使草案已推断出研究背景，也会再次向你确认；前三题不会混入“用户提供/用户填写”等占位选项。四题提交后答案会写回 Brief，选择“准确，继续”即可开始分析，不会再重复弹第二个确认面板。

| 信息 | 含义 | 默认 / 示例 |
|---|---|---|
| 研究背景 | 项目研究背景是什么（如业务现状、问题由来或发起本次研究的上下文） | "AI 能力快速进入广告生产链路，现有竞争壁垒正在发生变化" |
| 当前研究 hypo | 当前的研究hypo是什么（如当前结论判断，或预期引导的讨论方向） | "明年应加大 AI 广告产品投入" |
| 高可信论据 | 从 agent 整理的 evidence list 中填写编号、名称或原文片段 | 用于判断子论点可信度和引用优先级 |
| 报告主题 | Manager 根据输入信息和论据总结 | 可在确认时修改 |
| 听众 | 总办 / 董事会 / 业务负责人等 | 默认总办 |
| 项目类型 | 分析类 / 梳理类 | 默认分析类 |
| 交付形式 | 文档 / PPT / HTML | 默认文档 |
| 报告篇幅 | 交付物长度 | 默认 3 页；PPT 默认 10 页 |
| agent执行流程 | analysis（分析） → storyline（故事线） → report（报告产出） → qa_preparation（追问清单） → format（可视化排版） | 默认全流程执行，不询问 worker 选择 |
| 是否发起review sub_agent | 是否启用独立 review sub-agent | 默认否（更高效） |

可同步补充保密要求、已有分析资料等。Agent 默认先生成完整文档；Analysis 完成后会展示完整分析与 2-3 组主论点方案，Storyline 完成后会展示一版完整故事线。两处确认后，Report、独立 QA 和 Format 自动推进到最终材料。QA 是默认主链的一部分，不在 Report Worker 内生成；Report 或 Format 的局部返工可以跳过 QA 并复用最近一次追问清单。

**示例：**

> 用户：帮我分析 AI 对广告行业的重塑。汇报对象是 CEO 和 COO，要支撑"明年是否加大 AI 广告产品投入"这个决策，不提及具体客户名称。

---

## 第三步：审阅两个关键节点

默认主链是：分析 → 故事线 → 报告产出 → QA 梳理 → 文档可视化。Evidence 在 Brief 前按需读取，不单独成为内容生产阶段。默认只在 Analysis 和 Storyline 后暂停；后续自动走到最终真实渲染结果。你可以：

- 回复"继续"，进入下一阶段；
- 直接提出修改意见，Agent 在本阶段修正后重新提交。

提出的反馈会被自动记录为该阶段的经验，后续同类汇报自动参考，无需重复说明。

---

## 第四步：获取最终材料

默认先交付完整 DOCX，其中已包含独立 QA Worker 形成的追问清单。你确认后可以结束任务，也可以选择继续转译为 PPT / HTML。产物与 `render_manifest.json` 位于本次 run 目录中。

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

**为什么 PPT/HTML 文件生成了但没有交付？** 先检查 run 目录中的 `visual_quality_manifest.json`。PPT/DOCX 页面快照依赖 LibreOffice/PDF 渲染，HTML 页面快照依赖 Playwright/Chromium；无法完成真实页面检查时系统会阻止静默交付。

---

> 系统架构与技术细节请参阅 README 与 `docs/汇报助手系统设计方案.md`。
