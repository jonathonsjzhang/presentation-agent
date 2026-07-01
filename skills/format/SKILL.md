---
name: format
description: "[v2] Convert approved page content into a render-ready formal deliverable. Full format skill v1.0 — professional consulting style, data authenticity, presentation specs."
---
# Format Skill v1.0

## Role

把 `page_content.v1` 转为 `formatted_material.v1`。你负责正式表达、信息层级、来源与缺口呈现、renderer handoff、下游交接，**以及具体的呈现形式规则**（typography / color / spacing / chart / table / asset / 载体特有），但不重新做论点、故事线 或逐字稿。

本 Skill 定义三种载体（`format.ppt` / `format.document` / `format.html`）共有的稳定职责，以及各 capability **自带**的呈现形式规则。本轮只能依据 `output_format` **唯一激活**一个 `format.*` capability；不要自行加载或混用其他载体流程。

> **本版关键变更**：v1.0 在 v0.9.1 基础上完成通用化改造，将"腾讯专用"泛化为"通用专业咨询风格"，适用于各行业和各类型企业。同时修复 MckEngine API 参数格式问题，新增完整的 PPT 呈现形式规范（导航系统、发现面板、数据强调、配色方案等）。

## Input readiness

开始前检查：

- 存在 `pages[]` 或 `draft_material.material_units[]`；
- 目标格式已在 report charter 与 active capability 中确定；
- 每个上游单元能追溯 page takeaway、证据、来源和 data gap；
- 需要的原始细节若被投影，应按 `material_refs[].artifact_path` 读取，不能根据 preview 补写事实；
- 呈现形式所需 token（typography / color / chart palette / 资产）已就位或可在 active capability 的呈现形式子节中声明；
- **数据真实性检查**：`visual_object.chart_spec.data_ref` 或 `visual_object.table_data` 中的数据**必须**从原始文档/数据中真实提取，**禁止**使用模拟数据或示例数据。若原始文档中无对应数据，必须在 `gap_display.visible_note` 中声明"数据缺失"，并将 `quality_status` 设为 `partial`。

**数据提取规则**（v0.7 新增）：
1. 所有图表数据（柱数值、折线坐标、表格单元格）必须从 `source_refs[]` 引用的原始文档中提取
2. 提取后应填写 `data_source_extraction` 字段，记录提取位置（如 `filename.pdf §3.2 Table 2`）
3. 若原始文档为 PDF/图片，需使用 OCR 或手动录入，并在 `open_design_tasks` 中记录"需人工核对数据"
4. 发现面板（discovery panel）的洞察要点必须从原始文档的分析/结论部分提取，或由 AI 模型从文档中生成，**禁止**手动编写无依据的洞察

输出 `input_readiness.status = ready | partial | blocked`。输入不完整时可以生成 provisional spec，但必须把缺口写进对应单元和 `open_design_tasks`，不得把 deliverable 标为 completed。

## Stable workflow

1. **激活唯一 capability**：按 `output_format` 与受众/类型组合，从 `## Format capabilities` 选一个 `format.*` capability 激活；记录到 `format_decisions[0]`。同步在 `style_tokens` 中载入该 capability 呈现形式子节定义的 token 值。
2. 审计输入，记录无法保真的内容或 renderer 阻断。
3. 依据唯一 active `format.*` capability 的 layout 库、字段填写手册与**该 capability 内部的呈现形式子节**生成正式单元。
4. 保持每个单元与 `source_page_no`、结论、证据和缺口的映射。
5. 建立 `artifact_manifest`、`render_plan` 与 `quality_checks`；在 `render_plan.asset_requirements[]` 填齐该 capability 呈现形式子节中"模板变量"的资源要求。

## Invariants

- 不改变 core thesis、故事线顺序、结论强度或证据含义。
- 不新增无来源事实，不隐藏 low confidence、caveat 或 blocking gap。
- 每个正式单元只服务一个主要 takeaway，并有明确的信息层级。
- sources、confidence、data gaps 和 open tasks 必须进入正式内容或交付清单。
- Agent 只描述 render intent；`render_result=rendered` 只能由真实 renderer 回填。
- artifact 的 `format` 必须与 compiled `format.*` capability 一致（见 `## Format capabilities`）。
- **呈现形式规则与业务规则冲突时，业务规则优先**（如"未脱敏金额不得展示" > "用品牌色"）。跨载体一致性约束见 `## 跨载体协同`。

## Output contract

严格输出 `formatted_material.v1`，至少包含：

- `agent_id`, `schema`, `topic`, `audience`, `format`
- `input_readiness`
- `artifact_manifest`
- `render_plan`
- `material_units[]`, `appendix_units[]`
- `style_tokens`（**取值由 active capability 呈现形式子节定义**，至少含 typography / color / spacing 三个子集）
- `source_policy`, `gap_policy`, `redaction_policy`
- `format_decisions[]`
- `open_design_tasks[]`
- `downstream_handoff`
- `quality_checks[]`

每个 `material_unit` 至少包含：

- `unit_id`, `source_page_no`, `unit_type`, `headline`
- `layout_or_structure`（**必含 `presentation_style_ref` 引用 active capability 呈现形式子节中的具体 token**）
- `finalized_content`
- `visual_object`
- `source_display`
- `gap_display`
- `quality_status`

载体专属的 unit type、renderer、结构、图表限制和 QA 标准只服从本轮 active format capability（见下）。

---

## Format capabilities

三个 capability **共享**以下 token 骨架与字段规则，再各自定义**专属**设计能力 + **专属**呈现形式规则。

### 能力索引（\_index）

#### 命名空间

```
format.ppt       — 演示稿（≤15 页，强叙事；动画克制；图表用 native shape）
format.document  — 完整报告（多章节，可独立阅读；跨页表格；罗马+阿拉伯页码）
format.html      — 交互网页（可展开、可分享、外发必脱敏；响应式 + 暗色主题）
```

#### 选型规则（按 `output_format` 与受众/类型组合）

| `output_format` | capability        | 触发场景         | 备选（需用户显式 override）        |
| --------------- | ----------------- | ------------ | ------------------------- |
| `ppt`           | `format.ppt`      | 默认演示场景       | `format.html`（若受众需会后回看）   |
| `document`      | `format.document` | 默认存档 / 决策汇报  | `format.html`（若受众需链接分享）   |
| `html`          | `format.html`     | 默认外部分享 / 移动端 | `format.document`（若需打印归档） |

#### 激活约束

- 一次 report run 只能激活一个 `format.*` capability
- `artifact_manifest.target_format`、`render_plan.renderer`、各 `material_unit.unit_type`、active capability 的 layout 库 **四者必须同源**
- 多载体需求 → 拆为多次 report run；不允许多载体混编
- 呈现形式 token 一旦由 `format_handoff_notes` 指定（如 `brand_color_primary`），active capability 内部**所有**引用主色的位置同步切换

### 共享规范（三 capability 一致）

#### 跨载体通用字段填写规则

| 字段                                           | 规则                                                                                       |
| -------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `headline`                                   | ≤ 18 汉字 / 14 英文单词；名词短语或 so-what 句；保留 `page_takeaway` 的结论强度，不升级                           |
| `layout_or_structure.layout_type`            | 必须从 active capability 的合法 layout 库中选                                                     |
| `layout_or_structure.presentation_style_ref` | 必填，引用 active capability 呈现形式子节中的具体 token（如 `format.ppt §typography.h1`）                  |
| `finalized_content.primary_text`             | 1 句话承载 takeaway；≤ 32 汉字 / 25 英文单词；含数据时挂 `source_note`                                    |
| `finalized_content.supporting_points`        | 1–3 条；每条 ≤ 24 汉字 / 18 英文单词；按结论→证据→行动序                                                    |
| `finalized_content.callouts`                 | 触发：反直觉 / 高敏感 / 受众分歧 / 数据待确认；最多 1 条                                                       |
| `finalized_content.quote_blocks`             | 触发：直接引用用户/客户/法规原文；需带 `attribution`                                                       |
| `source_display.footer`                      | 形如 `来源：[1][2] 置信度：中`；不展开论证                                                               |
| `source_display.inline_sources[]`            | 形如 `[1] filename.pdf §3.2`；引用 id 与 `appendix_units[]` 中 `appendix_unit.source_refs[]` 一致 |
| `source_display.confidence_note`             | 必填 `高/中/低` + 一句 ≤ 20 字的理由                                                                |
| `gap_display.visible_note`                   | 单元内可见缺口（数据缺失 / 待确认 / 假设）最多 1 条；≤ 24 汉字                                                   |
| `gap_display.hidden_internal_note`           | 仅给 QA 看的内部备注；不出现在受众视野                                                                    |
| `quality_status`                             | `complete` / `partial` / `blocked`；非 `complete` 时 `open_design_tasks` 必有对应条目             |

#### 共享 token 骨架（**名字与含义统一，量化值由各 capability 给出**）

> 为什么要把"token 名字"放共享、"token 量化值"放各 capability？因为三载体的 token 名字语义相同（`color.brand.primary` 在三载体下都指"品牌主色"），但**量化值**不同（PPT 用 pt、Document 用 pt、HTML 用 px；PPT 强调字号大、HTML 强调相对单位）。共享 token 名字保证跨载体一致性，量化值差异化反映载体物理差异。

| Token                                              | 含义                               |
| -------------------------------------------------- | -------------------------------- |
| `font.family.sans`                                 | 无衬线（默认）                          |
| `font.family.serif`                                | 衬线（报告场景）                         |
| `font.family.mono`                                 | 等宽（数据 / 代码）                      |
| `font.size.{title,h1,h2,h3,body,caption,footnote}` | 7 档字号（按视觉等效）                     |
| `line.height.{tight,normal,relaxed}`               | 3 档行距                            |
| `weight.{bold,medium,regular}`                     | 3 档字重                            |
| `color.brand.{primary,secondary,three_way[]}`      | 品牌主色 / 辅色 / **3 方对比色板**（PPT 强需求） |
| `color.neutral.{900,700,500,300,100}`              | 5 档中性灰（文字层级）                     |
| `color.surface.{bg,panel,panel_tint,divider}`      | 4 档背景色（含"浅蓝面板"用于主结论高亮）           |
| `color.accent.{success,warning,danger,info}`       | 4 档语义强调色                         |
| `color.callout.{box_bg,box_border}`                | callout 框底 / 框边                  |
| `color.bracket.stroke`                             | 大括号 `}` 注释线色（McKinsey 风格）        |
| `color.ellipse.stroke`                             | 虚线椭圆色（产品分组圈选）                    |
| `color.chart.{palette[],highlight}`                | 图表色板 + 单一强调点色                    |
| `space.{xs,sm,md,lg,xl,2xl}`                       | 6 档间距（按视觉等效）                     |
| `grid.{columns,gutter,margin,safe_area}`           | 栏 / 栏距 / 页边距 / 安全区               |

#### 跨载体通用渲染前置检查

- `input_readiness.status != blocked` 才进入 render plan
- 缺数据图表 → 改用安全版式 + 写 `open_design_tasks`，**不得伪造 completed**
- 高风险页 → 配套 `appendix_units[]` 备份页
- `format_handoff_notes` 必含模板/字体/分辨率等资产要求（见各 capability 呈现形式子节中的"模板变量"）

#### 跨载体失败处置（继承 Failure conditions 并补充）

- artifact 格式与 active capability 冲突 → abort + 重选 capability；不进入 render
- 为排版修改或删除上游结论 → 回退到 page_content；写 `open_design_tasks`
- 丢失来源/口径/关键限定/阻断缺口 → 补 `source_display` / `gap_display`；降级 `quality_status`
- 只有格式建议无正式材料单元 → 重新生成 `material_units[]`，禁止空跑
- 未真实渲染却声称 completed → 删除 `render_result` 字段；改 `artifact_manifest.render_status=drafted`
- 同一产物混入两种或三种载体结构 → 锁定单 capability；多载体走多次 report run

---

### `format.ppt` capability

#### 能力边界

- **能做**：8–12 页（不超过 15 页）演示稿；每页一个 takeaway；图表用 native shape 渲染；动画克制。
- **不能做**：长篇论证、跨页细读、脚注密集引用、供会后反复翻阅的存档版本。

#### layout 库（10 个 `layout_type`）

| `layout_type`       | 适用单元         | `hierarchy_map` 必含                                    | 触发            |
| ------------------- | ------------ | ----------------------------------------------------- | ------------- |
| `title_slide`       | slide（cover） | `topic`, `subtitle`                                   | 仅第 1 页        |
| `executive_summary` | slide        | `primary` (1 句结论), `supporting` (≤3)                  | **必在 page 2（封面后一页）**，作为后续 slides 的核心观点总结 |
| `action_title`      | slide（默认）    | `action_title` (1 句结论), `supporting` (1–2)            | 大多数内容页        |
| `key_takeaway`      | slide        | `takeaway` (1 句), `evidence` (1)                      | 总结性单点页        |
| `pyramid`           | slide        | `top` (结论), `layers` (3–4)                            | 结构性框架         |
| `matrix_2x2`        | slide        | `quadrants[]` (4)                                     | 战略定位 / 分类     |
| `funnel`            | slide        | `stages[]` (3–5)                                      | 漏斗转化          |
| `waterfall`         | slide        | `start`, `deltas[]`, `end`                            | 数值分解          |
| `bar_chart`         | slide        | `chart_spec`                                          | 横向比较          |
| `line_chart`        | slide        | `chart_spec`                                          | 时间序列          |

> **禁止类型**：`目录页`（directory page）和 `章节分隔页`（section divider page）**不在**本 layout 库中，format worker **不得生成**这两类页面。报告靠叙事流和发现面板的"发现"文字来引导读者，不需要独立目录页或章节分隔页。

#### 字段填写规则（PPT 特化）

- `unit_type = "slide"`（强一致；每张 slide 一单元）
- `layout_or_structure.layout_type` 必填，从上表 10 个选
- `layout_or_structure.reading_order` 数组顺序：标题 → 主体 → 来源脚注
- `visual_object`：
  - 数据页：必填 `chart_spec`（含 `chart_type`, `data_ref`, `axes`, `annotations[]`）
  - 框架页：可选 `mck_api.template`（如 `pyramid_v2`、`matrix_2x2_v1`）
  - 无视觉对象时：`visual_object = null`，但 `layout_type` 必须是非数据 layout
- `format_handoff_notes`（顶层 + 单元级）：必备 `font_family`、`master_template`、`aspect_ratio`（见下方"PPT 呈现形式 / 模板变量"）

#### renderer handoff 契约

- `render_plan.renderer = "mck_ppt_shape_native"`
- `deliverables[0]` = `{ "name": "<topic>.pptx", "format": "pptx", "renderer": "mck_ppt_shape_native" }`
- `asset_requirements[]` 至少含 `master_template`、`font_family`、所有 `chart_spec` 所需数据
- 高风险页必须列入 `manual_steps[]` 并配套 `appendix_units[]` 备份页
- `quality_checks` 必含 `FMT-FM-PPT-RENDER-READY-001`：所有 slide 单元 `layout_type` 非空 + `chart_spec` 数据可解析

---

#### PPT 呈现形式规则（format.ppt 专属，基于 `20251208_AI产品用户留存洞察_vS.pdf` 23 页实际案例提炼）

> 本节所有规范**均来自 vS.pdf 的实际页面逐像素分析**，而非 McKinsey 培训 PPT 的通用理论。vS.pdf 是腾讯内部咨询级汇报的标准参考，其呈现规则代表了 format worker 输出 `formatted_material.v1` 时应遵循的**唯一视觉标准**。
>
> 与 `format.document` / `format.html` 在字号单位、动画、密度、图表类型上有本质差异。本节覆盖 vS.pdf 中实际使用的 **13 种版式类型 × 6 类图表 × 11 档字号 × 完整配色系统 × 固定页面元素规范**。

---

##### 7.1 页面类型与版式规范（13 种，均从 vS.pdf 实际页面归纳）

> 每个 `material_unit` 的 `layout_type` 必须为以下之一。每种给出：触发场景、布局结构、背景、内容规范。
>
> **⛔ 禁止页面类型**：`目录页`（directory page）和 `章节分隔页`（section divider page）**不得生成**。报告靠叙事流和发现面板的"发现"文字引导读者，不需要独立目录页或章节分隔页。

| # | `layout_type` | 中文名 | vS 页码 | 触发场景 |
|---|---|---|---|---|
| 1 | `cover_title` | 封面页 | P1 | 报告首页，展示标题+日期+品牌 |
| 2 | `executive_summary` | 核心发现/执行摘要 | **P2（封面后一页）** | **必在封面后一页**，3-5个核心发现的概览，作为后续 slides 的核心观点总结 |
| 3 | `methodology_context` | 方法论/背景说明 | P3 | 解释数据来源、方法论、定义关键概念 |
| 4 | `credibility_check` | 可信性检验/数据校验 | P4 | 验证数据可信度（分布检验/一致性检查） |
| 5 | `kpi_dashboard` | 数据概览/KPI仪表盘 | P5 | 展示核心指标总览（强留存率/样本量等） |
| 6 | `chart_with_panel` | 图表+发现面板 ⭐最常用 | P6,P10,P15,P17-P19,P22 | **标准内容页**：一个主图表 + 右侧发现要点面板 |
| 7 | `table_chart_hybrid` | 表格+图表混合 | P7,P8 | 数据表格 + 配套柱状图的组合展示 |
| 8 | `multi_bar_comparison` | 多柱对比图 | P9 | 三品牌（元宝/DS/豆包）在某维度上的横向对比 |
| 9 | `timeline_distribution` | 时间/分布图 | P9(下半) | 用户时间分布/占比分布的条形图 |
| 10 | `strategy_roadmap` | 策略路线表 | P12 | 场景×功能×资源的矩阵式路线规划 |
| 11 | `user_voice_quote` | 用户原声/引用 | P13 | 嵌入用户访谈原声 + 对应数据佐证 |
| 12 | `conversion_funnel` | 转化/迁移矩阵 | P14 | 用户迁移路径/转化效率的多维对比 |
| 13 | `discussion_action` | 讨论/行动建议 | P23 | 报告末页，Exploit/Explore 分类的行动建议 |

---

###### 7.1.1 `cover_title` 封面页

**vS 参考页**: P1

```
┌──────────────────────────────────────────────────┐
│  ████████████████████████████████ Tencent        │
│  █                                   （抽象曲线纹理）    │
│  █                                                   │
│  █   元宝/DS/豆包用户留存洞察                          │  ← 白色 36-40pt Light
│  █                                                   │
│  █                                       2025/12/08  │  ← 白色 14pt 左下
│  ████████████████████████████████████████████████   │
└──────────────────────────────────────────────────┘
```

| 参数 | 规范值 |
|---|---|
| 背景 | 深蓝渐变 `#0052CC → #003D82`（或纯 `#0066CC`），可叠加抽象曲线纹理 |
| 主标题 | 白色 (`#FFFFFF`)，36-40pt，Light 或 Regular 字重，左偏居中位置 |
| 副标题 | 如有，白色 16-18pt Regular，位于主标题下方 |
| 日期 | 白色 14pt，位于左下角 (距左边距 ~80px, 距底边 ~60px) |
| Logo | "Tencent" 文字 logo（白色），右上角 (距右边距 ~60px, 距顶边 ~30px) |
| 字体 | 微软雅黑 |

---

###### 7.1.2 `executive_summary` 核心发现页

**vS 参考页**: P2

```
┌──────────────────────────────────────────────────┐
│                                    Tencent       │
│                                                  │
│  核心发现                                         │  ← 黑色 22-24pt Bold
│                                                  │
│  ┌────────────────────────────────────────────┐   │
│  │ 发现1：纯白用户价值高但新增难度大...        │   │  ← 浅灰面板 #F5F5F5
│  │ − 发现1.1：打"功能纯白"是更可行的路径...   │   │     内边距 16px
│  │ − 发现1.2：在非纯白用户中...               │   │
│  │                                            │   │
│  │ 发现2：模型仍是根基...                      │   │  ← 蓝色粗体 14-16pt
│  │                                            │   │
│  │ 发现3：召回手段仍在早期...                  │   │
│  └────────────────────────────────────────────┘   │
│                                                  │
│                                              2   │  ← 页码右下
└──────────────────────────────────────────────────┘
```

