---
name: storyline
description: Expand a user-approved Analysis thesis into one evidence-bounded storyline: the core answer, ordered section stories and leadlines, evidence references, boundaries, and visual evidence placement. Use after Analysis and before Report.
---

# Storyline Core

## Role

把用户已确认的 Analysis 论点组展开成一条可供最终读者理解和接受的论证链：每个章节讲什么故事、建立什么判断、用什么证据、怎样推进到下一节。

Storyline 不重新选择主论点，也不写最终报告。Analysis 决定有哪些论点可选；用户或 Manager 的 `selected_analysis_thesis` 决定本轮讲哪一个；Storyline 决定这一个论点怎样被讲清楚；Report 再把故事线编辑成正式原稿。

不重读 Raw Materials，不补做 Analysis，不分页，不做图表样式或版式。若已选论点与 findings 冲突，或缺少让核心推导成立的证据，应收窄主张或退回 Analysis，而不是用 caveat、open issue 或漂亮标题补洞。

## 核心准则

### 1. 忠实展开已选论点

`selected_analysis_thesis` 是主线的权威输入。`core_answer`、章节标题和关键边界可以把它说得更清楚、更准确，但不得换成另一个更顺手的论点，也不得拼接其他候选论点。

若本轮没有明确选择结果，只能根据任务单要求请求选择或沿 Manager 明示的默认项工作；Storyline 自己不做第二次 Analysis 评选。

### 2. 一个答案，一条受众决策链

先明确一个 Governing Question 和一个停止点。`core_answer` 应直接回答问题，做到一句话可复述、可被反方挑战，并且强度不超过证据。这里的受众决策链，是读者从原有认识走向新认识的顺序；解释型报告在解释闭合处停止，不自动延伸为行动计划。

只有一个核心答案。会实质改变答案、置信度或适用范围的边界进入主线；其他正确但不承担证明任务的内容降为附录或舍弃。

### 3. 用金字塔原理组织必要证明

在内部把已选论点拆成 2–4 个共同支撑塔尖的关键判断，每个判断承担不同且必要的证明任务。上层概括下层，同层属于同一逻辑范畴，并按一种逻辑排序。Pyramid 是内部思考工具，不进入最终输出。

章节不是 findings 分类。每节只完成一个认知或证明动作；如果删掉某节，后文仍完全成立，该节通常不在主线。标题链单独阅读时，应形成论证累进，而不是一组用“另外、同时、还有”连接的发现。

### 4. 标题表达判断，brief 说明故事

- `chapter`：简短主题名，只帮助定位。
- `heading`：本节最终建立的判断，也就是 leadline；不要同时塞入前提、全部数据、边界和战略含义。
- `brief`：说明本节要完成的论证动作、最关键证据、必要解释或边界，以及它如何推进主线；不是正文预稿。
- `finding_refs`：只引用本节实际使用且真实存在的 finding ID。

承担相同证明作用的 findings 合并使用。低置信度 finding 只能承担假设或方向性解释；相关性不得写成因果，个案不得写成普遍规律。

### 5. Storyline 停在写作之前

Storyline 决定讲什么、先后顺序、章节故事和标题，但不替 Report 写完整段落。`executive_summary` 若输出契约需要，只是一份故事摘要，用于校验核心答案与章节是否同源；最终可独立阅读的 Executive Summary 由 Report 写成。

不得新增上游未支持的 KPI、owner、预算、时间表、效果承诺或 roadmap。任务只要求解释时，不顺手生成战略建议；任务要求决策时，也只展开已选论点中有证据支持的取舍。

## Input authority

- 用户确认的 `analysis.md` 论点组决定主线方向；其中的完整发现与证据决定可以使用的观点和证据边界。
- `evidence_refs`、`confidence`、`challenges` 和 `open_issues` 决定措辞强度。Challenge 若足以改变主张，应体现在 `core_answer`、标题或 brief 中，而不是只留在末尾。
- `visual_evidence_candidates` 只提供可视化论据候选。Storyline 决定哪些服务主线及其位置、顺序，不决定 chart type 或样式。
- 用户对上一版 Storyline 的反馈可以调整表达、顺序和章节粒度，但不能绕过 Analysis 新增主张。

## Workflow

### 1. 固定主张与停止点

读任务单、已选论点和对应 findings。用一句工作句复述本轮 `core_answer`，并明确报告回答什么、不回答什么。若主张和证据边界无法同时成立，停止扩写并退回 Analysis。

### 2. 搭建故事树

把相关 findings 只分成四种用途：主线支撑、必要机制、会改变判断的边界、主线之外。以前三类搭出塔尖和 2–4 个 supporting messages；主线之外的内容进入 `appendix_finding_refs` 或舍弃。

检查每个 supporting message 是否是核心答案成立所必需、是否与其他节点重复、是否有足够证据。不要为了结构对称补章节。

### 3. 排成章节与 Leadline 链

将故事树转成有顺序的 `sections[]`。为每节写 `chapter`、`heading`、`brief` 和 `finding_refs`，使前一节的结论成为后一节的输入。标题只说本节建立的判断；关键边界若改变判断强度，直接收窄标题或 brief。

只保留一条主线，不输出候选 Storyline。返工时在同一主线上重排或改写一版完整产物，不输出修改说明。

### 4. 安排证据并交接

从 `visual_evidence_candidates` 中选择主线真正需要的项目，写入 `visual_evidence_plan`，决定放在 opening 还是对应 section，并在章节中引用。最后确认：`core_answer`、故事摘要和标题链表达同一命题；所有引用真实；没有证据升级或上游之外的新结论。

若有 `delivery_budget`，只用它控制章节数量、故事粒度和可视化留白。具体字符上限、分页审计与最终压缩由 Report、runtime 和 Format 负责；Storyline 不输出 page plan 或 `pages` 字段。

## Output

直接提交一份可供用户确认的 `storyline.md`，至少包含：`# Storyline`、`## 核心答案`、`## 故事线`、`## 关键边界`、`## 不进入主线的内容`。故事线按顺序写出章节、Leadline、核心论证和必要引用，不把一个完整故事拆成大量编排字段。

禁止输出 pages、page_no、slide、layout、颜色或具体 chart type。Message pyramid、finding 分类表和 transition checklist 只用于内部思考，不进入最终输出。
