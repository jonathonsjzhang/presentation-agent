# PPT 呈现形式规范（format.ppt）

> 本节定义 `output_format=ppt` 时的版式规范，按 **功能层 → 形式层 → 图表层** 三层结构组织。
> 当 compiler 注入 `format.ppt` capability 时，以下规则生效。

## 能力边界

- **能做**：8–12 页（不超过 15 页）演示稿；每页一个 takeaway；图表用 native shape 渲染；动画克制。
- **不能做**：长篇论证、跨页细读、脚注密集引用、供会后反复翻阅的存档版本。

## 金字塔原则（贯穿全文）

**每一个论述页必须遵循金字塔原则**：
- **中心论点**（结论标题，≤40 字）：一句话回答"so what"
- **支持论点**（1-3 条 key insight）：为什么是这个结论
- **数据/证据**（图表/表格）：支持每个 key insight 的事实

---

## Layer 1: 功能层（4 类，决定页面在 PPT 中的位置）

| 功能类型 | schema layout_type | 页面位置 | 必含内容 |
|---------|-------------------|---------|---------|
| **封面页** Cover | `cover` | S1 | 标题、副标题、日期、品牌 |
| **执行摘要** Executive Summary | `executive_summary` | **S2（封面后一页，必填）** | 3-5 条核心发现，每条 1 句结论 + 关键数据 |
| **论述页** Argument | 多种 | 中间页（S3 ~ S(N-1)） | 中心论点 + 支持论点 + 证据（金字塔原则） |
| **结尾页** Closing | `closing` | **SN（末页）** | 行动建议（Exploit/Explore/Watch）或总结 |

**禁止类型**：`section_divider`（章节分隔页）、目录页（directory page）不在本 layout 库中。

---

## Layer 2: 形式层（论述页的版式选择）

论述页根据内容性质，从以下 8 种 McKinsey 经典版式中选择。每种版式都遵循"行动标题 → 主视觉 → 来源"三段结构：

| 形式 | 中文名 | schema layout_type | 适用场景 | 信息密度 |
|------|-------|-------------------|---------|---------|
| 左右结构 | L-R | `key_takeaway` | 数据分析对比（图表+发现面板）| 图表 60% + 面板 25% + 标题 10% + 脚注 5% |
| 图文结构 | Image-Text | `key_takeaway` | 概念解释 / 用户原声 | 文字 30% + 图片/形状 50% + 标题 15% + 脚注 5% |
| 表格结构一 | Table I | `data_table` | 2-3 列对比（短表+洞见）| 表格 65% + 洞见 25% + 脚注 10% |
| 表格结构二 | Table II | `data_table` | 多列明细（长表为主）| 表格 75% + 脚注 15% + 标题 10% |
| 流程结构 | Process | `process_chevron` | 步骤、漏斗、价值链 | 流程图 60% + 关键节点 30% + 脚注 10% |
| 矩阵结构 | Matrix | `matrix_2x2` | 四象限、SWOT、风险矩阵 | 矩阵 70% + 轴标签 + 脚注 |
| 引用结构 | Quote | `key_takeaway` | 用户原声 / 客户反馈 | 引言 50% + 署名/来源 30% + 上下文 20% |
| 列表结构 | List | `key_takeaway` | 优先级、Exploit/Explore | 列表 70% + 脚注 15% + 标题 15% |

**Layout 选择流程图**：
```
论述页要传达什么？
├─ 一个关键数据 → List / Big Number → key_takeaway
├─ 对比/分析 → 左右结构 / 表格结构 → key_takeaway / data_table
├─ 解释/例证 → 图文结构 / 引用结构 → key_takeaway
├─ 流程/步骤 → 流程结构 → process_chevron
├─ 分类/定位 → 矩阵结构 → matrix_2x2
└─ 多列数据 → 表格结构二 → data_table
```

---

## Layer 3: 图表层（在版式内选择具体图表）

| 图表类型 | MckEngine 方法 | schema layout_type | 适用数据 | 注意事项 |
|---------|---------------|-------------------|---------|---------|
| **柱状图（分组）** | `grouped_bar` | `grouped_bar` | 多品类×多时间点 | 最多 6 类 × 3 系列 |
| **柱状图（堆叠）** | `stacked_bar` | `grouped_bar` | 构成占比+对比 | 不超过 6 段 |
| **水平条** | `horizontal_bar` | `horizontal_bar` | 排名、长标签 | 单系列 |
| **折线图** | `line_chart` | `line_chart` | 时序趋势 | 2-5 系列 |
| **面积图（堆叠）** | `stacked_area` | `line_chart` | 累计趋势 | 区分堆叠 vs 折线 |
| **饼图** | `pie` | `pie` | 占比（≤6 段）| 段数过多改用堆叠柱 |
| **环形图** | `donut` | `donut` | 占比+中心标签 | 中间可放关键数字 |
| **瀑布图** | `waterfall` | `waterfall` | 数值分解 | start/deltas/end |
| **散点图** | `bubble` | `key_takeaway` | 两维分布 | z = 气泡大小 |
| **雷达图** | `scorecard` | `scorecard` | 多维度评分 | Harvey Ball 样式 |
| **数据表格** | `data_table` | `data_table` | 结构化数据 | 列数 ≤ 6 |
| **表格+洞见** | `table_insight` | `data_table` | ⭐ 开篇推荐 | 左表+右面板 |
| **大数字** | `big_number` | `key_takeaway` | 单一关键指标 | + 详细描述 |
| **四象限** | `matrix_2x2` | `matrix_2x2` | 战略定位 / 风险 | 配轴标签 |
| **金字塔** | `pyramid` | `process_chevron` | 层级结构 | 自顶向下 |
| **流程箭头** | `process_chevron` | `process_chevron` | 3-5 步流程 | 水平/垂直 |
| **价值链** | `value_chain` | `process_chevron` | 端到端流程 | 横向 |

