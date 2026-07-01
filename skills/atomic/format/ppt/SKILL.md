---
name: ppt
description: Adapt report structure for a presentation with page-level claims, one question and conclusion per page, controlled length, and appendix split.
---

# PPT Format

Use this atomic capability only when `output_format=ppt`. Storyline units are pages and each page advances one claim.

## PPT 版式核心规则

### 1. 页面结构
- ❌ **不生成**目录页、章节分隔页（节省页面给正文内容）
- ✅ 封面后第一页必须是 **Execution Summary**，使用**分层论点树结构**（编号发现 + 缩进子发现，形成逻辑递进），禁止使用并列卡片

  ```
  发现1：纯白用户价值高但新增难度大
  └─ 发现1.1：打"功能纯白"是更可行的路径
  └─ 发现1.2：在非纯白用户中，迁移DS用户相对更加容易
  发现2：功能满意度驱动留存...
  ```
- ✅ 每页必须包含**至少一个视觉元素**（图表/表格/形状/矩阵），**禁止纯文字页**
- ✅ 图表类型选择不受限（柱状图/条形图/折线图/散点图/饼图/表格/矩阵等均可），根据数据特征选择最合适的方式。**散点图在展示"幅度 vs 比率"双维度时为首选**

### 2. 信息密度与版式多样性
- 每页由三个信息层级构成：
  - **行动标题**：页面最顶部，一句话结论（≤ 25 字）
  - **主视觉区域**：占据正文区 ~70%，包含图表/表格/矩阵等视觉元素
  - **来源与注释**：页面底部，标注数据来源、关键定义、计算方法
- **版式按内容类型匹配，禁止所有页面使用同一版式**。从 MckEngine 72 种布局中按内容类型和叙事目标选择：

  | 内容类型 | 推荐方案 | 可用 MckEngine 布局 | 占比参考 |
  |---------|---------|-------------------|---------|
  | **数据对比**（多实体/时间/维度） | 方案H: 图表类 | #37 Grouped Bar / #38 Stacked Bar / #39 Horizontal Bar / #50 Line Trend / #70 Stacked Area / #72 Multi-Bar Panel | ~25% |
  | **双变量分析**（幅度 vs 比率） | 方案J: 高级可视化 | #53 Bubble/Scatter / #49 Waterfall / #51 Pareto / #48 Donut / #64 Pie | ~15% |
  | **结构化多维度**（评分/对比/矩阵） | 方案CDF: 框架矩阵 | #13 2x2 Matrix / #19 Side-by-Side / #22 Traffic Light / #56 Harvey Ball / #54 Heat Matrix / #65 SWOT | ~20% |
  | **数据驱动叙事**（指标+图表+洞察） | 方案K: 仪表盘 | #57 Dashboard KPI+Chart+Takeaways / #58 Table+Chart+Factoids / #71 Table+Insight Panel | ~20% |
  | **流程/时间/层级** | 方案F: 时间流程 | #28 Timeline / #29 Vertical Steps / #30 Cycle / #31 Funnel / #16 Process Chevron / #15 Staircase / #67 Value Chain | ~10% |
  | **定性/引用/摘要** | 方案E: 内容叙事 | #23 Executive Summary / #25 Quote / #26 Two-Column / #27 Four-Column / #24 Key Takeaway / #34 Action Items | ~10% |

- **选择优先级**：内容类型 > 数据维度 > 叙事目标 > 布局可用性
- 每个布局对应 `layout_type` 字段，记录在 `format_decisions[].layout_rationale` 中
- 布局的具体参数和可调用方法参考 `references/mck-engine/engine-api.md`（67 个方法）和 `references/mck-engine/layout-catalog.md`（72 种布局详情）

- 正文页建议包含主视觉 + 2-4 条 insight + 脚注
- **用户原声引用应嵌入对应分析页**（作为论据支撑发现），而非独立成页

### 3. 数据真实性
- 所有图表数据（柱数值、折线坐标、表格单元格）必须从 `source_refs[]` 引用的原始文档中提取
- 禁止使用模拟数据、占位数据或示例数据填充图表
- 若原始文档中无对应数据，必须在 `gap_display.visible_note` 中声明"数据缺失"

### 4. 文本溢出预防
- 标题 ≤ 40 字（中文）
- 表格单元格启用 word_wrap，内容 ≤ 50 字符/单元格
- 发现面板/insight 要点数 ≤ 5 条，每点 ≤ 80 字符
- 文本框内容 ≤ 150 字符

### 5. 布局约束
- 使用安全区约束（距离幻灯片边界至少 0.5 英寸）
- 形状之间保持至少 0.1 英寸间距，防止重叠
- 多图表布局时确保宽度总和 ≤ 正文区域宽度

### 6. 专业咨询风格（推荐，适配用户模板时可按实际调整）
当输出给高管汇报、董事会汇报、战略分析等高要求场景时，建议采用以下增强规则：
- **全局导航标签栏**（推荐）：每页顶部显示分析维度标签，当前维度高亮
- **发现呈现多样化**（推荐）：不固定位置和格式，根据内容特性选择呈现方式：
  - 作为页标题（如"发现1：纯白用户强留存显著高于非纯白"）
  - 作为图表中的 pp 标注/数据标注嵌入
  - 作为侧边分析面板 + 引文框联动
  - 作为结构化引文框嵌入分析页
- **散点图优先用于双维度分析**（推荐）：当需要同时展示"幅度"和"率"两个维度时（如"强留存提升(pp) vs 强留存率(%)"），优先使用散点图，在同一图表中展示多个数据点的横纵坐标分布
- **数据强调**（推荐）：图表中关键数据点使用 pp 标注/高亮/编号圆圈等方式突出
- **配色方案**（推荐）：支持自定义（通过 `style_tokens.color`），不同产品/维度用不同颜色区分

## Renderer 实现指引

- 使用 `presentation_agent.vendor.mck_ppt.DeckBuilder` 路径保持编辑能力
- 实现时注意：
  - 避免硬编码位置和尺寸，使用常量或相对位置
  - 使用 try-except 捕获 API 错误，提供友好错误信息
  - 日志记录关键步骤，方便调试
  - 渲染后运行 QA 门禁检查输出质量

## 参考资源

| 资源 | 位置 | 说明 |
|------|------|------|
| **专业咨询风格指南** | `references/presentation_style_guide.md` | 导航栏、发现面板、数据强调、模板、配色方案 |
| **MckEngine API 文档** | `references/mck-engine/engine-api.md` | MckEngine 布局方法的完整 API 参考 |
| **布局目录** | `references/mck-engine/layout-catalog.md` | 所有可用布局类型说明 |
| **配色方案** | `references/mck-engine/color-palette.md` | 颜色定义和用法 |
| **品牌指南** | `references/mck-engine/brand-guide.md` | 品牌色和设计系统 |
| **呈现规范** | `references/mck-engine/presentation-convention.md` | 团队级 PPT 呈现约定 |

## 示例

| 示例 | 位置 | 说明 |
|------|------|------|
| **AI 产品留存分析** | `examples/retention-case1/README.md` | format skill 输出 vs 人工稿对比 |
| 人工绘制参考 | `examples/retention-case1/20251208_AI产品用户留存洞察_vS.pdf` | 23 页专业咨询风格 PPT |
| AI 生成输出 | `examples/retention-case1/AI_product_retention_analysis.pptx` | 使用 format skill v1.1 规则生成 |
| 源文档 | `examples/retention-case1/AI 产品用户留存分析_文档资料.pdf` | 原始调研报告 |