| 参数 | 规范值 |
|---|---|
| 背景 | 纯白 `#FFFFFF` |
| 标题 | `#212121`，22-24pt Bold，左上对齐 |
| 内容区 | 浅灰面板 `#F5F5F5` 背景，圆角 0-2px，内边距 16-20px |
| 发现标题 | `#1E6FE0`（品牌蓝），14-16pt Bold，如 "发现1：" |
| 子发现缩进 | "− " 开头，缩进 20px，12-13pt Regular，`#333333` |
| 发现数量 | 建议 3-5 个，每个含 0-3 个子发现 |
| Logo | 蓝色 Tencent logo，右上角 |
| 页码 | `#888888` 9pt，右下角 |

---

###### 7.1.3 `chart_with_panel` 图表+发现面板 ⭐ **标准内容页模板**

**vS 参考页**: P6, P10, P15, P17, P18, P19, P22（出现频率最高）

```
┌──────────────────────────────────────────────────┐
│ 人群  纯白  非纯白  文本  功能  运营              │  ← 导航栏: #003D82 底, 白字 11pt
├──────────────────────────────────────────────────┤
│                                    Tencent       │
│                                                  │
│ 发现1：纯白用户强留存显著高于非纯白，             │  ← #1E6FE0 20-22pt Bold
│ 对元宝和DS的拉动更大                              │
│                                                  │
│ ┌─────────────────────────┬ ┌──────────────────┐ │
│ │                         │ │ 发现             │ │
│ │    [Chart Area]         │ │                  │ │  ← 左 60-65% : 右 35-40%
│ │                         │ │ • 要点1          │ │     图表区           : 灰色面板 #F5F5F5
│ │                         │ │ • 要点2          │ │                       内边距 12-16px
│ │                         │ │ • 要点3          │ │
│ │                         │ │                  │ │
│ └─────────────────────────┘ └──────────────────┘ │
│ 来源: 注1: ...                                    │  ← #888888 8-9pt
│                                              6   │  ← 页码
└──────────────────────────────────────────────────┘
```

| 参数 | 规范值 |
|---|---|
| **导航栏** | 见 §7.2.5 |
| 主标题 | `#1E6FE0`，20-22pt Bold，左上对齐（导航栏下方 16-20px） |
| **左图表区** | 占宽 60-65%，高度自适应 |
| **右发现面板** | 见 §7.3 |
| **来源脚注** | 见 §7.2.3 |
| **页码** | 见 §7.2.2 |

> **这是 vS.pdf 中使用频率最高的版式**（7/23 页）。绝大多数数据分析页都采用此布局。format worker 在输出 `material_unit` 时，**默认应优先选择 `chart_with_panel` 作为内容页的 layout_type**。

---

###### 7.1.4 `table_chart_hybrid` 表格+图表混合

**vS 参考页**: P7, P8

```
┌──────────────────────────────────────────────────┐
│ [导航栏]                                         │
├──────────────────────────────────────────────────┤
│ [Tencent logo]                                   │
│                                                  │
│ 人群：元宝和豆包纯白用户更下沉...                   │  ← 蓝色标题 20-22pt
│                                                  │
│ ┌──────────────────┬────────┬ ┌────────────────┐ │
│ │                  │        │ │ 发现            │ │
│ │  [Data Table]    │[Bar]   │ │                │ │  ← 三栏布局:
│ │  (红框高亮关键格) │ Chart  │ │  Discovery     │ │     表格 45% + 柱状 20% + 面板 35%
│ │                  │        │ │  Panel         │ │
│ └──────────────────┴────────┘ └────────────────┘ │
│ □ 代表纯白用户...                                 │  ← legend + source
│                                              8   │
└──────────────────────────────────────────────────┘
```

| 参数 | 规范值 |
|---|---|
| 导航栏 + 标题 | 同 `chart_with_panel` |
| 表格区域 | 占宽 40-50%，见 §7.7 表格规范 |
| 图表区域 | 占宽 15-25%，紧贴表格右侧，通常为横向柱状对比 |
| 高亮方式 | 关键数据格用红框 (`#D32F2F`, 2px solid) 圈出 |
| Legend | 表格下方一行，解释颜色编码含义 |

---

###### 7.1.5 `multi_bar_comparison` 多柱对比图

**vS 参考页**: P9

| 参数 | 规范值 |
|---|---|
| 导航栏 + 标题 | 同 `chart_with_panel` |
| 布局 | 三列水平条形图，每列对应一品牌（元宝绿/DS蓝/豆包浅蓝） |
| 数据标签 | 数值在条末端；统计不显著时显示灰色 "不显著" 替代条形 |
| 辅助信息 | 每列下方显示样本量和占比（灰色椭圆框内） |
| 发现面板 | 同标准模板 |

---

###### 7.1.6 其他版式类型的简要规范

| layout_type | 核心特征摘要 | 详细参数提示 |
|---|---|---|
| `methodology_context` | 无导航栏；标题+正文+浅蓝 callout 框并排；可嵌入截图 | callout 框: `#E8F0FA` 背景, 14pt bold 居中文字 |
| `credibility_check` | 灰色表头栏；三行横向对比(标签+三元宝柱)；右侧竖向注释；多行编号脚注 | 表头: `#EEEEEE` bg; 注释字号: 10pt; 脚注格式: "注1: ...; 注2: ..." |
| `kpi_dashboard` | 无/极简导航栏；双表格并列（KPI指标表 + 因素框架表）；KPI含品牌icon+柱+数值 | KPI数字: 24-28pt bold; 百分比: 18-20pt |
| `timeline_distribution` | 三品牌水平堆叠条；时间段用同色系深浅区分；百分比在条内/末端 | 同 `multi_bar_comparison` 的配色和标注风格 |
| `strategy_roadmap` | 大型表格: 受众分层(左蓝标签)→场景→已有功能→计划功能→资源支持；两侧竖向注释箭头+规模数字 | 左侧标签: 蓝底白字; 资源列: 缩进 bullet 列表 |
| `user_voice_quote` | 左: 品牌组合图标+柱状(红框重点)+留存率; 右: 引用框(灰底/手撕边)含原话+画像 | 引用文字: 12pt regular; 画像: 9pt gray "—女/27/杭州/跨境电商" |
| `conversion_funnel` | 上: 组合留存率柱状对比; 下: 单/双/三栖行为分布; 转化效率百分比标注 | 转化效率用蓝色粗体标注在对应柱旁 |
| `discussion_action` | 无导航栏；编号深蓝圆圈(1,2)+蓝色标签方块("Exploit"/"Explore")+详细行动bullet | 编号圆圈: 直径28px, #0066CC填充, 白字14pt bold; 标签块: #0066CC填充, 白字16pt bold |

---

##### 7.2 固定页面元素规范（每页必须包含）

> 以下元素构成 vS 风格的"页面DNA"。除明确标注"不适用"的版式外，其余版式**必须包含**这些元素。

###### 7.2.1 Tencent Logo

| 属性 | 规范 |
|---|---|
| 位置 | 每页右上角（距右边距 ~60px, 距顶边 ~25-30px） |
| 有色背景页（封面/导航栏内） | 白色 "Tencent" 文字 logo |
| 白色背景页 | 蓝色 `#0066CC` 或 `#1E6FE0` "Tencent" 文字 logo |
| 尺寸 | 约 100px × 24px（宽度 × 高度） |
| 字体 | Tencent Brand Sans / Segoe UI Bold |

###### 7.2.2 页码

| 属性 | 规范 |
|---|---|
| 位置 | 每页右下角（距右边距 ~50px, 距底边 ~30px） |
| 格式 | 阿拉伯数字（如 "6"、"23"） |
| 字号 | 9pt |
| 颜色 | `#888888` (`color.text.muted`) |
| **不适用** | 封面页 (`cover_title`) 通常不显示页码 |

###### 7.2.3 来源/脚注 (Source Notes)

| 属性 | 规范 |
|---|---|
| 位置 | 页面底部偏左（距左边距 ~60px, 距底边 ~25-35px） |
| 字号 | 8-9pt |
| 颜色 | `#888888` (`color.text.muted`) |
| 格式 | 编号形式 `"注1：描述；注2：描述..."` |
| 内容要求 | 数据来源说明、方法论注脚、样本量声明、口径差异解释 |
| **不适用** | 封面页、核心发现页(P2)、讨论行动页(P23)可能无脚注 |

###### 7.2.4 保密标签 (Confidential Tag)

| 属性 | 规范 |
|---|---|
| 位置 | 标题区右下方（logo 下方，距右边距 ~60px） |
| 文字 | "内部汇报 · 仅供参考" |
| 字号 | 9pt |
| 颜色 | `#999999` |
| **适用范围** | 内容页 (P4-P22)；封面和讨论页可选 |

###### 7.2.5 导航标题栏 (Navigation Title Bar) ⭐ **vS 最具辨识度的元素**

| 属性 | 规范 |
|---|---|
| 位置 | 内容页**最顶部**，全宽 |
| 高度 | 28-32px |
| 背景色 | `#003D82` (`color.nav.bar`) 深海军蓝 |
| 内容 | 白色文字 tabs，空格分隔 |
| Tab 字号 | 11pt Regular |
| Tab 示例 | `"人群  纯白  非纯白  文本  功能  运营"` |
| 当前 tab 高亮 | 白色小矩形背景 + 深蓝文字（反转色），圆角 2-3px |
| 非当前 tab | 白色文字，无背景 |
| **适用范围** | `chart_with_panel` / `table_chart_hybrid` / `multi_bar_comparison` / `timeline_distribution` / `strategy_roadmap` / `user_voice_quote` / `conversion_funnel` |
| **不适用** | `cover_title` / `executive_summary` / `methodology_context` / `credibility_check` / `kpi_dashboard` / `discussion_action` |

> **设计意图**：导航栏告诉读者"当前页面属于哪个分析维度"，在长达 20+ 页的数据分析报告中起到**全局定位**作用。tabs 应与报告的分析框架一一对应。

---

##### 7.3 发现面板 (Discovery Panel) 规范 ⭐ **vS 标准内容页标配**

> 发现面板是 vS 风格的核心组件。它将"数据是什么"（左图表区）和"所以呢"（右面板区）分离在同一视图中，实现 **Data → Insight** 的一站式传达。

| 属性 | 规范 |
|---|---|
| 位置 | 内容页右侧 |
| 宽度占比 | 30%-40%（约 280-340px @ 16:9 画布） |
| 背景色 | `#F5F5F5` (`color.panel.bg`) 浅灰 |
| 边框 | 无外框，或极细 `#E0E0E0` 线 (0.5pt) |
| 圆角 | 0-2px（极微妙，几乎不可见） |
| 内边距 | 上下左右各 12-16px |
| 标题文字 | "发现"，14pt Bold，`#212121` |
| 要点格式 | `• ` 开头，12-13pt Regular，`#333333`，行距 1.4x |
| 要点数量 | 2-4 条（建议不超过 4 条） |
| 标题到首条间距 | 8-10px |
| 条目间距 | 6-8px |
| **适用版式** | `chart_with_panel` / `table_chart_hybrid` / `multi_bar_comparison` / `timeline_distribution` |
| **不适用** | `cover_title` / `executive_summary` / `methodology_context` / `credibility_check` / `kpi_dashboard` / `discussion_action` / `strategy_roadmap` / `user_voice_quote` |

**内容撰写原则**：
- 每条要点必须是**从左侧图表直接得出的结论**，不能引入外部信息
- 使用"比""高于""低于""显著""不显著"等**比较性语言**
- 避免重复图表中的数字——面板的作用是**解读**不是**复述**
- 如果某条发现跨页成立（如"纯白用户留存更好"），可以适当引用其他页面的数据

---

##### 7.4 配色系统（从 vS.pdf 逐页提取的实际色值）

> 以下颜色全部来自 vS.pdf 的实际像素采样。这是 format worker 输出 `style_tokens` 时的**权威色板**。

###### 7.4.1 品牌三方对比色板（核心）

| Token 名 | 色值 | RGB | 用途 |
|---|---|---|---|
| `color.brand.yuanbao` | **`#3FBF6F`** | (63, 191, 111) | 元宝的数据点/柱/线/标注/正面向指标 |
| `color.brand.ds` | **`#1E6FE0`** | (30, 111, 224) | DS的数据点/柱/线/标注/主标题色/品牌标识 |
| `color.brand.doubao` | **`#BBD8F8`** | (187, 216, 248) | 豆包的数据点/柱/线/标注 |

> **使用原则**：任何涉及三方对比的场景（图表/表格/指标卡），**严格按此色板分配颜色**，不得混用或自创颜色。元宝=绿、DS=蓝、豆包=浅蓝，在全报告中保持一致。

###### 7.4.2 结构功能色

| Token 名 | 色值 | RGB | 用途 |
|---|---|---|---|
| `color.brand.primary` | **`#0066CC`** | (0, 102, 204) | 主操作色（白底页的 logo/链接）、按钮默认态 |
| `color.nav.bar` | **`#003D82`** | (0, 61, 130) | 导航标题栏背景色 |
| `color.panel.bg` | **`#F5F5F5`** | (245, 245, 245) | 发现面板 / 引用框 / 总结面板背景 |
| `color.panel.callout` | **`#E8F0FA`** | (232, 240, 250) | 概念定义 callout 框背景（浅蓝） |
| `color.panel.callout_green` | **`#C8E6C9`** | (200, 230, 201) | 强调型 callout 框背景（浅绿，慎用） |
| `color.accent.red` | **`#D32F2F`** | (211, 47, 47) | 表格红框高亮 / 负面指标 / 警告 |
| `color.accent.positive` | **`#3FBF6F`** | (63, 191, 111) | 正向指标 / 增长标注（与 yuanbao 复用） |

###### 7.4.3 文字色

| Token 名 | 色值 | 用途 |
|---|---|---|
| `color.text.title` | **`#212121`** | Section header（核心发现/总结发现/供讨论）、封面外的主标题 |
| `color.text.page_title` | **`#1E6FE0`** | 内容页蓝色大标题（"发现1：..."、"人群：..."） |
| `color.text.subheading` | **`#1E6FE0`** | 子标题（"发现1"、"发现1.1"、"发现2"、"发现3"蓝色粗体） |
| `color.text.body` | **`#333333`** | 正文、bullet point 文字 |
| `color.text.body_bold` | **`#212121`** | 需要强调的粗体正文 |
| `color.text.muted` | **`#888888`** | 脚注、页码、来源注释、保密标签、"不显著"标记 |
| `color.text.white` | **`#FFFFFF`** | 封面文字、导航栏内文字、有色背景上的文字 |
| `color.text.table_header` | **`#212121`** | 表头文字（加粗） |
| `color.text.table_cell` | **`#333333`** | 表格单元格常规文字 |

###### 7.4.4 背景/中性色

| Token 名 | 色值 | 用途 |
|---|---|---|
| `color.bg.cover` | **`#0052CC`** → 渐变至 **`#003D82`** | 封面页背景（可叠加抽象曲线纹理图案） |
| `color.bg.white` | **`#FFFFFF`** | 绝大多数页面背景 |
| `color.bg.table_header` | **`#EEEEEE`** | 表头行背景 |
| `color.bg.table_alt` | **`#FAFAFA`** | 表格交替行背景（如有斑马纹需求时使用） |
| `color.line.grid` | **`#E0E0E0`** | 表格边框、坐标轴线、网格线 |
| `color.line.dashed` | **`#BDBDBD`** (或 `#AAAAAA`) | 虚线椭圆分组线、0pp 参考基线、分隔虚线 |

###### 7.4.5 配色使用规则

1. **对比度最低标准**: 正文与背景对比度 ≥ 4.5:1（WCAG AA）
2. **三方色板不可更改**: 元宝绿/DS蓝/豆包浅蓝的组合在全 report 中锁定不变
3. **红色仅用于强调**: 红框高亮每页 ≤ 3-4 个格；避免大红色块（除非是警告/负面结论）
4. **callout 框慎用绿色**: 绿色 callout 框仅在需要**极度强调**某个正向发现时使用（vS 中仅 P6 的 "+14pp/+18pp" 标注框用了绿色）
5. **同一维度内颜色一致**: 如"学历"在所有涉及人口属性的页面中使用相同的行高亮色

---

##### 7.5 字号体系（11 档，从 vS.pdf 逐页提取）

| 层级 | 字号 | 字重 | 颜色 token | 典型用途 |
|---|---|---|---|---|
| **L0** 封面标题 | **36-40pt** | Light / Regular | `text.white` | 封面主标题（P1） |
| **L1** Section Header | **22-24pt** | Bold | `text.title` | "核心发现"、"总结发现"、"供讨论"、板块分隔标题 |
| **L2** 页面主标题 | **20-22pt** | Bold | `text.page_title` | "发现1：纯白用户强留存显著高于非纯白..."、各内容页的大标题 |
| **L3** 导航 Tab | **11pt** | Regular | `text.white` | 导航栏内的标签文字 |
| **L4** 发现子标题 | **14-16pt** | Bold | `text.subheading` | "发现1"、"发现1.1"、"发现2"、"发现3"——蓝色粗体 |
| **L5** Callout 框标题 | **13-14pt** | Bold | `text.body_bold` | callout 概念框内的标题文字 |
| **L6** 正文 | **12-13pt** | Regular | `text.body` | 描述性文字、bullet points、表格内说明文字 |
| **L7** 图表标注 | **13-15pt** | Bold | `text.page_title` | "+10pp"、"+18pp"、"+5p" 等数据提升标注 |
| **L8** 表头 | **10-11pt** | Bold | `text.table_header` | 表格列头文字 |
| **L9** 表格单元格 | **10-11pt** | Regular | `text.table_cell` | 表格内的数据和分类名 |
| **L10** 脚注/页码 | **8-9pt** | Regular | `text.muted` | 来源注释、页码、保密标签、legend 小字 |

**字号使用原则**：
- 同一层级的文字在整个 report 中保持**一致**（如所有 L2 标题都是 22pt Bold 蓝色）
- 正文行距 = 1.3-1.5 × 字号（中文排版需更大行距以保证可读性）
- 图表坐标轴标签 = L9 (10-11pt)
- 图例文字 = L8-L9 (10-11pt)
- 引用文字（用户原声）= L6 (12pt)，可用轻微斜体或不斜体

---

##### 7.6 图表类型与规范（全面图表库）

> 本节给出**完整图表类型库**。format worker 根据数据形态自由选用，**不受 vS.pdf 实际使用的 6 类限制**。先查 §7.6.0 决策表选定图表类型，再按对应小节执行详细规范。
> 
> vS.pdf 的图表仅作为**案例参考**，不代表类型上限。当数据形态匹配时，可选用本节省任何图表类型。

###### 7.6.0 图表类型决策表

| 数据形态 | 首选图表 `chart_type` | 备选 | 说明 |
|---|---|---|---|
| 类别 vs 数值（对比） | `bar_horizontal` | `bar_vertical` | 横向便于读标签，默认首选 |
| 时间序列（趋势） | `line` | `area` | ≤ 12 时间点 |
| 部分-整体（≤5 块） | `bar_stacked_100` | `pie`（慎用） | 饼图仅 ≤ 5 块 |
| 部分-整体（>5 块） | `bar_stacked_100` | `treemap` | |
| 两维分布（x vs y） | `scatter` | `bubble`（加 z 维） | |
| 三维（x+y+z） | `bubble` | `scatter`（分面） | z = 气泡大小 |
| 流程转化（逐级递减） | `funnel` | `sankey` | |
| 数值分解（起始→环节→终点） | `waterfall` | `bridge` | |
| 层级/结构框架 | `pyramid` | `tree` | |
| 矩阵定位（两维分类） | `heatmap` | `scatter_quadrant` | |
| 高亮配对比较 | `lollipop` | `bar_horizontal` | |
| KPI/指标总览 | `kpi_card` | `gauge` | |
| 结构化多维数据 | `table` | `table_chart_hybrid` | |
| 时间线/分布 | `timeline_bar` | `distribution` | |
| 双轴（柱+线，两套量纲） | `combo` | — | |

> **使用说明**：format worker 先根据本表选定 `chart_type`，再查阅 §7.6.1–§7.6.14 的对应详细规范。vS.pdf 中实际使用的 6 类图表已融入本决策表和相关小节，作为具体案例参考，但不构成类型上限。

###### 7.6.1 棒棒糖/散点混合图 (Lollipop-Scatter Hybrid)

**vS 参考页**: P6, P17, P18, P19