**图表选择决策树**：
```
要表达什么关系？
├─ 数量对比 → 柱状图（grouped_bar / horizontal_bar）
├─ 占比构成 → 饼图 / 环形图 / 堆叠柱
├─ 趋势变化 → 折线图 / 面积图
├─ 数值分解 → 瀑布图
├─ 两维分布 → 散点图 / 气泡图
├─ 结构层级 → 金字塔
├─ 多维评分 → 雷达图 / 评分卡
└─ 明细查询 → 数据表格
```

---

## 完整版式 + 图表组合示例

| 页面 | 功能层 | 形式层 | 图表层 | schema layout_type |
|------|--------|--------|--------|-------------------|
| S1 | 封面 | — | — | `cover` |
| S2 | 执行摘要 | 列表结构 | — | `executive_summary` |
| S3 | 论述页 | 左右结构 | 柱状图（分组）| `grouped_bar` |
| S4 | 论述页 | 左右结构 | 柱状图（分组）| `grouped_bar` |
| S5 | 论述页 | 表格结构一 | 表格 | `data_table` |
| S6 | 论述页 | 左右结构 | 水平条 | `horizontal_bar` |
| S7 | 论述页 | 表格结构一 | 表格 | `data_table` |
| S8 | 论述页 | 流程结构 | 流程图 | `process_chevron` |
| S9 | 论述页 | 引用结构 | — | `key_takeaway` |
| S10 | 结尾页 | 列表结构 | — | `closing` |

---

## 字段填写规则（PPT 特化）

- `unit_type = "slide"`
- `layout_or_structure.layout_type` 必填，**按本规范 Layer 1 表选择**（与 schema formatted_material.v1 对齐）
- `layout_or_structure.reading_order` 数组顺序：标题 → 主体 → 来源脚注
- `visual_object`：数据页必填 `chart_spec`，框架页可选 `mck_api.template`
- `format_handoff_notes` 必备 `font_family`、`master_template`、`aspect_ratio`

## Renderer handoff 契约

- `render_plan.renderer = "mck_ppt_shape_native"`
- `deliverables[0]` = `{ "name": "<topic>.pptx", "format": "pptx", "renderer": "mck_ppt_shape_native" }`
- 高风险页必须列入 `manual_steps[]` 并配套 `appendix_units[]` 备份
- `quality_checks` 必含：所有 slide 单元 `layout_type` 非空 + `chart_spec` 数据可解析

---

## PPT 呈现形式细则

### 页面结构
- ❌ 不生成目录页、章节分隔页
- ✅ 封面后第一页必须是 **Execution Summary**
- ✅ 每页必须包含至少一个视觉元素（图表/表格/形状/矩阵），禁止纯文字页
- ✅ 论述页遵循金字塔原则（中心论点 → 支持论点 → 证据）

### 信息密度
- 每页三个信息层级：行动标题 → 主视觉区域 (~70%) → 来源与注释
- 正文页建议包含主视觉 + 2-4 条 insight bullet + 脚注

### 文本溢出预防
- 标题 ≤ 40 字（中文）
- 表格单元格启用 word_wrap，内容 ≤ 50 字符/单元格
- insight 要点数 ≤ 5 条，每点 ≤ 80 字符

### 布局约束
- 使用安全区约束（距边界 ≥ 0.5 英寸）
- 形状之间保持 ≥ 0.1 英寸间距防止重叠

## 专业咨询风格（推荐）

### 导航标签栏
每页顶部显示分析维度标签，当前维度高亮。

### 发现面板
每页右侧 20-25% 空间，显示 2-4 条关键洞察要点。

### 数据强调
- pp 标注：图表中直接用 `+Xpp`/`-Xpp` 标注差异值
- 红框/编号圆圈：标出关键数据点

### 脚注系统
每页底部标注：数据来源（必须）、关键定义（推荐）、计算方法（推荐）。

### 配色方案
支持自定义（通过 `style_tokens.color`），默认通用配色。

---

## 完整的 72 种版式模板库

完整版式库见 `references/mck_engine_catalog.md`，涵盖 13 个类别、72 种 MckEngine 方法。
本规范是基于该库 **按金字塔原则和功能/形式/图表三层**重新组织的子集。
