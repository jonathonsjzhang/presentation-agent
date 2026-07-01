# PPT 呈现形式规范（format.ppt）

> 本节定义 `output_format=ppt` 时的 layout 库、字段填写规则、renderer 契约和呈现形式细则。
> 当 compiler 注入 `format.ppt` capability 时，以下规则生效。

## 能力边界

- **能做**：8–12 页（不超过 15 页）演示稿；每页一个 takeaway；图表用 native shape 渲染；动画克制。
- **不能做**：长篇论证、跨页细读、脚注密集引用、供会后反复翻阅的存档版本。

## Layout 库（10 个 `layout_type`）

| `layout_type` | 适用单元 | `hierarchy_map` 必含 | 触发 |
|---|---|---|---|
| `title_slide` | slide (cover) | `topic`, `subtitle` | 仅第 1 页 |
| `executive_summary` | slide | `primary`(1 句结论), `supporting`(≤3) | **必在 page 2**（封面后一页） |
| `action_title` | slide（默认） | `action_title`(1 句结论), `supporting`(1–2) | 大多数内容页 |
| `key_takeaway` | slide | `takeaway`(1 句), `evidence`(1) | 总结性单点页 |
| `pyramid` | slide | `top`(结论), `layers`(3–4) | 结构性框架 |
| `matrix_2x2` | slide | `quadrants[]`(4) | 战略定位/分类 |
| `funnel` | slide | `stages[]`(3–5) | 漏斗转化 |
| `waterfall` | slide | `start`, `deltas[]`, `end` | 数值分解 |
| `bar_chart` | slide | `chart_spec` | 横向比较 |
| `line_chart` | slide | `chart_spec` | 时间序列 |

**禁止类型**：目录页（directory page）和章节分隔页（section divider page）不在本 layout 库中。

## 字段填写规则（PPT 特化）

- `unit_type = "slide"`
- `layout_or_structure.layout_type` 必填，从上表 10 个选
- `layout_or_structure.reading_order` 数组顺序：标题 → 主体 → 来源脚注
- `visual_object`：数据页必填 `chart_spec`，框架页可选 `mck_api.template`
- `format_handoff_notes` 必备 `font_family`、`master_template`、`aspect_ratio`

## Renderer handoff 契约

- `render_plan.renderer = "mck_ppt_shape_native"`
- `deliverables[0]` = `{ "name": "<topic>.pptx", "format": "pptx", "renderer": "mck_ppt_shape_native" }`
- 高风险页必须列入 `manual_steps[]` 并配套 `appendix_units[]` 备份
- `quality_checks` 必含：所有 slide 单元 `layout_type` 非空 + `chart_spec` 数据可解析

## PPT 呈现形式细则

### 页面结构
- ❌ 不生成目录页、章节分隔页
- ✅ 封面后第一页必须是 **Execution Summary**
- ✅ 每页必须包含至少一个视觉元素（图表/表格/形状/矩阵），禁止纯文字页
- ✅ 图表类型选择不受限，根据数据特征选择最合适的方式

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