| 属性 | 规范 |
|---|---|
| **触发场景** | 对比两组人群在同一维度上的留存差异（纯白 vs 非纯白 / 功能纯白 vs 非功能纯白 / 满意度5分 vs 非5分） |
| **Y轴** | 强留存率 (%)，范围 0%-75%（或根据数据动态调整） |
| **X轴** | 强留存提升 (pp)，范围随数据调整 |
| **数据点 marker** | 元宝: 绿色实心圆 ● (`#3FBF6F`); DS: 蓝色自定义图标(鲸鱼/海豚); 豆包: 浅蓝实心圆 ● (`#BBD8F8`) |
| **配对连线** | 两组之间的垂直细实线（`#CCCCCC`, 0.75pt） |
| **提升标注** | 较高点上方标注 "+Xpp"（品牌色 Bold 13-15pt），如 "+10pp"、"+18pp" |
| **Callout 标签框** | 关键发现处添加绿色/蓝色圆角矩形标注框（如 "元宝纯白用户强留存率"） |
| **0pp 参考线** | 水平灰色虚线（`color.line.dashed`），标示"无差异"基线 |
| **Legend** | 图表区域内左上角或上方，marker icon + 文字标签 |
| **坐标轴** | 轴线 `color.line.grid`; 轴标签 `text.table_cell` (10-11pt); 轴标题 `text.subheading` (12-13pt Bold) |

**vS 特色细节**:
- P6 中 DS 用了**鲸鱼/海豚形状的自定义 icon**（非常独特，但 format worker 默认用圆形即可，有条件时可用自定义 shape）
- Callout 框用**浅绿背景** (`#C8E6C9`) 来突出最重要的发现
- 配对连线让读者一眼看出"纯白 vs 非纯白"的差异方向和幅度

###### 7.6.2 象限分组散点图 (Quadrant Grouped Scatter)

**vS 参考页**: P10, P15, P22（**vS 最具特色的图表类型**）

| 属性 | 规范 |
|---|---|
| **触发场景** | 多维度因素对留存的影响分布，按品牌分组观察聚类模式 |
| **Y轴** | 强留存率 (%), X轴: 强留存提升 (pp) |
| **数据点标注** | 每个点标注因素名称+"5分"（如"可靠性5分"、"深度思考5分"），10-11pt |
| **分组椭圆** | 每个品牌的聚类用**虚线椭圆**包围：元宝绿虚线 / DS蓝虚线 / 豆包浅蓝虚线（`color.line.dashed`, 1pt） |
| **Marker 形状区分** | 不同类别用不同 marker：● 产品纯白 / ▲ 功能纯白 / ◆ 文本满意度 ■ 功能满意度 □ 其他 |
| **Legend** | 左上角，列出所有 marker 形状及其含义 |
| **品牌 icon** | 各组椭圆附近放置品牌 icon（元宝● / DS🐋 / 豆包●）作为分组标识 |
| **特点** | 信息密度极高，一张图容纳 15-25 个数据点 + 3 个分组 + 多维分类 |

**vS 特色细节**:
- P22 (总结发现页) 的象限图**整合了全报告的所有发现**，是整个 deck 的"全景图"
- 虚线椭圆的手绘感（不完全规则的椭圆形）增加了咨询风格的亲和力
- Marker 形状的语义编码帮助读者快速识别数据点的类别归属

###### 7.6.3 横向柱状对比图 (Horizontal Bar Comparison)

**vS 参考页**: P4, P7(右), P8(右), P13, P14

| 属性 | 规范 |
|---|---|
| **触发场景** | 三品牌在某维度上的直接对比 |
| **方向** | 以**横向（水平）**为主（纵向柱状图在 vS 中极少使用） |
| **配色** | 元宝: `#3FBF6F` / DS: `#1E6FE0` / 豆包: `#BBD8F8` |
| **数值标签** | 在柱末端（外侧）或柱内部（当柱足够宽时），11-12pt Bold |
| **统计显著性** | 不显著的对比项用灰色 `#AAAAAA` 文字 "不显著" 替代柱子 |
| **排序** | 通常按某一品牌的值降序排列（便于快速识别最大/最小项） |
| **柱宽** | 统一柱宽，柱间距 ≥ 柱宽的 0.5 倍 |

###### 7.6.4 数据表格 (Data Table)

**vS 参考页**: P5, P7(左), P8(左), P12, P20

| 属性 | 规范 |
|---|---|
| **触发场景** | 结构化多维数据展示（人群画像 / 渠道来源 / 流失原因 / 策略路线 / 迁移矩阵） |
| **表头行** | 背景 `#EEEEEE`，文字 10-11pt Bold `#212121`，居中或左对齐 |
| **品牌列** | 列头含品牌 icon 或品牌名（品牌色着色） |
| **数据单元格** | 10-11pt Regular `#333333`，百分比值右对齐，文本值左对齐 |
| **红框高亮** | 关键数据格用 `#D32F2F` 2px solid 红框圈出（每页 ≤ 3-4 格） |
| **合计/汇总行** | 底部特殊行（样本量/合计），可用不同背景色或字体样式区分 |
| **Legend 行** | 表格下方，解释颜色编码（如"□代表纯白用户占比显著高于非纯白用户"） |
| **边框线** | 外框和主要分隔线 `#E0E0E0` 0.75pt; 内部细分线可更淡 `#F0F0F0` 0.5pt |
| **斑马纹** | vS 中**未使用**斑马纹交替行色（保持干净的白色背景） |

**vS 特色细节**:
- P7 的"各家纯白画像"表格是 vS 中最复杂的表格之一：3 品牌 × 2 纯白状态 × 3 维度（学历/城市线级/职业）= 18 个数据格 + 3 个红框高亮格
- P12 的策略路线表更像 roadmap 而非传统表格：左侧受众分层标签（蓝底白字）+ 右侧详细 bullet 描述

###### 7.6.5 KPI 指标卡 (KPI Metric Card)

**vS 参考页**: P5(左侧表格上半部分)

| 属性 | 规范 |
|---|---|
| **触发场景** | 展示核心指标的"一眼可见"总览（强留存率 / 总用户数 / 样本占比） |
| **布局** | 三列（元宝/DS/豆包），每列含：品牌 icon + 品牌名 + 大号百分比 + 小型彩色辅助柱 |
| **主数字** | 24-28pt Bold，品牌色 |
| **辅助柱** | 小型水平条形，用于直观展示相对大小关系 |
| **标签** | 指标名称（"强留存率"、"总用户数"）在左侧，12-13pt Bold |

###### 7.6.6 时间/堆叠分布图 (Timeline Stacked Bar)

**vS 参考页**: P9

| 属性 | 规范 |
|---|---|
| **触发场景** | 时间维度分布（下载时间分布 / 使用时长分布 / 用户生命周期阶段） |
| **方向** | 水平堆叠条形 |
| **配色** | 同一品牌的不同时间段用**同色系的深浅变化**表示（如元宝: 深绿→中绿→浅绿） |
| **百分比标签** | 在条内或条末端，10-11pt |
| **辅助信息** | 条下方显示样本量和占比（灰色椭圆或括号包裹） |

###### 7.6.7 柱状图（通用规范） Bar Chart

> 通用柱状图规范，适用于 `bar_horizontal` 和 `bar_vertical` 两种方向。`bar_horizontal` 为默认首选。

| 属性 | 规范 |
|---|---|
| **方向选择** | `bar_horizontal`（默认）：类别名 ≤ 12 个、标签文字较长；`bar_vertical`：时间序列或类别名 ≤ 4 个且短 |
| **配色** | 单系列：`color.chart.palette[0]`；多系列：按 `color.chart.palette[]` 分配；三方对比：`color.brand.three_way[]` |
| **数值标签** | 柱末端外侧（柱宽 ≥ 12pt 时）或柱内部（柱窄时），11-12pt Bold |
| **排序** | `bar_horizontal`：按数值降序；`bar_vertical`：按时间升序 |
| **柱宽/间距** | 统一柱宽；柱间距 ≥ 柱宽 × 0.5 |
| **坐标轴** | 轴线 `color.line.grid`（0.5pt）；轴标签 `text.table_cell`（10-11pt）；Y 轴从 0 开始（除非有强理由截断） |
| **统计显著性** | 不显著的对比项用灰色 `#AAAAAA` 文字 "不显著" 替代柱子 |

###### 7.6.8 折线图 Line Chart

**触发场景**: 时间序列趋势、多系列趋势对比

| 属性 | 规范 |
|---|---|
| **线条** | 粗细 2.0-2.5pt；单系列 `color.brand.primary`；多系列按 `color.chart.palette[]` 分配 |
| **数据点 marker** | 圆形 ● 直径 4-6pt；重要拐点可放大至 8pt |
| **数值标签** | 仅标注关键拐点或首尾点（避免全部标注导致视觉混乱） |
| **Y 轴** | 从 0 开始（除非截断有明确业务理由）；范围覆盖数据 ±10% |
| **图例** | 图表上方或右侧，10-11pt；≥ 4 系列时可用直接标注替代图例 |
| **网格线** | 仅水平网格线（`color.line.grid`，0.5pt，浅灰）；垂直网格线仅在 x 轴标签稀疏时使用 |
| **面积变体** | `area`：折线下方填充 `color.chart.palette[0]` 且 `opacity=0.2`（浅且不抢眼） |

###### 7.6.9 散点图/气泡图 Scatter/Bubble

**触发场景**: 两维分布（scatter）、三维分布（bubble，z = 气泡面积）

| 属性 | 规范 |
|---|---|
| **X/Y 轴** | 轴线 `color.line.grid`（0.5pt）；根据数据范围动态调整；标注轴标题（12-13pt Bold `text.subheading`） |
| **数据点** | scatter：● 直径 6-10pt；bubble：气泡面积（非半径！）与 z 值成正比 |
| **分组** | 用形状（●▲■◆）或颜色（`color.chart.palette[]`）区分组别 |
| **趋势线** | 可选；0.5pt 虚线，同系列色，`opacity=0.6` |
| **标注** | 重点数据点可标注名称（10-11pt）；避免全部标注 |
| **四象限变体** | 叠加 x=中位数、y=中位数两条参考线；可用虚线椭圆包围聚类（`color.line.dashed`，1pt） |

###### 7.6.10 瀑布图/桥接图 Waterfall/Bridge

**触发场景**: 数值分解（起始值 → 各环节增减 → 终点值）、贡献度分析

| 属性 | 规范 |
|---|---|
| **桥接柱** | 起始/终点柱：`color.brand.primary` 填充；中间增减柱：正 → `color.accent.success`，负 → `color.accent.danger` |
| **连线** | 相邻柱之间的细桥接线（1pt，`color.line.grid`） |
| **数值标签** | 每个柱上方标注绝对值或变化量（±）；终点柱标注总计 |
| **排序** | 按增减绝对值降序排列（最大贡献在最上方/最左侧） |

###### 7.6.11 漏斗图 Funnel

**触发场景**: 流程转化（逐级递减）、用户生命周期阶段、销售管线

| 属性 | 规范 |
|---|---|
| **形状** | 梯形（上宽下窄）；每级高度与数值成正比；级间间距 4-8px |
| **配色** | 从上到下渐变（`color.brand.primary` 深 → 浅）；或用 `color.chart.palette[]` 区分每级 |
| **数值标签** | 每级右侧或内部标注数值 + 百分比（占初始值的比例） |
| **转化率** | 级间用箭头 + 转化率文字（如 "→ 45%"），`text.muted` 10-11pt |
| **对标线** | 可选：行业基准或目标值用虚线 `color.line.dashed` 标示 |

###### 7.6.12 金字塔图 Pyramid

**触发场景**: 层级结构、优先级框架、MECE 分解、人口金字塔

| 属性 | 规范 |
|---|---|
| **形状** | 正梯形（上窄下宽 = 重要性/数量递减）；或倒梯形（上宽下窄 = 重要性递增） |
| **配色** | 每层级用 `color.chart.palette[]` 中的不同色；或单色系深浅变化 |
| **文字标注** | 每层级内或左侧标注名称 + 数值/百分比；L6-L7 字号 |
| **顶部** | 顶层为结论/核心，最大字号（L2-L3） |
| **底部** | 基础层（如 "样本量 N=xxx"），`text.muted` 9-10pt |

###### 7.6.13 堆叠柱状图 Stacked Bar

**触发场景**: 部分-整体对比（≤ 5 块）、100% 占比对比、构成分析

| 属性 | 规范 |
|---|---|
| **方向** | `bar_horizontal_stacked`（默认，便于读类别名）；`bar_vertical_stacked`（时间序列场景） |
| **配色** | 各部分（segment）用 `color.chart.palette[]` 区分；保持跨页一致 |
| **数值标签** | 每段内标注百分比（仅 ≥ 5% 的段才标；< 5% 省略以免拥挤）；10-11pt 居中 |
| **图例** | 图表上方或右侧，10-11pt；多系列时用直接标注替代图例 |
| **100% 模式** | `bar_stacked_100`：所有柱总长为 100%，便于跨类别比较占比；标注每段的百分比 |
| **排序** | segments 按数值降序排列（最大块在最下方/最左侧） |

###### 7.6.14 饼图/环形图 Pie/Donut

> ⚠️ **慎用**：人类对角度的判断不如长度准确。优先用 `bar_stacked_100`。仅在（≤ 5 块）且需要强调"整体中各部分的占比"时才用。

| 属性 | 规范 |
|---|---|
| **块数上限** | ≤ 5 块；超 5 块改 `bar_stacked_100` 或合并小值为"其他" |
| **配色** | 使用 `color.chart.palette[]`；最重要块可用 `color.brand.primary` 强调或 explode（分离） |
| **标注** | 块外连线 + 名称 + 百分比；避免直接标在块内（小角难以辨认） |
| **环形图变体** | 中心可放总计数字（KPI 场景），24-28pt Bold |
| **起始角度** | 12 点钟方向为最大块；顺时针按数值降序排列 |

---

##### 7.7 特殊元素规范

###### 7.7.1 Callout 框（概念定义框 / 强调标注框）

| 属性 | 规范 |
|---|---|
| **触发场景** | 定义关键概念（"强留存率"）或强调重要发现（"+14pp 提升"） |
| **背景色 - 定义型** | `#E8F0FA` (浅蓝) —— 用于概念定义（P3） |
| **背景色 - 强调型** | `#C8E6C9` (浅绿) —— 用于极度重要的正向发现标注（P6） |
| **圆角** | 4-6px |
| **内边距** | 10-14px |
| **文字** | 13-14pt Bold，居中或左对齐 |
| **边框** | 无（或极淡同色系 0.5pt） |
| **使用频率** | 每页 ≤ 2 个 callout 框 |

###### 7.7.2 红框高亮 (Red Border Highlight)

| 属性 | 规范 |
|---|---|
| **触发场景** | 表格中需要读者**特别注意**的关键数据格 |
| **样式** | 2pt solid `#D32F2F` 红色边框 |
| **适用对象** | 表格单元格（不在图表或自由文本上使用） |
| **使用限制** | 每页 ≤ 3-4 个红框格；避免相邻格同时红框（会失去焦点） |

###### 7.7.3 用户原声引用框 (Quote Box)

| 属性 | 规范 |
|---|---|
| **触发场景** | 引入真实用户反馈来佐证数据发现 |
| **背景色** | `#F5F5F5` (浅灰) 或带手撕边缘效果 |
| **引语文字** | 12pt Regular `#333333` |
| **用户画像** | 9pt `#888888`，格式 "—女/27/杭州/跨境电商"（性别/年龄/城市/职业） |
| **位置** | 通常在页面右侧或下方，与对应数据图表相邻 |

###### 7.7.4 统计显著性标注

| 属性 | 规范 |
|---|---|
| **触发场景** | 某对比项经统计检验后**不显著** |
| **表现形式** | 用灰色 `#AAAAAA` 或 `#BBBBBB` 文字 "**不显著**" 替代原来的数据可视化元素（柱/点/线） |
| **位置** | 原数据可视化元素的位置 |
| **注意** | 不能省略不显著的数据点——必须以某种形式告知读者"这里做了检验但没通过" |

###### 7.7.5 图例 (Legend)

| 属性 | 规范 |
|---|---|
| **位置** | 图表区域内（左上角或上方），不超出图表区的边界 |
| **格式** | marker shape/icon + 空格 + 文字标签 |
| **字号** | 10-11pt |
| **分隔** | 多个 item 之间用 3-4 个空格分隔 |
| **颜色** | 文字 `#333333`，marker 与数据点颜色一致 |

---

##### 7.8 间距与布局网格（基于 16:9 画布估算）

> 所有距离值为近似值，基于 vS.pdf 的视觉比例反推。renderer 实现时可微调 ±5px。

| 区域 | 距离 |
|---|---|
| 页面左边距 | ~60px (0.5") |
| 页面右边距 | ~60px (0.5") |
| 页面上边距 | ~40px (0.33") |
| 页面下边距 | ~50px (0.42") |
| **导航栏高度** | **28-32px** |
| 导航栏到主标题 | 16-20px |
| 主标题到内容区 | 20-24px |
| 内容区到脚注 | 16-20px |
| **左图表区宽度占比** | **60-65%** |
| **右发现面板宽度占比** | **35-40%** |
| 图表区 ↔ 发现面板间距 | 16-20px |
| 发现面板内边距 | 12-16px |
| Bullet 点之间行距 | 1.4× 字高（中文） |
| 发现标题到首条 bullet | 8-10px |
| 表格行高 | 22-26px（含文字 11pt + padding） |
| 表格外边距 | 四周至少 8px |

###### 7.8.1 布局约束规则（v0.7 新增）

> 为防止文本溢出、形状重叠、布局错位等问题，renderer 在实现时必须遵守以下约束。

**文本溢出预防**：

| 约束 | 规范 |
|---|---|
| **发现面板内容高度检查** | 添加每个要点前，检查 `content_top + 预计高度 < panel_top + panel_h`。若超出，减小字体至 `FONT_L6` 或省略部分要点（保留前 2 条） |
| **表格单元格文本换行** | 所有表格单元格必须设置 `cell.text_frame.word_wrap = True`；若文本超出单元格宽度，自动缩小字体至 `FONT_L6`（最小 `FONT_L4`） |
| **文本框最大字符数** | 单个文本框文本长度 > 300 字符时，必须启用 `word_wrap` 或拆分为多个文本框 |
| **标题最大长度** | 页面标题 ≤ 40 汉字 或 60 英文字符；超出时换行（最多 2 行） |

**形状重叠预防**：

| 约束 | 规范 |
|---|---|
| **导航栏标签宽度** | 根据节名长度动态计算 `sep_x`，节名长度 > 6 汉字时缩小字体至 `FONT_L5` 或缩写节名 |
| **KPI 卡片内文本位置** | 数值、标签、子标签的位置根据文本长度动态调整；若文本超出卡片宽度，缩小字体或换行 |
| **发现面板要点数量限制** | 每个发现子标题下的要点 ≤ 3 条；总要点数 ≤ 8 条（超出时省略低优先级要点） |

**布局错位预防**：

| 约束 | 规范 |
|---|---|
| **多表格布局** | 同一行放置 > 2 个表格时，检查总宽度是否超出 `content_w`；若超出，换行放置或减小表格宽度 |
| **图表位置检查** | 添加图表前检查与周围元素的间距 ≥ `space.md`（12px）；若重叠，调整位置或缩小图表尺寸 |
| **页面安全区** | 所有元素必须在 `safe_area` 内（左边距 60px，右边距 60px，上边距 40px，下边距 50px）；超出时调整位置或尺寸 |

**位置属性验证**：

| 约束 | 规范 |
|---|---|
| **异常值检测** | 所有形状的 `left`/`top`/`width`/`height` 属性必须是有效数值（整数或浮点数）；若出现 `'4111901.25'` 等异常值，必须删除并重新创建该形状 |
| **边界检查** | 所有形状的 `left + width ≤ SLIDE_W` 且 `top + height ≤ SLIDE_H`；超出时调整尺寸或位置 |

---

##### 7.9 字体与排版细节

| 属性 | 规范 |
|---|---|
| **首选中文字体** | 微软雅黑 (Microsoft YaHei) —— Windows 系统默认，清晰易读 |
| **英文字体/数字** | Segoe UI 或 Arial（与微软雅黑搭配时视觉效果最佳） |
| **字体 fallback 链** | 微软雅黑 → 苹方 (PingFang SC) → Helvetica Neue → Arial → sans-serif |
| **禁止使用的字体** | 宋体 (SimSun) —— 衬线体在小字号投影环境下辨识度差；花体/装饰字体；手写体 |
| **正文行距** | 1.3-1.5 倍字号（中文需要更大的行距） |
| **段落间距** | 段落之间 0.5-1 倍字号 |
| **对齐方式** | 正文左对齐；数字右对齐（表格中）；标题左对齐；页码/脚注按固定位置 |
| **最大行长** | 正文每行不超过 35-40 个中文字符（超过后换行） |
| **标点压缩** | 中文标点占 1 个字符宽度（半角或全角均可，但全文统一） |

###### 7.9.1 字体回退检查规则（v0.7 新增）

> 为防止目标机器上字体缺失导致渲染不一致，renderer 在实现时必须检查字体是否存在。

| 检查项 | 规范 |
|---|---|
| **字体存在性检查** | 在脚本开头检查 `font_family_primary` 是否存在于系统；若不存在，输出警告并使用 fallback 字体 |
| **Fallback 字体检查** | 检查 fallback 链中的字体是否存在；若都不存在，使用系统默认 sans-serif 字体 |
| **中文字体检查** | 检查中文字体是否能正确渲染中文字符（不出现方框 □） |
| **字体回退机制** | 当指定字体不存在时，按 `font_family_fallback` 链依次尝试；若全部失败，使用系统默认字体并输出警告到 `open_design_tasks` |

**字体检查代码示例**（Python）：
```python
import matplotlib.font_manager as fm

def check_font_exists(font_name):
    """检查字体是否存在"""
    system_fonts = [f.name for f in fm.fontManager.ttflist]
    return font_name in system_fonts

# 在渲染脚本开头检查
if not check_font_exists("Microsoft YaHei"):
    print("WARNING: 微软雅黑字体不存在，将使用 fallback 字体")
    # 尝试 fallback
    for fallback in ["PingFang SC", "Helvetica Neue", "Arial"]:
        if check_font_exists(fallback):
            FONT_CN = fallback
            break
```

---

##### 7.10 动画与切换规范（vS.pdf 为静态打印版，以下为 PPT 原文件的推断）

| 类型 | 规范 |
|---|---|
| **默认动画** | **无动画**（vS.pdf 是静态打印版，原始 PPT 推测也无动画） |
| **允许的切换效果** | 仅 "淡出" (Fade) 或 "无" (None) |
| **禁止的效果** | 所有飞入/旋转/弹跳/擦除等动态效果；文字逐行出现；图表序列动画 |
| **如果必须有动画**（如现场演讲版） | 仅限：① 整页淡入 ② 发现面板的 bullet 逐条淡入（Click 触发）③ 图表序列按品牌逐个出现（Click 触发） |
| **动画时长** | 如使用，每个 ≤ 0.5 秒 |

---

##### 7.11 下游交接清单 (Renderer Handoff Checklist)

> 当 `formatted_material.v1` 传递给 renderer 时，以下 12 个变量**必须**在 `render_plan.format_handoff_notes` 中提供完整值。renderer 依赖这些参数来正确渲染每一页。

| # | 变量名 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| 1 | `font_family_primary` | string | ✅ | 主字体，默认 `"Microsoft YaHei"` |
| 2 | `font_family_fallback` | string | ✅ | Fallback 链，默认 `"PingFang SC, Helvetica Neue, Arial, sans-serif"` |
| 3 | `aspect_ratio` | string | ✅ | 画布比例，默认 `"16:9"` |
| 4 | `brand_color_primary` | hex | ✅ | 主品牌色，默认 `#1E6FE0` |
| 5 | `three_way_palette` | object | ✅ | 三方色板 `{yuanbao: "#3FBF6F", ds: "#1E6FE0", doubao: "#BBD8F8"}` |
| 6 | `nav_bar_color` | hex | ✅ | 导航栏背景色，默认 `#003D82` |
| 7 | `nav_tabs` | string[] | ✅ | 导航栏 tab 名称列表，如 `["人群","纯白","非纯白","文本","功能","运营"]` |
| 8 | `panel_bg_color` | hex | ✅ | 发现面板背景色，默认 `#F5F5F5` |
| 9 | `confidential_tag` | string | ❌(可选) | 保密标签文字，默认 `"内部汇报 · 仅供参考"`；传空字符串则不渲染 |
| 10 | `logo_type` | enum | ✅ | `"tencent_blue"` (白底页) / `"tencent_white"` (有色背景页) / `"none"` (无logo) |
| 11 | `source_note_prefix` | string | ❌(可选) | 来源脚注前缀，默认 `"来源: "`；每页的完整脚注由 renderer 根据 `material_unit.source_notes[]` 拼接 |
| 12 | `user_template_path` | string | ❌(可选) | 用户 PPT 模板 .pptx 路径；非空时 renderer 加载该模板的母版页、配色、字体并适配输出；为空时用 renderer 内置默认母版（腾讯 vS 风格） |

###### 7.11.1 Renderer 错误处理要求（v0.7 新增）

> 为防止渲染脚本因数据异常或位置属性异常而崩溃，renderer 必须实现错误处理。

| 要求 | 规范 |
|---|---|
| **数据验证** | 添加图表/表格前，检查数据是否有效（非空、数值类型正确）；若无效，输出警告并使用安全默认值 |
| **位置属性验证** | 所有形状的 `left`/`top`/`width`/`height` 必须是有效数值；若出现异常值（如 `'4111901.25'`），删除并重新创建该形状 |
| **异常处理** | 每个渲染函数必须有 `try-except` 块；捕获异常后输出错误信息到日志，并继续渲染下一页（不中断整个渲染过程） |
| **图表数据检查** | `chart_spec.data_ref` 引用的数据必须存在且可解析；若数据缺失，改用安全版式（如仅显示表格）并写 `open_design_tasks` |

**错误处理代码示例**（Python）：
```python
def safe_add_shape(slide, shape_type, left, top, width, height, **kwargs):
    """安全添加形状（验证位置属性）"""
    try:
        # 验证位置属性
        if not (isinstance(left, (int, float)) and isinstance(top, (int, float))):
            raise ValueError(f"Invalid position: left={left}, top={top}")
        if not (isinstance(width, (int, float)) and isinstance(height, (int, float))):
            raise ValueError(f"Invalid size: width={width}, height={height}")
        
        # 检查边界
        if left + width > SLIDE_W or top + height > SLIDE_H:
            raise ValueError(f"Shape out of bounds: left+width={left+width}, top+height={top+height}")
        
        # 添加形状
        shape = slide.shapes.add_shape(shape_type, left, top, width, height)
        return shape
    except (ValueError, AttributeError) as e:
        print(f"WARNING: Failed to add shape: {e}")
        # 记录到 open_design_tasks
        return None  # 返回 None，调用者需处理
```

###### 7.11.2 Renderer 日志要求（v0.7 新增）

> 为方便调试和定位问题，renderer 必须输出日志。

| 要求 | 规范 |
|---|---|
| **日志级别** | DEBUG（详细调试信息）、INFO（关键步骤）、WARNING（潜在问题）、ERROR（渲染失败） |
| **日志内容** | 每页渲染开头输出 `INFO: Rendering P{i} ({layout_type})`；添加图表/表格时输出 `DEBUG: Added chart/table`；捕获异常时输出 `ERROR: {exception}` |
| **日志输出** | 输出到控制台（stdout）或日志文件（如 `render.log`） |
| **日志格式** | `[2026-07-01 13:14:09] INFO: Rendering P1 (cover_title)` |

**日志代码示例**（Python）：
```python
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),  # 输出到控制台
        logging.FileHandler('render.log')  # 输出到文件
    ]
)

logger = logging.getLogger(__name__)

# 在渲染函数中使用
def render_cover(prs):
    logger.info("Rendering P1 (cover_title)")
    try:
        # 渲染代码...
        logger.debug("Added title text box")
    except Exception as e:
        logger.error(f"Failed to render cover: {e}")
        raise
```

---

> **§7.13 用户模板适配规范**（新增）：当 `user_template_path` 非空时，renderer 必须按 §7.13 的规则完成模板元素提取、layout 映射和冲突处理，确保输出 PPT 符合用户模板的视觉规范。

##### 7.12 页面内容强制规则 ⛔ **新增**

> 本条规则为 v0.5 新增，针对 vS.pdf 的实际页面特征（**每一页都有图表/表格/形状，没有任何一页是纯文字**）提炼而成。format worker 在输出每个 `material_unit` 时**必须检查**本条规则。

###### 7.12.1 核心禁令：禁止纯文字页

**规则**：每个 `material_unit`（即每一页 slide）**必须包含至少一个视觉元素**。纯文字页（整页只有标题 + bullet points，无任何图/表/形状）**一律禁止**。

| 概念 | 定义 |
|---|---|
| ✅ **允许** | 图表（柱状图/折线图/散点图/象限图等）、数据表格、KPI 指标卡、流程图形状（箭头/方框/椭圆等）、callout 标注框、引用框、发现面板（含要点列表 + 灰色背景，视为视觉元素） |
| ❌ **禁止** | 整页只有 `headline` + `supporting_points`（纯文字 bullet 列表），无任何形状/色块/图表/表格 |

###### 7.12.2 每页视觉元素检查清单

format worker 在生成每个 `material_unit` 时，必须确认以下检查项：

| # | 检查项 | 强制 |
|---|---|---|
| 1 | 本页是否有 `visual_object.chart_spec`（图表规格）？ | ✅ 至少 1 项满足 |
| 2 | 本页是否有 `visual_object.table_data`（数据表格）？ | ✅ 至少 1 项满足 |
| 3 | 本页是否含发现面板（`layout_type = chart_with_panel` 或显式 `discovery_panel` 字段）？ | ✅ 至少 1 项满足 |
| 4 | 本页是否有形状元素（`visual_object.shapes[]`，如箭头/方框/椭圆/标注线）？ | ✅ 至少 1 项满足 |
| 5 | 本页是否有 KPI 指标卡（`layout_type = kpi_dashboard`）？ | ✅ 至少 1 项满足 |
| 6 | 本页是否为封面页（`cover_title`）或核心发现页（`executive_summary`，含灰色面板视为视觉元素）？ | ✅ 豁免：封面/核心发现页可用大字+面板替代图表 |

**判定逻辑**：
- 检查项 1–5 至少一项 = `true` → 本页 **合规**
- 检查项全部 = `false` → 本页 **不合规**，必须修改 `layout_type` 或添加 `visual_object`
- `executive_summary` 页：灰色面板 `#F5F5F5` 背景 + 发现要点，视为已含视觉元素，**豁免**纯文字禁令
- `cover_title` 页：大字号标题 + 有色背景，视为已含视觉元素，**豁免**纯文字禁令

###### 7.12.3 纯文字页的整改方案

当 format worker 发现某页当前为纯文字时，必须按以下优先级整改：

| 优先级 | 整改方案 | 适用场景 |
|---|---|---|
| P0 | 添加 `chart_spec`（用数据图表支撑文字结论） | 有任何可视图数据时 |
| P1 | 改用 `chart_with_panel` layout（左图右文） | 有图表 + 需要解读时 |
| P2 | 添加数据表格 `table_data` | 数据维度多、不适合图表时 |
| P3 | 添加形状元素 `shapes[]`（箭头/流程图/框架图） | 纯框架性内容（如 pyramid/funnel） |
| P4 | 改用 `kpi_dashboard` layout（指标卡） | 结论是数值型 KPI 时 |

###### 7.12.4 Quality Check 条目

新增 `quality_checks[]` 条目（format worker 输出时必须包含）：

```
FMT-FM-PPT-NO-TEXT-ONLY-001:
  description: "每页必须有图/表/形状，禁止纯文字页"
  check: "每个 material_unit 的 visual_object 非空，或 layout_type ∈ {cover_title, executive_summary, chart_with_panel, table_chart_hybrid, multi_bar_comparison, timeline_distribution, kpi_dashboard, strategy_roadmap, user_voice_quote, conversion_funnel, discussion_action}"
  fail_action: "强制添加 chart_spec 或改用 chart_with_panel layout"
```

###### 7.12.5 文本溢出预防检查（v0.7 新增）

> 为防止文本溢出文本框、表格单元格或发现面板，format worker 在输出 `material_unit` 时必须检查以下项。

| # | 检查项 | 规范 | 强制 |
|---|---|---|---|
| 1 | 发现面板内容高度 | `content_top + 预计高度 < panel_top + panel_h`；超出时减小字体或省略要点 | ✅ |
| 2 | 表格单元格文本换行 | 所有表格单元格设置 `word_wrap = True`；文本超出时自动缩小字体至 `FONT_L6`（最小 `FONT_L4`） | ✅ |
| 3 | 文本框最大字符数 | 单个文本框 > 300 字符时必须启用 `word_wrap` 或拆分 | ✅ |
| 4 | 页面标题最大长度 | ≤ 40 汉字 或 60 英文字符；超出时换行（最多 2 行） | ✅ |
| 5 | 发现面板要点数量 | 每个子标题下 ≤ 3 条；总要点数 ≤ 8 条 | ❌(建议) |
| 6 | KPI 卡片文本溢出 | 数值/标签/子标签超出卡片宽度时，缩小字体或换行 | ✅ |

**文本溢出修复流程**：
```
检查文本是否溢出
  ├─ 是 → 启用 word_wrap
  │        ├─ 仍溢出 → 减小字体（L6 → L5 → L4）
  │        └─ 仍溢出 → 拆分到多个文本框 或 省略部分文本
  └─ 否 → 继续
```

---

> **本节（§7.1 – §7.12）与 McKinsey 培训 PPT 通用规范的关系**：
> McKinsey 培训提供了**理论层面的完整图表库和版式库**（12类图表 × 10种版式），是"知道有哪些工具可用"的知识库。
> vS.pdf 则展示了**在真实咨询项目中如何选择和使用这些工具**（实际只用了 6 类图表 × 13 种版式），并加入了 McKinsey 培训中没有的**项目特有元素**（导航栏、发现面板、三方色板、保密标签等）。
> **本节以 vS.pdf 为最高优先级标准**，McKinsey 培训中的图表/版式类型在本节未覆盖的部分可作为扩展参考（但不应作为默认选项）。
> **§7.12 禁止纯文字页规则**是 vS.pdf 所有 23 页的共性特征提炼——vS.pdf 中**没有任何一页是纯文字页**，每一页都有图表/表格/形状/面板作为视觉支撑。
> **§7.13 用户模板适配规范**（新增）：当 `user_template_path` 非空时，renderer 必须按本节约定的规则完成模板元素提取、layout 映射和冲突处理，确保输出 PPT 符合用户模板的视觉规范。

##### 7.13 用户模板适配规范（Template Adaptation）

> 本条规则为 v0.6 新增，支持 format worker 接受用户提供的 .pptx 模板文件，并将输出适配到该模板的母版页、配色和字体。

###### 7.13.1 模板接入方式

| 方式 | 说明 |
|---|---|
| **显式指定** | `render_plan.format_handoff_notes.user_template_path` 填写用户模板 .pptx 路径；renderer 优先使用模板中的母版页 |
| **隐式检测** | 若 `user_template_path` 为空但工作区存在 `templates/default.pptx`，自动检测并使用 |
| **无模板** | `user_template_path = null` 时，使用 renderer 内置的默认母版（腾讯 vS 风格） |

###### 7.13.2 模板元素提取与映射

Renderer 在加载用户模板后，必须提取并映射以下元素：

| 模板元素 | 提取内容 | 映射目标 |
|---|---|---|
| 母版页（Master Slides） | 所有母版页的 `layout_type` 名称、占位符位置 | `material_unit.layout_or_structure.layout_type` 优先映射到同名母版页 |
| 配色方案（Theme Color） | 主题色板（12 色） | `style_tokens.color.*` 自动继承模板色板；若冲突，以 `format_handoff_notes.brand_color_primary` 为准 |
| 字体方案（Theme Font） | 标题字体、正文 | `style_tokens.font.family.*` 自动继承；若模板字体不可读（如手写体），回退到 skill 默认字体 |
| 版式占位符 | 标题框、正文框、图表区、图片区的位置和尺寸 | `layout_or_structure` 的间距参数自动适配模板占位符位置 |

###### 7.13.3 映射优先级

| 优先级 | 规则 |
|---|---|
| P0 | 模板中**存在同名母版页** → 直接使用（如模板有 `chart_with_panel` 母版页，则使用该页） |
| P1 | 模板无同名母版页，但**版式相似**（如 `标题+图表` 可映射为 `bar_chart`） → 使用最相似的母版页 |
| P2 | 模板无对应母版页 → 使用 renderer 内置默认母版，在 `open_design_tasks` 中记录"模板缺失 XX 版式" |
| P3 | 模板母版页的占位符位置与 skill 规范**冲突**（图表区太小） → 以 skill 规范为准，调整占位符尺寸 |

###### 7.13.4 模板适配工作流

```
用户输入（可选）：
  render_plan.format_handoff_notes.user_template_path = "C:/.../用户模板.pptx"

Format worker 执行：
  1. 检查 user_template_path 是否存在
  2. 若存在：提取模板的母版页列表、配色、字体
  3. 对每个 material_unit：
     a. 尝试将 layout_type 映射到模板中的母版页
     b. 若映射成功：使用模板母版页渲染
     c. 若映射失败：使用默认母版页，记录到 open_design_tasks
  4. 输出：template_adaptation_report（映射成功率、冲突清单、回退清单）

Renderer 执行：
  1. 加载 user_template_path 中的 .pptx
  2. 按 format worker 的映射指示，使用对应母版页创建每页
  3. 将 style_tokens 中的色值、字体写入对应母版页的占位符
  4. 若模板母版页的布局与 style_tokens 的间距冲突，以 style_tokens 为准
```

###### 7.13.5 模板适配 Quality Check

| # | 检查项 |
|---|---|
| 1 | `user_template_path` 非空时，文件必须存在且为合法 .pptx |
| 2 | 所有 `material_unit.layout_type` 至少有 P1 级映射（同名或相似母版页） |
| 3 | 模板配色与 `brand_color_primary` 不冲突（或已显式指定覆盖） |
| 4 | 模板字体的中文字符渲染正常（不出现乱码或方框） |
| 5 | 模板母版页的图表区尺寸 ≥ skill 规范的最小尺寸（避免数据标签被截断） |

---

##### 7.14 Renderer 实现质量规范（v0.7 新增）

> 本条规则为 v0.7 新增，针对 QA 检查发现的代码质量问题（硬编码位置、重复代码、缺乏错误处理等），为 renderer 实现提供质量指南。

###### 7.14.1 避免硬编码位置和尺寸

**问题**：位置和尺寸硬编码导致规范变化时需逐个修改，且不同页面可能不一致。

**规范**：
- 所有位置和尺寸**必须**使用 §7.8 定义的常量（如 `NAV_H`, `PANEL_W`, `FONT_L8` 等）
- 禁止使用魔法数字（如 `Inches(0.35)` 应定义为 `NAV_H = Inches(0.35)` 然后引用 `NAV_H`）
- 页面尺寸变化时，使用相对位置（如 `SLIDE_W * 0.05` 表示左边距 5%）而非绝对位置

**示例**：
```python
# ❌ 错误：硬编码
slide.shapes.add_textbox(Inches(0.4), Inches(1.28), ...)

# ✅ 正确：使用常量
CONTENT_LEFT = Inches(0.4)  # 页面左边距
TITLE_TOP = NAV_H + Inches(0.2)  # 导航栏下方
slide.shapes.add_textbox(CONTENT_LEFT, TITLE_TOP, ...)
```

###### 7.14.2 减少重复代码

**问题**：每个渲染函数都重复添加 logo、标题、页脚，代码重复率高。

**规范**：
- 创建 `BaseSlideRenderer` 基类，包含通用方法（`add_logo`, `add_title`, `add_footer`, `add_nav_bar`）
- 每个页面的渲染函数继承基类，只需实现页面特有的内容渲染
- 通用样式设置（如字体、颜色）提取到基类或辅助函数

**示例**：
```python
class BaseSlideRenderer:
    def __init__(self, prs, style_tokens):
        self.prs = prs
        self.style = style_tokens
    
    def add_common_elements(self, slide, page_num, title_text, nav_section=None):
        """添加通用元素：logo, 标题, 导航栏, 页脚"""
        add_tencent_logo(slide)
        add_slide_title(slide, title_text)
        if nav_section:
            add_nav_bar(slide, nav_section)
        add_footer(slide, page_num)
    
    def render_slide(self, page_num, title_text, nav_section=None):
        """渲染单页（模板方法模式）"""
        slide = self.create_slide()
        self.add_common_elements(slide, page_num, title_text, nav_section)
        self.render_content(slide)  # 由子类实现
        return slide
    
    def render_content(self, slide):
        """由子类实现的具体内容渲染"""
        raise NotImplementedError

class CoverRenderer(BaseSlideRenderer):
    def render_content(self, slide):
        # 封面特有内容
        ...
```

###### 7.14.3 配置外部化

**问题**：配色、字体、间距等分散在代码中，修改时需要改动多个位置。

**规范**：
- 将配色方案、字体方案、间距方案提取到配置文件（如 `config.json` 或 `config.yaml`）
- 或在脚本开头定义配置字典，统一管理
- 支持从用户模板中自动提取配置（参见 §7.13）

**示例**：
```python
# config.py
STYLE_CONFIG = {
    "color": {
        "brand_primary": "#1E6FE0",
        "yuanbao_green": "#3FBF6F",
        ...
    },
    "font": {
        "primary": "Microsoft YaHei",
        "fallback": ["PingFang SC", "Arial"],
        "sizes": {"L10": 32, "L9": 26, ...}
    },
    "spacing": {
        "nav_h": 0.35,
        "panel_w": 4.3,
        ...
    }
}
```

###### 7.14.4 模块化设计

**问题**：单个渲染脚本过长（> 2000 行），难以维护。

**规范**：
- 将渲染脚本拆分为多个模块：
  - `config.py` - 配置
  - `utils.py` - 辅助函数（添加形状、设置字体等）
  - `renderers/` - 各页面渲染器（按页面类型分组）
  - `main.py` - 主程序入口
- 每个模块 ≤ 300 行
- 使用明确的导入关系，避免循环导入

**推荐目录结构**：
```
render_tool/
├── config.py           # 配置
├── utils.py            # 辅助函数
├── base_renderer.py    # BaseSlideRenderer 基类
├── renderers/          # 渲染器目录
│   ├── cover.py        # 封面页
│   ├── summary.py      # 核心发现页
│   ├── methodology.py  # 方法论页
│   ├── dashboard.py    # KPI 仪表盘页
│   └── ...
└── main.py             # 主程序
```

### `format.document` capability

#### 能力边界

- **能做**：完整论证 + 详细脚注 + 章节可独立阅读 + 打印 / 存档。
- **不能做**：高密度动画、native chart 实时交互、强时间节奏的引导。

#### layout 库（10 个 `document_role`）

| `document_role`        | 适用场景               | 必含字段                                                            |
| ---------------------- | ------------------ | --------------------------------------------------------------- |
| `executive_summary`    | 全文导读（**必为首个正文单元**） | `headline` + 5 条 `key_points` + 1 句 `recommended_action`        |
| `introduction`         | 背景 / 问题陈述          | `context`, `scope`, `methodology_summary`                       |
| `finding_section`      | 单一发现的完整论证          | `headline`, `argument_chain` (含 evidence 链), `visualizations[]` |
| `comparison_section`   | 并排比较               | `criteria[]`, `options[]`, `comparison_table`                   |
| `recommendation`       | 行动建议               | `action`, `rationale`, `expected_impact`, `risks[]`             |
| `risk_section`         | 风险与缓解              | `risk`, `likelihood`, `impact`, `mitigation`                    |
| `methodology_appendix` | 方法学说明              | `methods`, `data_sources[]`, `limitations[]`                    |
| `data_appendix`        | 数据附录               | `tables[]`, `source_refs[]`                                     |
| `glossary`             | 术语表                | `terms[]`                                                       |
| `bibliography`         | 引用与来源              | `references[]`                                                  |

#### 字段填写规则（Document 特化）

- `unit_type = "document_section"`（强一致；每章一单元）
- `layout_or_structure.layout_type` 必填，从上表 10 个选
- `layout_or_structure.paragraph_roles[]`：每段标 `{role: "topic | evidence | analysis | recommendation", text}`
- `finalized_content` 必含 `body`（完整段落）+ `bullet_groups[]`（要点列表）
- `visual_object.document_asset_mode ∈ {table_only, chart_embed, mixed}`，决定 `visualizations[]` 结构
- `format_handoff_notes` 必含：模板、TOC 深度、页眉页脚模板（见下方"Document 呈现形式 / 模板变量"）

#### renderer handoff 契约

- `render_plan.renderer = "docx_report_renderer"`
- `deliverables[0]` = `{ "name": "<topic>.docx", "format": "docx", "renderer": "docx_report_renderer" }`
- `asset_requirements[]` 至少含 `word_template`（如 `consulting_report_v3.dotx`）、所有表格数据、所有图片资源
- `manual_steps[]` 必含 TOC 复核、脚注连续性检查、附录页码
- `quality_checks` 必含 `FMT-FM-DOC-RENDER-READY-001`：首单元 `document_role=executive_summary` + 必填字段非空

---

#### Document 呈现形式规则（format.document 专属）

> 与 PPT / HTML 在字号单位、纸张、页码、表格处理上**有本质差异**——Document 用 cm、A4 纸、罗马+阿拉伯双段页码、跨页表格续表，**没有动画也没有交互**。

##### typography（Document 量化值）

- 字体栈：sans `思源黑体 / Calibri`；serif `思源宋体 / Georgia`（报告场景**默认用 serif**）；mono `Consolas`
- 字号（pt）：`title 22` / `h1 18` / `h2 16` / `h3 14` / `body 11` / `caption 9` / `footnote 8`（**比 PPT 整体小 1 档**，因长文阅读）
- 行距：`tight 1.2` / `normal 1.5` / `relaxed 1.7`（**比 PPT 整体宽**，长文舒适）
- 字重：`bold 700` / `medium 500` / `regular 400`（**bold 用 700** 区别于 PPT 600）

##### color（Document 取值与角色）

- 品牌色取值与 PPT **完全一致**（同 brand 下三载体品牌色必须统一）
- `color.brand.three_way[]`：Document 中**极少用**（仅在 `comparison_section` 中需要 3 方对比时使用）
- 强调色更保守：`color.accent.success` 默认 `#2E7D32`（**深绿**，区别于 PPT 明亮 `#3FBF6F`）
- `color.surface.panel`：`#F5F7FA` / `#EAEAEA`（长文阅读低对比）
- `color.chart.palette[]`：与 PPT 同（跨载体一致）

##### spacing / grid（Document 量化值，A4 纸）

- 间距（cm）：`xs 0.1` / `sm 0.3` / `md 0.5` / `lg 0.8` / `xl 1.2` / `2xl 1.6`
- 栏：1（**单栏长文**）；gutter —；margin 2.5（cm）；safe_area 3.0

##### chart 类型决策（Document 专属，**不推荐棒棒糖 / 象限图**）

| 数据形态           | Document 推荐                               |
| -------------- | ----------------------------------------- |
| 类别 vs 数值（≤6 类） | `bar_horizontal`（横向条形，**便于阅读标签**）         |
| 类别 vs 数值（≥7 类） | `bar_horizontal`（带排序）                     |
| 时间序列           | `line`                                    |
| 部分-整体（≤5）      | `pie`（**慎用**，仅 2-3 块；多于 3 块改 stacked_bar） |
| 部分-整体（>5）      | `treemap`                                 |
| 两维分布           | `scatter`                                 |
| 流程转化           | `funnel`                                  |
| 数值分解           | `waterfall`                               |
| 地理             | `choropleth_map`                          |
| 矩阵定位           | `matrix_2x2`                              |

> Document **不强制使用** PPT 的 `lollipop_grouped` / `quadrant_3group`；若 story 强需求可借调，但需在 `format_decisions[]` 写理由（"PPT 原型延续"）。默认采用**更易打印**的 `bar_horizontal` / `matrix_2x2`。

##### table 样式（Document 量化值）

- 表头：加粗 + 底色 `color.surface.panel`（**不用品牌色**，避免长文阅读视觉过载）
- 行高 1.5；斑马纹**开**（`color.surface.bg` / `color.surface.panel`）；数字右对齐 / 文字左对齐
- 合计行：加粗 + 顶分隔线 1.5pt
- 脚注：表格下方 ≤ 3 行（footnote 字号 8pt）
- 边框：**全框 + 内外边框**（hairline 0.5pt）—— 区别于 PPT 的"仅水平"

##### asset 规则（Document 量化值）

- 图片：200 dpi（**高于 PPT**）；png / jpg / svg
- 引用：角注编号 `[1]`
- Logo：页眉 / 页脚（**每页都有**，区别于 PPT 仅角落）
- 视频：**不推荐**（仅超链接）—— 区别于 PPT 嵌入
- 图标库：Lucide
- 引用对齐：左对齐（图片）/ 角注（数据）

##### Document 特有规则

- **纸张与边距**：
  - 默认 A4（210×297mm）；Letter（8.5×11in）备选
  - 页边距：上 2.5cm / 下 2.5cm / 左 2.5cm / 右 2.5cm
  - 装订线：左 +0.5cm（仅装订场景）
- **页眉页脚**（**每页都有**，区别于 PPT）：
  - 页眉：左 公司 logo（高度 0.8cm） / 中 文档标题（caption 字号） / 右 章节编号
  - 页脚：左 日期（footnote 字号） / 右 "第 X 页 / 共 Y 页"（footnote 字号）
- **TOC 与编号**：
  - TOC 深度：默认 2 级（章 / 节）；长报告可 3 级
  - 段落间距：段前 0pt / 段后 6pt
  - 标题断页：**H1 强制新页起**；H2 同页
- **图表位置**：
  - inline 嵌入：figure 标题在上、数据在下
  - figure 标题：caption 字号，左对齐
  - **跨页表格：必须从表头续起**（"续表 X"）；不允许在表中间断页 —— Document 特有
- **页码编号**（**Document 特有，HTML/PPT 无此概念**）：
  - 前置部分（封面 / TOC / 摘要）：罗马数字（i, ii, iii）
  - 正文：阿拉伯数字（1, 2, 3）
  - 附录：阿拉伯数字续编
- **模板变量**（`format_handoff_notes` 必填）：
  - `word_template` = `consulting_report_v3.dotx`（或指定）
  - `toc_depth` = `2`（默认）/ `3`（长报告）
  - `page_number_style` = `roman`（前置）/ `arabic`（正文+附录）

---

### `format.html` capability

#### 能力边界

- **能做**：可交互 / 可展开 / 可分享链接 / 移动端可读 / 按需深读 / 暗色主题。
- **不能做**：受控于 PDF/PPT 的"逐页节奏"叙事；外发时**必须**脱敏。

#### layout 库（5 个内部结构）

| 内部结构                | 必含元素                                                                              | 触发      |
| ------------------- | --------------------------------------------------------------------------------- | ------- |
| `summary_panel`     | `headline`, `key_takeaways[]` (≤5), `quick_jump_anchors[]`                        | 页面顶部常驻  |
| `navigation`        | `toc[]`, `breadcrumb`                                                             | 左侧 / 顶部 |
| `module_body`       | `headline`, `body_blocks[]` (text / chart / table / quote / expandable / callout) | 主内容区    |
| `evidence_expander` | `trigger_label`, `details[]` (source 详情 / 原始数据)                                   | 证据点可展开  |
| `appendix_panel`    | `references[]`, `glossary[]`, `method_notes`                                      | 页底      |

#### 字段填写规则（HTML 特化）

- `unit_type = "html_module"`（强一致；每模块一单元）
- `layout_or_structure.layout_type` 从 5 个内部结构中按需选 1–5 个
- `layout_or_structure.figure_slots[]`：声明图表位（避免布局漂移）
- `finalized_content.body_blocks[]` 类型枚举：`text | chart | table | quote | expandable | callout`
- `visual_object`：
  - `chart_spec` 数据驱动（与 PPT 同 schema）
  - `asset_requirements[]` 必含 `css_theme`、`responsive_breakpoints`
- `redaction_policy` 必填；外发场景默认 `external-strict`（人名 / 客户名 / 金额阈值脱敏；详见下方"HTML 呈现形式 / 脱敏规则"）
- **呈现形式规则**：见下方"HTML 呈现形式"整章

#### renderer handoff 契约

- `render_plan.renderer = "html_renderer"`
- `deliverables[0]` = `{ "name": "<topic>.html", "format": "html", "renderer": "html_renderer" }`（可单页可站点，由 `generation_path` 决定）
- `asset_requirements[]` 必含 `css_theme`、`responsive_breakpoints`、所有图表数据、所有可展开内容
- `manual_steps[]` 必含：外链健康度检查、移动端自检、敏感信息扫描
- `quality_checks` 必含 `FMT-FM-HTML-RENDER-READY-001`：所有 `html_module` 单元 `redaction_policy` 已设 + `css_theme` 已声明 + 所有 `body_blocks` 类型合法

---

#### HTML 呈现形式规则（format.html 专属）

> 与 PPT / Document 在字号单位、交互、响应式、脱敏上**有本质差异**——HTML 用 px、可交互、响应式断点、外发强制脱敏、双主题切换、键盘导航可达。

##### typography（HTML 量化值）

- 字体栈：sans `system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`（**系统字体优先**，区别于 PPT/Doc 的固定字体栈）；serif `Georgia, "Noto Serif SC", serif`；mono `"JetBrains Mono", Consolas, monospace`
- 字号（px）：`title 32` / `h1 24` / `h2 20` / `h3 18` / `body 16` / `caption 13` / `footnote 12`（**字号最大**，屏幕阅读 + 移动端适配）
- 行距：`tight 1.25` / `normal 1.6` / `relaxed 1.75`（**最宽**，屏幕可读性）
- 字重：`bold 600` / `medium 500` / `regular 400`

##### color（HTML 取值与角色）

- 品牌色取值与 PPT / Document **完全一致**（同 brand 三载体统一）
- `color.brand.three_way[]`：HTML 中**可用于模块化对比卡**（如产品对比三色卡片）
- **支持 light / dark 双主题**（HTML 特有）
  - light 主题 token：见上 PPT / Document 默认值
  - dark 主题 token：`color.neutral.900 = #F5F5F5` / `color.surface.bg = #1A1A1A` / `color.surface.panel = #2A2A2A`（**反相**）
- 强调色更明亮（屏幕）：`color.accent.success = #3FBF6F`（与 PPT 腾讯绿同）

##### spacing / grid（HTML 量化值，px）

- 间距（px）：`xs 4` / `sm 8` / `md 16` / `lg 24` / `xl 32` / `2xl 48`（**与 PPT 数值相同**，但 PPT 用 pt、HTML 用 px，视觉等效）
- 栏：12；gutter 24（**比 PPT 大 50%**，屏幕可读）；margin 24（**比 PPT 小**，移动端留白）；safe_area 32

##### chart 类型决策（HTML 专属，**可交互优先**）

| 数据形态           | HTML 推荐                                     |
| -------------- | ------------------------------------------- |
| 类别 vs 数值（≤6 类） | `bar`                                       |
| 类别 vs 数值（≥7 类） | `bar_horizontal`                            |
| 时间序列           | `line`（**可加 hover tooltip 显示原始数据**）         |
| 部分-整体（≤5）      | `donut`（**默认带交互**，可点选切片下钻）                  |
| 部分-整体（>5）      | `treemap`                                   |
| 两维分布           | `scatter`（**可点选散点 → 弹出 evidence expander**） |
| 流程转化           | `funnel`                                    |
| 数值分解           | `waterfall`                                 |
| 地理             | `map`（**可缩放、可点选**）                          |
| 矩阵定位           | `heatmap`（**可点选单元格 → 弹出 expander**）         |

> HTML **不强制使用** PPT 的 `lollipop_grouped` / `quadrant_3group`；推荐用 `bar` + `scatter` + expander 实现同类信息。若借调需在 `format_decisions[]` 写理由。

##### table 样式（HTML 量化值）

- 表头：sticky top + 底色 `color.surface.panel`（**sticky 滚动吸顶**，HTML 特有）
- 行高 1.5；斑马纹**开**；数字右对齐 / 文字左对齐
- 合计行：加粗 + 顶分隔线 2px
- 脚注：**hover tooltip**（区别于 PPT/Doc 的"表格下方文字"）
- 边框：仅水平分隔线（divider 色）

##### asset 规则（HTML 量化值）

- 图片：**@1x / @2x 双倍图**（移动端高清屏）；webp / svg（png 备用）
- 引用：hover tooltip + 角注编号（**双轨制**）
- Logo：顶部 nav 旁（**始终可见**，区别于 PPT/Doc 的角落/页眉）
- 视频：嵌入（mp4 / webm）
- 图标库：Lucide（`@lucide/web`）
- 引用对齐：居中（图片）/ tooltip（数据）

##### HTML 特有规则

**响应式断点**（HTML 特有，PPT/Doc 无此概念）：

| 断点    | 宽度         | 适用设备 |
| ----- | ---------- | ---- |
| `xs`  | `< 576px`  | 手机   |
| `sm`  | `≥ 576px`  | 大屏手机 |
| `md`  | `≥ 768px`  | 平板   |
| `lg`  | `≥ 992px`  | 小桌面  |
| `xl`  | `≥ 1200px` | 桌面   |
| `xxl` | `≥ 1400px` | 大屏   |

每断点行为：

- `lg` 以上：横向布局（侧栏 + 主内容 + 右侧栏）
- `md`：单列（侧栏折叠为顶部 nav）
- `xs` / `sm`：单列 + 图表单列 + 文字下移

**交互态**（HTML 特有）：

| 元素           | hover                             | active                      | focus                                    |
| ------------ | --------------------------------- | --------------------------- | ---------------------------------------- |
| 链接           | 下划线 + `color.brand.primary`       | `color.brand.secondary`     | `outline: 2px solid color.brand.primary` |
| 按钮           | 阴影 +1 + `translateY(-2px)`（≤0.2s） | 阴影 -1                       | `outline: 2px solid color.brand.primary` |
| 卡片           | 阴影 +1 + `translateY(-2px)`（≤0.2s） | 阴影 -1                       | `outline: 2px solid color.brand.primary` |
| expander 触发器 | 底色变 `color.surface.panel`         | 底色变 `color.surface.divider` | `outline: 2px solid color.brand.primary` |
| 表格行          | 底色变 `color.surface.panel`         | —                           | `outline: 2px solid color.brand.primary` |

折叠 / 展开动画：≤0.3s（`ease-in-out`）。

**键盘导航**（HTML 特有，无障碍硬要求）：

- Tab 顺序 = 视觉顺序
- expander：`Enter` / `Space` 触发
- 模态框：`Esc` 关闭
- 焦点态**必须**明显（不依赖颜色单一指示，配 outline）

**脱敏渲染**（**外发场景强制，HTML 特有硬约束**）：

| 数据类型   | 脱敏规则                                 |
| ------ | ------------------------------------ |
| 人名     | `***先生` / `***女士`                    |
| 客户名    | 缩写 + `（客户）`（如 `ABC 公司` → `A**（客户）`）  |
| 金额超过阈值 | 范围带（`¥10M` / `¥10M-100M` / `>¥100M`） |
| 内部代号   | 通用名（如 `Project X` → `重大转型项目`）        |
| 联系方式   | 仅留一级域名（`example.com`）                |
| 内部邮件   | 完全删除                                 |

**主题切换**（HTML 特有）：

- 支持 light / dark 双主题
- 用户偏好持久化到 `localStorage.theme`
- 默认跟随系统：`prefers-color-scheme`

**加载性能**（HTML 特有）：

- 首屏 LCP ≤ 2.5s
- 图表懒加载（`IntersectionObserver`，rootMargin `200px`）
- 大表格分页（每页 ≤ 50 行）
- 图片 `loading="lazy"`（首屏关键图除外）

**模板变量**（`format_handoff_notes` 必填）：

- `css_theme` = `mck_light_2025` / `mck_dark_2025`（**必填双主题**）
- `responsive_breakpoints` = 6 档默认（见上表）
- `interaction_states` = hover / active / focus 三态定义
- `redaction_policy` = `external-strict`（外发）/ `internal-relaxed`（内网）

---

## 跨载体协同（PPT / Doc / HTML 之间）

> 这一节给出**跨载体协同规则**，适用于**同一份内容**需要产多个载体版本时（如同一份 report 既要 PPT 又要 HTML）。单载体运行可跳过。

### 跨载体 rule 优先级

1. **业务规则**（如"不得展示未脱敏金额"）> **载体规则**（如"PPT 字号"）> **美学规则**（如"行距 1.5"）
2. **受众敏感** > **品牌一致** > **通用默认**
3. **离线资产**（已渲染的图片）> **在线资产**（CDN）
4. **可访问性**（a11y：对比度 ≥ 4.5:1 / 字号 ≥ 12px / focus 可见）> **视觉美观**

### 跨载体一致性约束

| 约束             | 说明                                                                                                                           |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **品牌色一致**      | 同 brand 下三载体的 `color.brand.primary` 与 `color.brand.three_way[]` 必须完全一致；切换 brand 时**所有**引用主色的位置（标题、callout、tab 高亮、椭圆、强调点）同步切换 |
| **字号视觉等效**     | 相同语义元素（标题 / 正文 / 脚注）的视觉等效：PPT `title 28pt` ≈ Doc `title 22pt` ≈ HTML `title 32px`（按 1m 视距测算）                                 |
| **数据一致**       | 同一数据点在三载体下数值 / 单位 / 口径必须完全一致                                                                                                 |
| **缺口标记一致**     | gap 标识符（如 `GAP-001`）在三载体下命名一致                                                                                                |
| **来源编号一致**     | 引用 id（如 `[1] report.pdf §3.2`）在三载体下完全一致                                                                                      |
| **图表配色一致**     | 同 brand 下三载体图表色板必须取自同一 `color.chart.palette[]`                                                                               |
| **token 名字一致** | 共享 token 骨架（`color.brand.primary` / `font.size.title` 等）在三载体的 `style_tokens` 中**名字必须一致**，**取值**按各载体量化表                       |

### 载体差异速查（避免混淆）

| 维度          | PPT                          | Document                | HTML             |
| ----------- | ---------------------------- | ----------------------- | ---------------- |
| 字号单位        | pt                           | pt                      | px               |
| 字号 title    | 28pt                         | 22pt                    | 32px             |
| 字号 body     | 14pt                         | 11pt                    | 16px             |
| 字号 footnote | 9pt                          | 8pt                     | 12px             |
| 字重 bold     | 600                          | 700                     | 600              |
| 行距 normal   | 1.4                          | 1.5                     | 1.6              |
| 间距单位        | px                           | cm                      | px               |
| margin      | 48px                         | 2.5cm                   | 24px             |
| 栏数          | 12                           | 1                       | 12               |
| 品牌色         | #1A3A6E                      | #1A3A6E                 | #1A3A6E          |
| 强调色 success | #2E7D32                      | #2E7D32                 | #3FBF6F（屏幕明亮）    |
| 图表类型        | 含 lollipop / quadrant_3group | bar_horizontal / pie 慎用 | 全部可交互            |
| 表格          | 无斑马纹                         | 全框                      | sticky top + 斑马纹 |
| Logo        | 角落                           | 页眉 / 页脚（每页）             | 顶部 nav 旁         |
| 视频          | 嵌入                           | 不推荐                     | 嵌入               |
| 动画          | 克制（fade / build）             | 无                       | 完整（折叠/展开 ≤0.3s）  |
| 响应式         | 无                            | 无                       | 6 断点             |
| 主题切换        | 无                            | 无                       | light / dark 双主题 |
| 脱敏          | 仅内部                          | 仅内部                     | **外发强制**         |
| 键盘导航        | 无                            | 无                       | **强制**           |
| 加载性能        | 离线                           | 离线                      | LCP ≤ 2.5s       |

---

## Failure conditions

- artifact 格式与 active capability 冲突；
- 为排版修改或删除上游结论；
- 丢失来源、口径、关键限定条件或阻断缺口；
- 只有格式建议，没有正式材料单元；
- 未真实渲染却声称 completed；
- 同一产物混入两种或三种载体结构。
- **呈现形式违反业务规则**（如未脱敏金额、品牌色不一致、可访问性不达标）；
- **呈现形式违反载体特有规则**（如 PPT 含 cube 切换 / Doc 表格跨页断行 / HTML 焦点态不可见 / HTML 外发未脱敏）；
- **跨载体一致性破坏**（如 PPT 与 HTML 的 brand.primary 不一致、数据口径不同）；
- **可访问性不达标**（a11y：对比度 < 4.5:1 / 字号 < 12px / 键盘不可达）。

---

## v0 → v0.1 合并 diff

| 类别                             | 项                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **未变（v0 原样承接）**                | v0 全部 75 行 core 结构（frontmatter 主体 / Role 主体 / Input readiness / 5 步 workflow / 6 条 invariants / 14 顶层字段 / 12 单元字段 / 6 条 failure）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| **新增（capabilities）**           | `## Format capabilities` 章节（\_index 命名空间与选型 + 共享规范 14 字段规则 + **共享 token 骨架** + 跨载体通用渲染前置 + 跨载体失败处置 + format.ppt 12 layout / format.document 10 document_role / format.html 5 内部结构 + 三 capability 的 renderer handoff 契约）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **新增（呈现形式规则，下沉到各 capability）** | **不再有独立 `## 呈现形式规则` 板块**。呈现形式规则完整融入各 capability 内部：· `format.ppt` 包含 PPT 量化 typography / color（含 three_way 色板）/ spacing / chart（含 lollipop_grouped / quadrant_3group 特有类型）/ table / asset / PPT 特有规则（动画克制 / 信息密度 / 口播时长 / 位置标记 / 模板变量）· `format.document` 包含 Document 量化 typography（serif 默认、字号小 1 档、行距宽、bold 700）/ color（不用品牌色做表头、强调色保守）/ spacing（cm 单位、1 栏）/ chart（bar_horizontal 优先、lollipop 不强制）/ table（全框 + 斑马纹）/ asset（200dpi、Logo 每页、video 不推荐）/ Document 特有规则（A4 纸张 / 页眉页脚每页 / TOC / 跨页表格续表 / 罗马+阿拉伯页码 / 模板变量）· `format.html` 包含 HTML 量化 typography（系统字体优先、字号最大、行距最宽）/ color（light/dark 双主题、强调色明亮）/ spacing（px、gutter 加大）/ chart（全部可交互、tooltip 与下钻）/ table（sticky top、hover tooltip）/ asset（双倍图、Logo 顶部）/ HTML 特有规则（6 断点响应式 / 5 元素交互态 / 键盘导航 / 强制脱敏 6 类 / 双主题切换 / 加载性能 LCP / 模板变量） |
| **新增（跨载体协同）**                  | `## 跨载体协同` 章节（rule 优先级 4 条 + 一致性约束 7 条 + **载体差异速查表 18 维**），位于三个 capability 之后                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| **微调**                         | frontmatter 加 `version: v0.2` 与 extends 三 capability；Role 段落补"以及具体的呈现形式规则"与"各 capability 自带"；workflow 升级为 6 步（前置 step 0），step 2 改"该 capability 内部的呈现形式子节"；invariants 在 v0 6 条基础上新增第 7 条"业务规则优先"，引用 `## 跨载体协同`；output contract `style_tokens` 改"取值由 active capability 呈现形式子节定义"；`layout_or_structure` 补 `presentation_style_ref` 引用"active capability 呈现形式子节中的具体 token"；failure 在 v0 6 条基础上新增 4 条与呈现形式相关                                                                                                                                                                                                                                                                                                                                                                                    |
| **关键设计决定**                     | 1) 共享 token 骨架（名字 + 含义）但**量化值差异化**——三载体在字号单位、字号大小、字重、行距、间距单位、品牌色用法、图表类型、动画 / 交互 / 脱敏 等维度有**本质差异**，不能强行统一；2) 跨载体一致性通过**载体差异速查表**约束同 brand 下的视觉等效；3) PPT 特有的 `lollipop_grouped` / `quadrant_3group` chart 不强制 Document / HTML 使用（可借调但需理由）；4) HTML 强制脱敏是**外发硬约束**，PPT / Document 仅有内部使用场景                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |

## v0.4 → v0.5 diff

| 类别 | 变更项 |
|---|---|
| **format.ppt layout 库** | 从 12 个 `layout_type` 减至 **10 个**：删除 `swot`（可用 `matrix_2x2` 或 `pyramid` 替代）、删除 `appendix`（附录内容并入 `discussion_action` 或单独 appendix Unit）；新增**禁止声明**：`目录页`和`章节分隔页`不在库中，format worker 不得生成 |
| **§7.1 页面类型表** | `executive_summary` 触发场景从"必在 page 2 或 3"改为"**必在 page 2（封面后一页）**"，作为后续 slides 的核心观点总结；表格顶部新增**禁止页面类型**提示框 |
| **§7.12 新增** | 全新小节「页面内容强制规则」：**每页必须有图/表/形状，禁止纯文字页**。含：核心禁令（7.12.1）、视觉元素检查清单 6 项（7.12.2）、纯文字页整改方案 5 档优先级（7.12.3）、Quality Check 条目 `FMT-FM-PPT-NO-TEXT-ONLY-001`（7.12.4） |
| **字段填写规则** | format.ppt 的 `layout_type` 选填说明从"从上表 12 个选"改为"从上表 10 个选" |
| **McKinsey 注释** | §7.1–§7.12 范围更新，新增对 §7.12 的说明：vS.pdf 所有 23 页均无纯文字页，此规则从实际案例提炼 |

> **v0.5 版本说明**：本次修改来自用户反馈（2025-07-01），针对 PPT 呈现形式的三条硬性约束。修改后 format worker 生成的 PPT 将：① 无目录页/章节分隔页；② 封面后必须有核心发现页（page 2）；③ 每页必有视觉元素（图/表/形状），从规则层面杜绝纯文字页。

## v0.5 → v0.6 diff

| 类别 | 变更项 |
|---|---|
| **§7.6 图表类型库扩展** | 从 v0.5 限制的"6 类图表"恢复为**全面图表库**：移除"应限制在这 6 类之内"的 narrowing 语言；新增 §7.6.0 图表类型决策表（16 种数据形态 → 首选/备选图表）；新增 8 个图表类型详细规范（§7.6.7–§7.6.14）：柱状图（通用）、折线图、散点图/气泡图、瀑布图、漏斗图、金字塔图、堆叠柱状图、饼图/环形图；原有 6 类保留为 vS.pdf 案例参考 |
| **§7.11 下游交接清单** | 新增变量 #12 `user_template_path`（string，可选）：用户 PPT 模板 .pptx 路径；非空时 renderer 加载该模板的母版页、配色、字体并适配输出 |
| **§7.13 新增** | 全新小节「用户模板适配规范」：模板接入方式（7.13.1）、模板元素提取与映射（7.13.2）、映射优先级 4 档（7.13.3）、模板适配工作流（7.13.4）、模板适配 Quality Check 5 项（7.13.5） |
| **§7.6.0 决策表** | 新增：数据形态 → 图表类型决策表，format worker 先查表选类型再按对应小节执行详细规范 |
| **纯文字页整改** | §7.12 保持不变；§7.6 图表库扩展后，§7.12.3 的 P0 优先级"添加 chart_spec"现在有更全面的图表类型可选 |

> **v0.6 版本说明**：本次修改来自用户反馈，针对 v0.5 的两处不足：① v0.5 的 §7.6 错误地将图表类型限制为 vS.pdf 中实际出现的 6 类；v0.6 恢复全面图表决策表 + 14 类详细规范，format worker 根据数据形态自由选用。② 新增用户模板适配机制（§7.13），支持 format worker 接受用户 .pptx 模板并适配输出。

## v0.6 → v0.7 diff

| 类别 | 变更项 |
|---|---|
| **Input readiness 新增** | 新增"数据真实性检查"规则：所有图表数据必须从原始文档提取，禁止模拟数据；新增 `data_source_extraction` 字段记录提取位置；发现面板洞察要点必须从文档提取或由 AI 生成，禁止手动编写无依据洞察 |
| **§7.8 布局约束规则（7.8.1 新增）** | 文本溢出预防（发现面板高度检查、表格单元格换行、文本框最大字符数、标题最大长度）；形状重叠预防（导航栏标签宽度动态计算、KPI 卡片文本位置调整、发现面板要点数量限制）；布局错位预防（多表格布局宽度检查、图表位置间距检查、页面安全区约束）；位置属性验证（异常值检测、边界检查） |
| **§7.12 文本溢出预防（7.12.5 新增）** | 6 项文本溢出预防检查（发现面板内容高度、表格单元格换行、文本框最大字符数、页面标题最大长度、发现面板要点数量、KPI 卡片文本溢出）；文本溢出修复流程（启用 word_wrap → 减小字体 → 拆分文本框 → 省略文本） |
| **§7.4 颜色对比度** | 已有规则（7.4.5 #1：对比度 ≥ 4.5:1）保持不变 |
| **§7.9 字体回退检查（7.9.1 新增）** | 字体存在性检查、Fallback 字体检查、中文字体渲染检查、字体回退机制；提供 Python 代码示例（使用 matplotlib.font_manager 检查字体） |
| **§7.11 错误处理和日志（7.11.1、7.11.2 新增）** | 数据验证、位置属性验证、异常处理（try-except）、图表数据检查；日志级别（DEBUG/INFO/WARNING/ERROR）、日志内容、日志输出、日志格式；提供 Python 代码示例（safe_add_shape、logging 配置） |
| **§7.14 Renderer 实现质量规范（新增）** | 避免硬编码位置和尺寸（使用常量、禁止魔法数字、相对位置）；减少重复代码（BaseSlideRenderer 基类、模板方法模式）；配置外部化（配置文件、配置字典）；模块化设计（拆分模块、推荐目录结构） |
| **版本号** | v0.6 → v0.7 |
| **文件末尾** | 新增本 v0.6 → v0.7 diff 章节 |

> **v0.7 版本说明**：本次修改来自 QA 检查报告（对 `render_high_density.py` 生成的高密度版 PPTX 的系统性检查）。针对发现的 5 类绘制卡点（模拟数据、手动编写洞察、示例文本、硬编码配色、字体回退不明确）和 6 个输出警告（位置属性异常），在 SKILL 中新增针对性规则，从规范层面防止这些问题。同时新增 §7.14 Renderer 实现质量规范，提高 renderer 代码质量。

---

## §7.15 MckEngine API 参数格式速查表（基于 engine.py 源码）

> **⚠️ 关键提示**：`references/framework/engine-api.md` 文档中的参数格式可能**与实际代码不一致**。本节记录从 `mck_ppt/engine.py` 源码中确认的**正确参数格式**。在编写 `render.py` 时，如遇疑问，**必须查看 engine.py 源码**确认参数格式。

### 7.15.1 颜色参数处理

**问题**：JSON 无法存储 `RGBColor` 对象，`content.json` 中的颜色值只能是字符串（如 `"NAVY"`），但 MckEngine API 要求的颜色参数必须是 `RGBColor` 对象。

**解决方案**：在 `render.py` 中添加颜色转换辅助函数：

```python
from pptx.util import RGBColor

# 颜色字符串到 RGBColor 对象的映射
COLOR_MAP = {
    'NAVY': RGBColor(0, 51, 102),
    'WHITE': RGBColor(255, 255, 255),
    'BLACK': RGBColor(0, 0, 0),
    'BG_GRAY': RGBColor(245, 245, 245),
    'LINE_GRAY': RGBColor(220, 220, 220),
    'MED_GRAY': RGBColor(136, 136, 136),
    'DARK_GRAY': RGBColor(51, 51, 51),
    'ACCENT_BLUE': RGBColor(30, 111, 224),
    'ACCENT_GREEN': RGBColor(46, 125, 50),
    'ACCENT_ORANGE': RGBColor(255, 152, 0),
    'ACCENT_RED': RGBColor(211, 47, 47),
    'LIGHT_BLUE': RGBColor(232, 240, 250),
    'LIGHT_GREEN': RGBColor(232, 245, 233),
    'LIGHT_ORANGE': RGBColor(255, 235, 205),
}

def get_color(color_val):
    """将颜色值（RGBColor 或字符串）转换为 RGBColor 对象"""
    if not isinstance(color_val, str):
        return color_val  # 已经是 RGBColor 对象
    if color_val in COLOR_MAP:
        return COLOR_MAP[color_val]
    return RGBColor(0, 51, 102)  # 默认返回 NAVY
```

### 7.15.2 布局方法参数格式（常用 14 个）

> 每个方法列出：**正确参数格式** + **常见错误** + **示例代码**

#### 1. `cover(title, subtitle='', author='', date='', cover_image=None)`

**参数格式**：全部为字符串

**content.json 格式**：
```json
{
  "idx": 1,
  "layout": "cover",
  "title": "标题",
  "subtitle": "副标题",
  "author": "作者",
  "date": "日期"
}
```

#### 2. `executive_summary(title, headline, items, source='')`

**参数格式**：
- `items`: 列表，每个元素是 `[数字字符串, 标题, 描述]` 三元组

**✅ 正确格式**：
```json
{
  "idx": 2,
  "layout": "executive_summary",
  "title": "标题",
  "headline": "副标题",
  "items": [
    ["1", "要点1标题", "要点1描述"],
    ["2", "要点2标题", "要点2描述"]
  ],
  "source": "来源"
}
```

**❌ 错误格式**（字典列表）：
```json
"items": [
  {"num": "1", "item_title": "...", "desc": "..."}
]
```

#### 3. `metric_cards(title, cards, source='')`

**参数格式**：
- `cards`: 列表，每个元素是 `[字母, 标题, 描述]` 三元组
- 可选格式：`(字母, 标题, 描述, 强调色, 浅色背景)` 五元组

**✅ 正确格式**：
```json
{
  "idx": 3,
  "layout": "metric_cards",
  "title": "标题",
  "cards": [
    ["A", "指标1", "描述1"],
    ["B", "指标2", "描述2"]
  ],
  "source": "来源"
}
```

**❌ 错误格式**（字典列表）：
```json
"cards": [
  {"label": "总样本", "value": "4,174", "unit": "份"}
]
```

#### 4. `three_stat(title, stats, detail_items=None, source='')`

**参数格式**：
- `stats`: 列表，每个元素是 `{"label": "...", "value": "...", "detail": "..."}` 字典

**✅ 正确格式**：
```json
{
  "idx": 4,
  "layout": "three_stat",
  "title": "标题",
  "stats": [
    {"label": "豆包", "value": "54%", "detail": "用户数 3,968"},
    {"label": "DS", "value": "34%", "detail": "用户数 3,607"},
    {"label": "元宝", "value": "19%", "detail": "用户数 2,771"}
  ],
  "source": "来源"
}
```

#### 5. `table_insight(title, headers, rows, insights, col_widths=None, insight_title='启示：', source='', bottom_bar=None)`

**参数格式**：
- `headers`: 字符串列表
- `rows`: 字符串列表的列表
- `insights`: 字符串列表

**✅ 正确格式**：
```json
{
  "idx": 5,
  "layout": "table_insight",
  "title": "标题",
  "headers": ["列1", "列2", "列3"],
  "rows": [
    ["行1列1", "行1列2", "行1列3"],
    ["行2列1", "行2列2", "行2列3"]
  ],
  "insights": ["洞察1", "洞察2", "洞察3"],
  "source": "来源"
}
```

#### 6. `funnel(title, stages, source='')` ⚠️ **已废弃（RETRED）**

**参数格式**：
- `stages`: 列表，每个元素是 `(名称, 计数标签, 百分比浮点数)` 三元组
- **注意**：此方法已标记为"RETRED"（废弃），但代码仍然可用

**✅ 正确格式**：
```json
{
  "idx": 7,
  "layout": "funnel",
  "title": "标题",
  "stages": [
    ["三栖用户", "2,128", 0.35],
    ["仅DS+元宝", "172", 0.12]
  ],
  "source": "来源"
}
```

**❌ 错误格式**（字典列表）：
```json
"stages": [
  {"label": "三栖用户", "value": "2,128", "detail": "留存率中等"}
]
```

#### 7. `grouped_bar(title, categories, series, data, max_val=None, y_ticks=None, summary=None, source='')`

**参数格式**：
- `series`: 列表，每个元素是 `(系列名称, RGBColor对象)` 二元组
- `data`: 二维列表，`data[类别索引][系列索引] = 数值`
- **⚠️ 不支持 `bottom_bar` 参数**（与 `table_insight` 不同）

**✅ 正确格式**（content.json）：
```json
{
  "idx": 8,
  "layout": "grouped_bar",
  "title": "标题",
  "categories": ["类别1", "类别2", "类别3"],
  "series": [
    ["系列1", "NAVY"],
    ["系列2", "ACCENT_BLUE"],
    ["系列3", "ACCENT_GREEN"]
  ],
  "data": [
    [0.224, 0.158, 0.131],
    [0.213, 0.119, 0.079],
    [0.204, 0.100, 0.101]
  ],
  "max_val": 0.25,
  "source": "来源"
}
```

**render.py 中需要转换颜色**：
```python
# 转换 series 格式：从 [name, color_str] 到 (name, RGBColor)
series_converted = []
for item in slide['series']:
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        name, color_val = item[0], item[1]
        series_converted.append((name, get_color(color_val)))
    else:
        # 如果只有 name，自动分配颜色
        default_colors = [NAVY, ACCENT_BLUE, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_RED]
        idx = len(series_converted)
        series_converted.append((item, default_colors[idx % len(default_colors)]))

eng.grouped_bar(
    title=slide['title'],
    categories=slide['categories'],
    series=series_converted,
    data=slide['data'],
    max_val=slide.get('max_val', 1.0),
    source=slide.get('source', '')
)
```

**❌ 错误格式**（`series` 为字符串列表）：
```json
"series": ["可靠性", "可用性", "速度/稳定性"]
```

**❌ 错误调用**（传递不支持的 `bottom_bar` 参数）：
```python
eng.grouped_bar(
    ...,
    bottom_bar=slide.get('bottom_bar')  # ❌ 此方法不支持 bottom_bar
)
```

#### 8. `horizontal_bar(title, items, summary=None, source='')`

**参数格式**：
- `items`: 列表，每个元素是 `(名称, 百分比整数0-100, RGBColor对象)` 三元组

**✅ 正确格式**（content.json）：
```json
{
  "idx": 12,
  "layout": "horizontal_bar",
  "title": "标题",
  "items": [
    ["豆包-文本不满", 44, "NAVY"],
    ["DS-文本不满", 57, "ACCENT_BLUE"],
    ["元宝-文本不满", 62, "ACCENT_GREEN"],
    ["元宝-功能不满", 31, "ACCENT_ORANGE"]
  ],
  "source": "来源"
}
```

**render.py 中需要转换颜色**：
```python
# 转换 items 格式：从 [name, pct, color_str] 到 (name, pct, RGBColor)
items_converted = []
for item in slide['items']:
    if isinstance(item, (list, tuple)) and len(item) >= 3:
        name, pct, color_val = item[0], item[1], item[2]
        items_converted.append((name, pct, get_color(color_val)))

eng.horizontal_bar(
    title=slide['title'],
    items=items_converted,
    source=slide.get('source', '')
)
```

**❌ 错误格式**（使用 `bar_chart` layout，MckEngine 不支持）：
```json
{
  "layout": "bar_chart",  // ❌ MckEngine 没有此方法
  "categories": ["..."],
  "values": [44, 57, 62, 31]
}
```

#### 9. `action_items(title, actions, source='')`

**参数格式**：
- `actions`: 列表，每个元素是 `(行动标题, 时间线, 描述, 负责人)` 四元组

**✅ 正确格式**：
```json
{
  "idx": 14,
  "layout": "action_items",
  "title": "标题",
  "actions": [
    ["提升可靠性", "Q1 2026", "答案准确性、信源权威性", "产品团队"],
    ["抢占拍照答疑纯白", "立即", "功能纯白留存提升 10-17pp", "功能团队"]
  ],
  "source": "来源"
}
```

**❌ 错误格式**（字典列表）：
```json
"actions": [
  {"priority": "Exploit", "action": "提升可靠性", "detail": "答案准确性"}
]
```

#### 10. `four_column(title, items, source='')`

**参数格式**：
- `items`: 列表，每个元素是 `[数字字符串, 标题, 描述]` 三元组

**✅ 正确格式**：
```json
{
  "idx": 13,
  "layout": "four_column",
  "title": "标题",
  "items": [
    ["1", "标题1", "描述1"],
    ["2", "标题2", "描述2"],
    ["3", "标题3", "描述3"],
    ["4", "标题4", "描述4"]
  ],
  "source": "来源"
}
```

### 7.15.3 其他布局方法参数格式（简要）

> 以下方法较少使用，提供简要格式说明。详细格式请查看 `engine.py` 源码。

| 方法 | 关键参数格式 |
|---|---|
| `big_number(title, number, unit='', description='', detail_items=None, source='', bottom_bar=None)` | `number`: 字符串或数字 |
| `two_stat(title, stats, detail_items=None, source='')` | `stats`: `[{"label": "...", "value": "..."}, ...]` (2个元素) |
| `data_table(title, headers, rows, col_widths=None, source='', bottom_bar=None)` | `headers`: 字符串列表；`rows`: 字符串列表的列表 |
| `matrix_2x2(title, quadrants, axis_labels=None, source='', bottom_bar=None)` | `quadrants`: `[左上, 右上, 左下, 右下]` 四元素列表 |
| `pyramid(title, levels, source='', bottom_bar=None)` | `levels`: `[顶层, 上层, 中层, 底层]` 列表 |
| `process_chevron(title, steps, source='', bottom_bar=None)` | `steps`: `[(标签, 标题, 描述), ...]` 元组列表 |
| `timeline(title, milestones, source='', bottom_bar=None)` | `milestones`: `[(日期, 标题, 描述), ...]` 元组列表 |
| `vertical_steps(title, steps, source='', bottom_bar=None)` | `steps`: `[(编号, 标题, 描述), ...]` 元组列表 |
| `donut(title, segments, center_label='', center_sub='', source='')` | `segments`: `[(标签, 数值, 颜色), ...]` 元组列表，最多6段 |
| `pie(title, segments, source='')` | `segments`: `[(标签, 数值), ...]` 元组列表，最多6段 |
| `gauge(title, pct, label='', source='')` | `pct`: 0-100 的整数 |
| `line_chart(title, categories, series, data, source='', bottom_bar=None)` | `series`: `[(名称, 颜色), ...]` 元组列表 |

### 7.15.4 常见错误排查

| 错误信息 | 原因 | 解决方案 |
|---|---|---|
| `MckEngine.xxx() got an unexpected keyword argument 'bottom_bar'` | 此方法不支持 `bottom_bar` 参数 | 删除 `bottom_bar` 参数（`grouped_bar`、`horizontal_bar` 不支持） |
| `too many values to unpack (expected 2)` | `series` 格式错误，应该是 `[(name, color), ...]` 二元组列表 | 修改 `series` 格式为 `[[name, color_str], ...]`，并在 render.py 中转换颜色 |
| `assigned value must be type RGBColor` | 颜色参数是字符串，不是 RGBColor 对象 | 在 render.py 中添加颜色转换逻辑（见 §7.15.1） |
| `not enough values to unpack (expected 3, got 2)` | `items` 或 `stages` 格式错误，元组长度不对 | 检查格式是否为三元组/四元组 |
| `ModuleNotFoundError: No module named 'pptx'` | 未使用 mck-ppt 的 venv | 使用 `"C:/Users/zoezoezhao/.venvs/mck-ppt/Scripts/python.exe" render.py` 运行 |

### 7.15.5 推荐工作流

1. **编写 `content.json`** → 使用本节的正确格式
2. **运行 `gate_check_s3.py`** → 验证 content.json 格式 `python ~/.workbuddy/skills/mck-ppt-design/references/scripts/gate_check_s3.py content.json .`
3. **编写 `render.py`** → 包含颜色转换逻辑（§7.15.1）+ 正确调用 MckEngine API
4. **运行 `render.py`** → 使用 mck-ppt venv 的 Python 解释器
5. **如遇错误** → 查看 §7.15.4 常见错误排查，或直接查看 `engine.py` 源码确认参数格式
6. **运行 `gate_check.py`** → S4 QA 检查输出的 PPTX 质量

### 7.15.6 查看 engine.py 源码的快速参考

**文件路径**：`~/.workbuddy/skills/mck-ppt-design/mck_ppt/engine.py`

**快速查找方法签名**：
```bash
grep -n "def method_name" ~/.workbuddy/skills/mck-ppt-design/mck_ppt/engine.py
```

**示例**：查找 `grouped_bar` 方法：
```bash
grep -n "def grouped_bar" ~/.workbuddy/skills/mck-ppt-design/mck_ppt/engine.py
# 输出: 1691:    def grouped_bar(self, title, categories, series, data, max_val=None,
```

然后读取该方法实现（从行 1691 开始读取 50-100 行）确认参数格式。

---

## §8 专业咨询风格 PPT 设计规范（通用）

> **📌 来源**：本章节基于专业咨询公司（McKinsey/BCG）的 PPT 设计最佳实践，结合高质量人工绘制 PPT 与 AI 生成 PPT 的系统性对比分析。识别出 **9 大关键差距**，本节提供针对性的设计规范和实现指南。
>
> **⚠️ 适用范围**：当 `output_format=ppt` 时，format worker **必须** 遵循本章规范。这些规范是对 §7 的补充和增强，不是替代。本规范为通用风格，适用于各行业和各类型企业。

### 8.1 全局导航标签栏规范

#### 8.1.1 设计目的
- 帮助观众快速定位当前页面属于哪个分析维度
- 建立多维度分析的心理框架
- 提供视觉一致性，提升专业度

#### 8.1.2 实现要求

| 属性 | 规范 |
|------|------|
| **位置** | 从第 3 页（数据分析首页）起，每页顶部固定显示 |
| **高度** | 24-30px |
| **标签数量** | 3-6 个（根据分析维度确定）|
| **标签内容示例** | `人群 \| 纯白 \| 文本 \| 功能 \| 运营` |
| **激活状态样式** | 品牌色填充 + 白色文字（#0052D9 背景，白色文字）|
| **非激活状态样式** | 透明填充 + 灰色文字（#666666）|
| **字体** | 11-12px, 中文字体（如微软雅黑/思源黑体）|
| **圆角** | 标签圆角 4px |

#### 8.1.3 content.json 格式
```json
{
  "idx": 6,
  "layout": "analysis_page",
  "title": "发现1：产品A用户留存显著高于产品B",
  "navigation": {
    "tabs": ["维度1", "维度2", "维度3", "维度4", "维度5"],
    "active_tab": 0
  },
  "main_chart": { ... },
  "insights": [ ... ],
  "footnotes": [ ... ]
}
```

#### 8.1.4 render.py 实现模板
```python
def add_navigation_bar(slide, tabs, active_idx):
    """添加全局导航标签栏"""
    bar_height = Inches(0.35)
    bar_top = Inches(0.5)
    tab_width = Inches(1.2)
    tab_gap = Inches(0.15)
    start_left = Inches(0.5)
    
    for i, tab_name in enumerate(tabs):
        left = start_left + (tab_width + tab_gap) * i
        
        if i == active_idx:
            # 激活状态: 品牌主色填充
            shape = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                left, bar_top, tab_width, bar_height
            )
            shape.fill.solid()
            shape.fill.fore_color.rgb = BRAND_COLORS['primary']  # 品牌主色
            shape.line.fill.background()  # 无边框
            tf = shape.text_frame
            p = tf.paragraphs[0]
            p.text = tab_name
            p.font.color.rgb = RGBColor(255, 255, 255)  # 白色文字
            p.font.size = Pt(11)
            p.font.bold = True
            p.alignment = PP_ALIGN.CENTER
        else:
            # 非激活状态: 透明填充
            shape = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                left, bar_top, tab_width, bar_height
            )
            shape.fill.background()  # 透明
            shape.line.color.rgb = RGBColor(200, 200, 200)  # 浅灰边框
            tf = shape.text_frame
            p = tf.paragraphs[0]
            p.text = tab_name
            p.font.color.rgb = RGBColor(102, 102, 102)  # 灰色文字
            p.font.size = Pt(11)
            p.alignment = PP_ALIGN.CENTER
        
        # 设置圆角
        shape.adjustments[0] = 0.1  # 圆角半径比例
```

---

### 8.2 发现面板设计规范（🔴 P0 优先级）

#### 8.2.1 设计目的
- 提炼该页的核心洞察，帮助观众快速抓住重点
- 作为图表数据的"翻译"，降低理解门槛
- 提供结构化的要点总结

#### 8.2.2 实现要求

| 属性 | 规范 |
|------|------|
| **位置** | 每页右侧 20-25% 区域（或主图表下方 20% 区域）|
| **标题** | "发现" / "启示" / "关键洞察" / "核心结论" |
| **背景颜色** | 浅灰色 (#F5F5F5) 或浅蓝色 (#E8F4FD) |
| **边框** | 左侧 3px 品牌色竖线（#0052D9）|
| **圆角** | 4-6px |
| **内边距** | 12-16px |
| **内容格式** | 项目符号列表（• 或数字编号）|
| **每条长度** | 10-20 个汉字（不超过 2 行）|
| **条目数量** | 2-4 条/页 |
| **关键词高亮** | 加粗或用品牌色标注 |

#### 8.2.3 content.json 格式
```json
{
  "insights": [
    {
      "text": "纯白用户留存明显高于非纯白用户 10-18pp",
      "highlight_keywords": ["纯白用户", "10-18pp"],
      "type": "key_finding"
    },
    {
      "text": "纯白用户为 DS、元宝带来的留存率提升均高于豆包",
      "type": "supporting"
    }
  ]
}
```

#### 8.2.4 render.py 实现模板
```python
def add_insight_panel(slide, insights, left, top, width, height):
    """添加发现面板"""
    # 背景形状
    panel = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        left, top, width, height
    )
    panel.fill.solid()
    panel.fill.fore_color.rgb = RGBColor(245, 245, 245)  # 浅灰背景
    panel.line.fill.background()  # 无外边框
    
    # 左侧品牌色竖线（通过窄矩形模拟）
    accent = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        left, top, Inches(0.05), height
    )
    accent.fill.solid()
    accent.fill.fore_color.rgb = BRAND_COLORS['primary']  # 腾讯蓝
    accent.line.fill.background()
    
    # 标题文本框
    title_box = slide.shapes.add_textbox(
        left + Inches(0.15), top + Inches(0.1),
        width - Inches(0.2), Inches(0.3)
    )
    tf = title_box.text_frame
    p = tf.paragraphs[0]
    p.text = "发现"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = RGBColor(51, 51, 51)  # 深灰黑
    
    # 要点列表
    content_box = slide.shapes.add_textbox(
        left + Inches(0.15), top + Inches(0.45),
        width - Inches(0.2), height - Inches(0.55)
    )
    tf = content_box.text_frame
    tf.word_wrap = True
    
    for i, insight in enumerate(insights):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        
        p.text = f"• {insight['text']}"
        p.font.size = Pt(11)
        p.font.color.rgb = RGBColor(51, 51, 51)
        p.space_after = Pt(6)
```

---

### 8.3 散点图/气泡图规范（🔴 P1 优先级）

> **⚠️ 注意**：MckEngine **不支持**散点图/气泡图布局方法！如需使用散点图，必须通过 python-pptx 手动绘制或使用 matplotlib 生成图片后插入。

#### 8.3.1 适用场景
- 展示两个连续变量之间的关系（如 X vs Y）
- 对比多个产品在不同维度上的分布
- 识别聚类群组或异常值

#### 8.3.2 适用场景示例
- 展示两个连续变量之间的关系（如 X vs Y）
- 对比多个产品在不同维度上的分布
- 识别聚类群组或异常值

#### 8.3.3 必须包含的元素

| 元素 | 说明 |
|------|------|
| **X/Y 轴标签和单位** | 如 "留存提升 (pp)"、"满意度 (分)" |
| **数据点标注** | 每个点旁标注产品名称或图标（产品A=绿色圆圈, 产品B=蓝色三角, 产品C=浅蓝圆点）|
| **颜色编码** | 不同产品使用不同颜色/形状（与 §8.8 配色方案一致）|
| **椭圆圈选（可选）** | 用虚线椭圆圈出聚类群组，辅助解读 |
| **图例** | 右上角或底部，说明形状/颜色的含义 |

#### 8.3.4 render.py 手动绘制散点图模板（使用 python-pptx）
```python
from pptx.util import Inches, Pt, Emu
from pptx.enum.shapes import MSO_SHAPE
import math

def draw_scatter_plot(slide, data_points, x_label, y_label, 
                      left, top, width, height):
    """
    手动绘制散点图
    data_points: [
        {"name": "产品A", "x": 12, "y": 26, "color": "product_a", "shape": "circle"},
        {"name": "产品B", "x": 18, "y": 45, "color": "product_b", "shape": "triangle"},
        {"name": "产品C", "x": 15, "y": 32, "color": "product_c", "shape": "circle"},
        ...
    ]
    """
    # 计算数据范围
    x_values = [p['x'] for p in data_points]
    y_values = [p['y'] for p in data_points]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    
    # 添加边距（10%）
    x_range = x_max - x_min or 1
    y_range = y_max - y_min or 1
    x_pad = x_range * 0.1
    y_pad = y_range * 0.1
    
    # 绘制坐标轴区域
    chart_left = left + Inches(0.6)  # 留出 Y 轴标签空间
    chart_top = top
    chart_width = width - Inches(0.8)  # 减去轴标签空间
    chart_height = height - Inches(0.5)  # 减去 X 轴标签空间
    
    # 绘制每个数据点
    for point in data_points:
        # 将数据坐标转换为像素坐标
        px_x = chart_left + ((point['x'] - x_min + x_pad) / (x_range + 2*x_pad)) * chart_width
        py_y = chart_top + chart_height - ((point['y'] - y_min + y_pad) / (y_range + 2*y_pad)) * chart_height
        
        # 绘制数据点形状
        if point.get('shape') == 'circle':
            shape_size = Inches(0.15)
            dot = slide.shapes.add_shape(
                MSO_SHAPE.OVAL,
                px_x - shape_size/2, py_y - shape_size/2,
                shape_size, shape_size
            )
        elif point.get('shape') == 'triangle':
            shape_size = Inches(0.18)
            dot = slide.shapes.add_shape(
                MSO_SHAPE.ISOSCELES_TRIANGLE,
                px_x - shape_size/2, py_y - shape_size/2,
                shape_size, shape_size
            )
        else:
            shape_size = Inches(0.12)
            dot = slide.shapes.add_shape(
                MSO_SHAPE.OVAL,
                px_x - shape_size/2, py_y - shape_size/2,
                shape_size, shape_size
            )
        
        # 设置颜色
        color = get_brand_color(point.get('color', 'blue'))
        dot.fill.solid()
        dot.fill.fore_color.rgb = color
        dot.line.color.rgb = color
        
        # 添加数据标签
        label = slide.shapes.add_textbox(
            px_x + shape_size/2 + Inches(0.05),
            py_y - Inches(0.1),
            Inches(0.8), Inches(0.2)
        )
        tf = label.text_frame
        p = tf.paragraphs[0]
        p.text = point['name']
        p.font.size = Pt(9)
    
    # 绘制 X/Y 轴标签
    # ... (省略轴标签代码)
```

---

### 8.4 用户访谈引用框规范（🟡 P2 优先级）

#### 8.4.1 设计目的
- 增加定性研究的真实感和说服力
- 打破纯数据的单调感
- 提供用户视角的补充解释

#### 8.4.2 适用场景示例
- 引用用户原始反馈，增加定性研究的真实感
- 打破纯数据的单调感
- 提供用户视角的补充解释

#### 8.4.3 实现要求

| 属性 | 规范 |
|------|------|
| **样式** | 手写风格字体（如楷体/手写体）|
| **边框** | 不规则边框（轻微倾斜或波浪边缘，可用自由曲线模拟）|
| **背景颜色** | 浅黄色 (#FFFDE7) 或浅米色 (#FFF8E1)，模拟便签纸 |
| **内容** | 直接引用用户原始回答，**不修改措辞** |
| **底部信息** | 用户画像（性别/年龄/城市/职业）|
| **字体大小** | 引用文字 12-13px，画像信息 9-10px |

#### 8.4.4 content.json 格式
```json
{
  "user_quote": {
    "text": "一开始觉得产品A和产品B差不多就没下载。但试用后发现效果不错...",
    "user_profile": {
      "gender": "女",
      "age": 27,
      "city": "杭州",
      "occupation": "跨境电商"
    },
    "source": "深度访谈"
  }
}
```

---

### 8.5 高信息密度布局模板（🔴 P0 优先级）

#### 8.5.1 设计目标
将单页信息密度从当前的 **1x** 提升至 **3-5x**，达到咨询公司（McKinsey/BCG）的专业水准。

#### 8.5.2 推荐布局方案

##### 方案 A: 左图右文（最常用，~60%页面适用）

```
┌─────────────────────────────────────────────────────┐
│ [导航标签栏]                                        │
├────────────────────────┬────────────────────────────┤
│                        │                            │
│   [主图表区域]         │   [发现面板]               │
│   (60-70%)             │   (20-25%)                 │
│                        │                            │
│   图表/表格            │   • 发现 1                 │
│   含 pp 标注           │   • 发现 2                 │
│   含红框高亮           │   • 发现 3                 │
│                        │                            │
├────────────────────────┴────────────────────────────┤
│ [脚注区域] 注1: ... 注2: ...                       │
└─────────────────────────────────────────────────────┘
```

**适用场景**: 数据分析页、对比页

##### 方案 B: 三栏布局（~20%页面适用）

```
┌─────────────────────────────────────────────────────┐
│ [导航标签栏]                                        │
├──────────┬──────────┬──────────┬───────────────────┤
│          │          │          │                   │
│ [数据A]  │ [数据B]  │ [可视化] │ [发现面板]         │
│ (32%)    │ (32%)    │ (18%)    │ (18%)             │
│          │          │          │                   │
│ 表格/指标│ 表格/指标│ 小图表   │ • 发现 1          │
│          │          │          │ • 发现 2          │
├──────────┴──────────┴──────────┴───────────────────┤
│ [脚注区域]                                         │
└─────────────────────────────────────────────────────┘
```

**适用场景**: 多维对比分析（如学历×城市×职业交叉表）

##### 方案 C: 上下分层（~15%页面适用）

```
┌─────────────────────────────────────────────────────┐
│ [导航标签栏]                                        │
├─────────────────────────────────────────────────────┤
│ [上部: 概览/总览] (50%)                             │
│ ┌─────────────────┬─────────────────────────────┐   │
│ │ 主指标卡片       │ 辅助说明                   │   │
│ └─────────────────┴─────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│ [下部: 详细分析] (35%)                             │
│ ┌─────────────────────────────────────────────────┐ │
│ │ 图表/表格                                      │ │
│ └─────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│ [脚注区域] (15%)                                   │
└─────────────────────────────────────────────────────┘
```

**适用场景**: 方法论页、总结页

##### 方案 D: 纯文字结构化（~5%页面适用）

```
┌─────────────────────────────────────────────────────┐
│                                                    │
│  [标题]                                            │
│                                                    │
│  1. 发现 1: 标题                                   │
│     └─ 子要点 1.1                                  │
│     └─ 子要点 1.2                                  │
│                                                    │
│  2. 发现 2: 标题                                   │
│     └─ 子要点 2.1                                  │
│     └─ 子要点 2.2                                  │
│                                                    │
└─────────────────────────────────────────────────────┘
```

**适用场景**: 执行摘要（封面后第2页）、行动建议（最后一页）

#### 8.5.3 每页必须包含的元素清单

| 优先级 | 元素 | 是否必须 | 说明 |
|-------|------|---------|------|
| 🔴 必须 | 1 个主图表/表格 | ✅ | 核心数据可视化 |
| 🔴 必须 | 1 个发现面板 | ✅ | 2-4 条洞察要点 |
| 🔴 必须 | 页面标题 | ✅ | 清晰描述该页主题 |
| 🟡 推荐 | 导航标签栏 | ✅ | 第3页起每页必须有 |
| 🟡 推荐 | 1-2 条脚注 | ✅ | 数据来源或方法说明 |
| 🟢 可选 | pp 标注 | - | 百分点差异强调 |
| 🟢 可选 | 红框高亮 | - | 关键数值标记 |
| 🟢 可选 | 编号圆圈 | - | Top 3 重要发现 |
| 🟢 可选 | 用户访谈引用 | - | 定性数据支持 |

---

### 8.6 数据强调规范（pp 标注 / 红框高亮 / 编号圆圈）（🔴 P0 优先级）

#### 8.6.1 pp 标注（百分点差异）

**用途**: 直观展示两个数值之间的差异幅度，避免观众自己计算。

**格式规范**:

| 属性 | 正向差异 | 负向差异 |
|------|---------|---------|
| **格式** | `+Npp` | `-Npp` |
| **N 取值** | 整数（四舍五入）| 整数 |
| **字体** | 11-12px, 加粗 | 11-12px, 加粗 |
| **颜色** | 绿色 `#22C55E` | 红色 `#EF4444` |
| **位置** | 数据点附近（上/右/左），避免遮挡 | 同左 |

**vS PDF 示例**（Page 6）:
```
      +10pp              +18pp
   60% ●━━━━━ 产品纯白    45% ●━━━━━ 产品纯白
       │                    │
   50% ○ 非产品纯白       27% ○ 非产品纯白
```

#### 8.6.2 红框高亮（关键数值标记）

**用途**: 引导视觉焦点到关键数据点（最大值、最小值、异常值、重要发现）。

**格式规范**:

| 属性 | 规范 |
|------|------|
| **边框宽度** | 2px 实线 |
| **颜色** | 红色 `#EF4444` |
| **圆角** | 2-3px |
| **适用对象** | 表格单元格、KPI 卡片、数据标签 |
| **使用频率** | 每页 1-3 处（避免过度使用）|

**vS PDF 示例**（Page 7 表格）:
```
┌──────────┬──────────┬──────────┐
│  65%     │  51%     │          │  ← 普通数值
│  23%     │ [ 25% ]  │          │  ← 红框高亮（关键发现）
│  12%     │ [ 25% ]  │          │  ← 红框高亮（异常值）
└──────────┴──────────┴──────────┘
```

#### 8.6.3 编号圆圈（重要发现标记）

**用途**: 标记 Top 3 重要发现，建立阅读优先级。

**格式规范**:

| 属性 | 规范 |
|------|------|
| **形状** | 圆形 |
| **直径** | 18-20px |
| **填充色** | 品牌蓝 `#0052D9` |
| **文字** | 白色阿拉伯数字（①②③ 或 123）|
| **字体** | 11-12px, 加粗 |
| **位置** | 发现面板的每条要点前，或图表的关键位置 |

**content.json 格式**:
```json
{
  "insights": [
    {
      "number": 1,
      "text": "纯白用户留存率高出非纯白 10-18pp",
      "type": "top_finding"
    },
    {
      "number": 2,
      "text": "拍照答疑是最大功能杠杆（+16-17pp）",
      "type": "top_finding"
    }
  ]
}
```

---

### 8.7 脚注和注释系统规范（🟡 P2 优先级）

#### 8.7.1 设计目的
- 提供数据来源的可追溯性
- 解释关键定义和计算方法
- 增加报告的可信度和专业度

#### 8.7.2 实现要求

| 属性 | 规范 |
|------|------|
| **位置** | 每页底部固定区域（距底部 10-15px）|
| **区域高度** | 40-60px（根据脚注数量自适应）|
| **字体** | 9-10px |
| **颜色** | 灰色 `#888888` |
| **格式** | 以 `注N:` 开头，N 为序号（1, 2, 3...）|
| **每条独立一行** | 是 |
| **最大条数** | 4 条/页（超过可折叠为"查看更多"）|

#### 8.7.3 脚注内容类型

| 类型 | 示例 | 必要性 |
|------|------|--------|
| **数据来源** | "样本 N=4,174，来自问卷调查" | 🔴 必须 |
| **关键定义** | "强留存率定义为过去一周主用该产品的用户占比" | 🟡 推荐 |
| **计算方法** | "留存提升 pp = 产品A留存率 - 产品B留存率" | 🟡 推荐 |
| **符号说明** | "* 表示 p<0.05, ** 表示 p<0.01" | 🟢 可选 |
| **免责声明** | "数据截止日期: 2025.11.13" | 🟢 可选 |

#### 8.7.4 content.json 格式
```json
{
  "footnotes": [
    {
      "id": 1,
      "text": "样本量: 元宝 2,771, DS 3,607, 豆包 3,968"
    },
    {
      "id": 2,
      "text": "问卷实际分布基于各产品留存率..."
    },
    {
      "id": 3,
      "text": "纯白用户定义: 在使用当前AI产品之前，未使用过其他同类产品"
    }
  ]
}
```

---

### 8.8 通用品牌配色方案（🟡 P1 优先级）

#### 8.8.1 设计目的
- 建立 PPT 的品牌一致性和专业感
- 确保不同产品/维度之间的颜色区分清晰可辨
- 提供可定制的配色方案，适应不同企业品牌

#### 8.8.2 推荐配色方案（通用专业风格）

| 元素 | 名称 | 色值 | 用途 |
|------|------|------|------|
| **品牌主色** | 专业蓝 | `#0052D9` | 导航栏激活状态、强调元素、编号圆圈 |
| **产品A** | 成功绿 | `#22C55E` | 产品A相关数据点、条形图 |
| **产品B** | 深蓝 | `#2563EB` | 产品B相关数据点、条形图 |
| **产品C** | 浅蓝 | `#93C5FD` | 产品C相关数据点、条形图 |
| **正向差异** | 成功绿 | `#22C55E` | pp 标注的正值 |
| **负向差异/警告** | 警告红 | `#EF4444` | pp 标注的负值、红框高亮 |
| **面板背景** | 浅灰 | `#F5F5F5` | 发现面板背景 |
| **面板背景(可选)** | 浅蓝 | `#E8F4FD` | 发现面板备选背景 |
| **文本主色** | 深灰黑 | `#333333` | 标题、正文 |
| **文本辅色** | 中灰 | `#666666` | 辅助文本、非激活标签 |
| **边框线** | 浅灰 | `#E0E0E0` | 表格边框、分割线 |

**自定义配色**：用户可通过 `brand_colors` 字段在 `content.json` 中自定义配色方案。如不提供，使用上述默认配色。

#### 8.8.3 Python 常量定义（render.py 使用）

```python
# 品牌配色常量（必须在 render.py 顶部定义）
BRAND_COLORS = {
    'primary': '#0052D9',       # 腾讯蓝（品牌主色）
    'yuanbao': '#22C55E',       # 元宝绿
    'ds': '#2563EB',            # DS深蓝
    'doubao': '#93C5FD',        # 豆包浅蓝
    'success': '#22C55E',       # 正向差异
    'warning': '#EF4444',       # 警告/负面
    'panel_bg': '#F5F5F5',      # 面板背景
    'panel_bg_alt': '#E8F4FD',  # 面板背景备选
    'text_primary': '#333333',  # 主文本
    'text_secondary': '#666666',# 辅助文本
    'border': '#E0E0E0',        # 边框线
}

def hex_to_rgb(hex_color):
    """将十六进制颜色转换为 RGBColor 对象"""
    hex_color = hex_color.lstrip('#')
    return RGBColor(int(hex_color[:2], 16), int(hex_color[2:4], 16), int(hex_color[4:], 6))

def get_brand_color(color_name):
    """根据名称获取品牌色的 RGBColor 对象"""
    if color_name in BRAND_COLORS:
        return hex_to_rgb(BRAND_COLORS[color_name])
    return hex_to_rgb('#0052D9')  # 默认返回品牌主色（专业蓝）
```

**自定义配色方案**：用户可在 `content.json` 中通过 `brand_colors` 字段自定义配色，详见 §8.8.2。

#### 8.8.4 强制规则
- ❌ **禁止**随意修改颜色（除非有明确业务理由并获得审批）
- ✅ **必须**使用 `get_brand_color()` 函数获取颜色
- ✅ **必须**确保同一产品/维度在不同页面中使用相同颜色
- ⚠️ **注意**：如果 MckEngine 内部方法不接受自定义颜色参数，可在渲染后手动调整形状颜色
- 🟢 **可选**：支持通过 `content.json` 的 `brand_colors` 字段自定义配色方案

---

### 8.9 页面结构与深度指南（🟡 P2 优先级）

#### 8.9.1 推荐页数公式

```
总页数 = 1(封面) + 1(执行摘要) + N_主题 × (2-3页/主题) + 1(总结) + 1(行动建议)

其中:
- N_主题 = 分析维度数量（通常 4-6 个）
- 2-3页/主题 = 每个维度的深度展开
```

#### 8.9.2 按 report_type 推荐页数

| report_type | 最小页数 | 推荐页数 | 最大页数 | 说明 |
|-------------|---------|---------|---------|------|
| **quick_sync** | 8 | 10-12 | 15 | 快速同步会，聚焦 Top 3 发现 |
| **business_progress** | 12 | 18-22 | 28 | 业务进度汇报，中等深度 |
| **deep_dive** | 20 | 28-35 | 40+ | 深度分析，完整证据链 |

#### 8.9.3 复杂主题拆分策略

对于重要主题（如"人群分析"、"文本满意度"等），建议拆分为 **2-3 页**：

**Page A: 核心发现页**
- 内容: 散点图/气泡图 + 发现面板 + pp 标注
- 目的: 展示该维度的核心洞察和高层次结论
- 布局: 方案 A（左图右文）

**Page B: 细分分析页**
- 内容: 多维交叉表 + 分组条形图 + 发现面板
- 目的: 展示细分人群/场景的差异
- 布局: 方案 B（三栏）或方案 A

**Page C: 深挖案例页（可选）**
- 内容: 用户画像 + 用户访谈引用 + 典型案例
- 目的: 通过定性数据增加真实感和说服力
- 布局: 方案 C（上下分层）或自定义

#### 8.9.4 完整 PPT 结构模板（以 deep_dive 为例）

```json
{
  "slides": [
    { "idx": 1, "type": "cover", "title": "..." },
    { "idx": 2, "type": "executive_summary", "title": "核心发现" },
    { "idx": 3, "type": "methodology", "title": "研究方法与数据来源" },
    { "idx": 4, "type": "definition", "title": "关键指标定义" },
    { "idx": 5, "type": "overview", "title": "数据概览" },
    
    // 主题1: 人群分析（3页）
    { "idx": 6, "type": "analysis", "dimension": "人群", "sub_type": "core_finding", "title": "发现1: ..." },
    { "idx": 7, "type": "analysis", "dimension": "人群", "sub_type": "detail", "title": "人群细分: ..." },
    { "idx": 8, "type": "analysis", "dimension": "人群", "sub_type": "case_study", "title": "典型案例: ..." },
    
    // 主题2: 文本满意度（2-3页）
    { "idx": 9, "type": "analysis", "dimension": "文本", "sub_type": "core_finding", "title": "发现2: ..." },
    { "idx": 10, "type": "analysis", "dimension": "文本", "sub_type": "detail", "title": "文本满意度细节: ..." },
    // ... 可能还有第 11 页
    
    // 更多主题...
    
    { "idx": "N-2', "type": "summary", "title": "总结发现" },
    { "idx": 'N-1', "type": "action_items", "title": "行动建议" },
    { "idx": 'N', "type": "appendix", "title": "附录" }  // 可选
  ]
}
```

---

## §8 补充: vS PDF 设计模式速查

### 模式使用频率统计

| 模式 | 使用频率 | 典型页面 | 适用场景 |
|------|---------|---------|---------|
| **A: 左图右文** | ~60% | Page 6, 7, 10, 15... | 数据分析页（最常用）|
| **B: 三栏布局** | ~20% | Page 5, 11, 16, 20 | 多维对比分析 |
| **C: 上下分层** | ~15% | Page 3, 4, 12, 21 | 方法论/总结页 |
| **D: 纯文字结构化** | ~5% | Page 2, 23 | 执行摘要/行动建议 |

### 选择决策树

```
开始选择布局模式
│
├─ 当前页面是执行摘要或行动建议？
│  └─ 是 → 使用模式 D（纯文字结构化）
│
├─ 当前页面需要展示 3 个及以上并列的数据集？
│  └─ 是 → 使用模式 B（三栏布局）
│
├─ 当前页面是方法论或总结页？
│  └─ 是 → 使用模式 C（上下分层）
│
└─ 其他情况 → 使用模式 A（左图右文，默认选择）
```

---

## v0.7 → v0.9 diff（待发布）

| 类别 | 变更项 |
|---|---|
| **§8 新增（整章）** | 基于 vS PDF 对比分析的 9 大差距，新增完整的「腾讯风格 PPT 设计规范」：§8.1 全局导航标签栏、§8.2 发现面板、§8.3 散点图/气泡图、§8.4 用户访谈引用框、§8.5 高信息密度布局模板（4种方案）、§8.6 数据强调规范（pp标注/红框/编号圆圈）、§8.7 脚注系统、§8.8 品牌配色方案、§8.9 页面结构与深度指南；附 vS PDF 设计模式速查表和选择决策树 |
| **影响程度** | 🔴 严重缺失项（#1 导航、#2 发现面板、#4 信息密度、#5 数据强调）已覆盖；🟡 部分缺失项（#6 访谈引用、#7 脚注、#8 配色、#9 页面深度）已覆盖 |
| **版本号** | v0.7 → v0.9（跳过 v0.8，因为 §8 是大章，直接升级到 v0.9）|

> **v0.9 版本说明（草案）**：本次修改来自对腾讯内部人工绘制的 vS PDF（23页）与 AI 生成 PPTX（14页）的系统性视觉对比分析。识别出 9 大关键差距，新增完整的 §8 章「专业咨询风格 PPT 设计规范（通用）」，涵盖导航系统、发现面板、图表类型扩展、信息密度提升、数据强调、品牌配色等核心要素。目标是将生成 PPT 的专业度和信息密度提升至咨询公司水准（3-5x 提升）。

> **v0.9.1 更新（通用化）**：将 §8 章从"腾讯专用"泛化为"通用专业咨询风格"，移除腾讯特定品牌元素（元宝/DS/豆包），使用通用术语（产品A/产品B/产品C）；配色方案支持自定义（通过 content.json 的 brand_colors 字段）；适用于各行业和各类型企业。

| 类别 | 变更项 |
|---|---|
| **§7.15 新增** | 全新小节「MckEngine API 参数格式速查表」：基于 engine.py 源码的正确参数格式；颜色参数处理（COLOR_MAP + get_color 辅助函数）；14 个常用布局方法的参数格式 + 常见错误 + 示例代码；其他布局方法简要格式；常见错误排查表；推荐工作流；查看 engine.py 源码的快速参考 |
| **版本号** | v0.7 → v0.8（待发布） |

> **v0.8 版本说明（草案）**：本次修改来自实际运行中的 5 类 MckEngine API 参数错误。`engine-api.md` 文档与实际代码不一致是主要痛点。新增 §7.15 提供基于源码的正确参数格式速查表，帮助 format worker 避免常见错误。同时提供颜色转换辅助函数和推荐工作流。

---

## v1.0 版本说明（正式版）

| 类别 | 变更项 |
|---|---|
| **通用化改造** | 将 §8 章从"腾讯专用"泛化为"通用专业咨询风格"：移除腾讯特定品牌元素（元宝/DS/豆包），使用通用术语（产品A/产品B/产品C）；配色方案支持自定义（通过 content.json 的 brand_colors 字段）；适用于各行业和各类型企业 |
| **§7.15 MckEngine API 速查表** | 新增完整的 API 参数格式速查表（14 个常用布局方法），基于 engine.py 源码的正确格式；颜色参数处理（COLOR_MAP + get_color 辅助函数）；常见错误排查表；推荐工作流 |
| **§8 专业咨询风格规范** | 新增完整的 PPT 呈现形式规范：§8.1 全局导航标签栏、§8.2 发现面板、§8.3 散点图/气泡图、§8.4 用户访谈引用框、§8.5 高信息密度布局模板（4种方案）、§8.6 数据强调规范（pp标注/红框/编号圆圈）、§8.7 脚注系统、§8.8 品牌配色方案、§8.9 页面结构与深度指南 |
| **QA 和稳定性** | 新增文本溢出预防规则（§7.12.5）、布局约束规则（§7.8.1）、字体回退检查规则（§7.9.1）、错误处理和日志要求（§7.11）、Renderer 实现质量规范（§7.14） |
| **数据真实性** | 新增数据提取规则（Input readiness）：禁止模拟数据，要求从原始文档提取真实数据；发现面板洞察要点必须从文档提取或由 AI 生成 |
| **版本号** | v0.9.1 → v1.0（正式版）|

### v1.0 版本亮点

1. **✅ 通用化完成**：适用于各行业和各类型企业，不再绑定腾讯特定品牌
2. **✅ API 参数格式明确**：基于源码的正确格式，避免常见错误
3. **✅ 完整的 PPT 呈现规范**：涵盖导航、发现面板、数据强调、配色等核心要素
4. **✅ 高质量保证**：文本溢出预防、布局约束、字体检查等多重保障
5. **✅ 数据真实性**：禁止模拟数据，确保所有数据来自原始文档

### v1.0 适用场景

- ✅ 各行业的数据分析汇报（金融/科技/制造/零售等）
- ✅ 企业内部业务分析（市场分析/用户研究/竞品分析）
- ✅ 咨询公司风格的专业汇报（McKinsey/BCG 水准）
- ✅ 高管汇报、董事会汇报、战略分析等高质量输出

> **v1.0 版本说明（正式版）**：本次版本在 v0.9.1 基础上完成通用化改造，将"腾讯专用"泛化为"通用专业咨询风格"，适用于各行业和各类型企业。同时整合了 v0.7 → v0.9.1 的所有改进（MckEngine API 速查表、PPT 呈现规范、QA 规则等），形成第一个正式稳定版本。推荐所有新项目使用 v1.0。

