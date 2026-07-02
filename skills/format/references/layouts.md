# §P-1 Layout 库（v0.9.1 实证有效的 5 类）

> **重要**：本 layout 库**只**收录 v0.9.1 实际渲染过的 5 类 layout。v3 旧版罗列的 20+ 类 layout（cube/quadrant_3group/lollipop/process_chevron/horizontal_bar 等）虽然写在文档里但**没有任何 renderer 真正调用过**，v3 起**禁止新增**，需要扩展必须先在 `evals/rubrics.json` 留出评估项。

## 1. layout_type 枚举（5 类）

| layout_type           | 中文名       | 适用场景       | 实证页（v0.9.1 case1） |
| --------------------- | -------- | ---------- | ----------------- |
| `cover`               | 封面 / 结论页  | 开篇 1 页 + 收尾 1 页 | P1, P16           |
| `executive_summary`   | 执行摘要      | 封面后置 1 页    | P2                |
| `analysis_dashboard`  | 主要分析页     | 6-8 页（主战场）  | P4-P11, P12-P13   |
| `methodology_or_strategy` | 方法论 / 行动建议 | 各 1 页      | P3, P14           |
| `priority_matrix`     | 优先级矩阵     | 收尾前 1 页     | P15               |

> **不要再用旧名**：`title_slide` / `action_title` / `key_takeaway` / `pyramid` / `funnel` / `bar_chart` / `bar_chart_horizontal` / `scatter_plot` / `heatmap_table` / `user_voice` / `action_items` / `closing_slide` ——这些是 v3 旧版命名的内部别名。v3 统一为以上 5 类。

## 2. 字段填写手册（每类 layout 必填字段）

### 2.1 `cover`（封面 / 结论页共用）

```json
{
  "unit_type": "cover",
  "headline": "AI 产品用户留存分析",
  "subtitle": "基于问卷数据的强留存、纯白用户、功能杠杆与运营召回洞察",
  "cover_meta": {
    "sample_size": "4,174",
    "subjects": "元宝 / DS / 豆包",
    "date_range": "2025.11.11-13"
  },
  "presentation_style_ref": "format.ppt §layout.cover"
}
```

- 背景：深色（默认 `color.navy` = #051C2C）
- 主标题：18-30pt 白色加粗
- 副标题：14pt 浅灰
- 装饰：右上 + 右下两个圆形（不同深浅的 navy / primary）作为视觉锚点
- 底部：左下角小字标注 skill 版本

### 2.2 `executive_summary`（执行摘要）— v3.2 改为纯文字结构化

```json
{
  "unit_type": "executive_summary",
  "headline": "核心发现：xxx",
  "subtitle": "封面后置 Execution Summary；后续页面围绕五个主题展开",
  "findings": [
    {
      "title": "留存格局清晰分层",
      "body": "豆包 54% > DS 34% > 元宝 19%，强留存差距已形成明显梯队。",
      "color_token": "color.brand.primary"
    }
  ],
  "navigation": { "tabs": ["总览", "人群", "文本", "功能", "运营", "建议"], "active_tab": 0 }
}
```

> **v3.2 关键变更**：v3.1 阶段 P2 = 5 个 card + 1 个 bar_chart 辅助图 + 1 个 insight_panel（混合方案 A）。**v3.2 起改为方案 D 纯文字结构化**——核心发现页是"观点罗列"性质，不放图表。原因：
> - 核心发现的目的是"让决策者 30 秒看完"，图表会拖慢阅读节奏
> - 5 个并列发现卡已经能传达全部信息，辅助图重复表达
> - insight_panel rail 仍保留，承担"翻译"功能（把卡里数据"再压缩"一次）
>
> **强制**：executive_summary 类型**禁止**添加 main_chart / auxiliary_chart 字段。renderer 看到该字段时应忽略并打 warning。
>
> **布局规范**（v3.2）：
> - 顶部 8%：标题区（title 18pt + subtitle 9.5pt muted）
> - 中部 8%：navigation tab
> - 主体 70%：左侧 60%（5 个 finding card 编号 + 标题 + body 垂直排列）+ 右侧 30%（insight_panel rail）
> - 底部 8%：脚注
> - 左右上下边距均为 0.7 inch（见 FMT-V3-009）

> **insight_panel 选型**：executive_summary 强制 **C-2-A right-rail**，因为 5 个 finding 卡需要"二次提炼"放在右侧。**禁止**用 callout-side（与 card 视觉冲突）、**禁止**用 top-banner（与标题区竞争）、**禁止**用 matrix-grid（exec_summary 维度单一）。

### 2.3 `analysis_dashboard`（主要分析页）—— **核心 6-8 页**

```json
{
  "unit_type": "analysis_dashboard",
  "headline": "留存总览：xxx",
  "subtitle": "可选副标题",
  "navigation": { "tabs": ["总览", "人群", "文本", "功能", "运营", "建议"], "active_tab": 0 },
  "main_chart": {
    "type": "bar_chart | grouped_bar | horizontal_bar | scatter | matrix_table | quoted_table",
    "data": { ... },
    "max_val": 60,
    "highlight_cells": [[0,1], [1,1]]
  },
  "side_legend": { "products": ["豆包", "DS", "元宝"] },
  "insight_panel": {
    "title": "关键洞察",
    "items": [
      "豆包强留存率为元宝 2.8 倍",
      "DS 居中但用户规模接近豆包",
      "元宝需先补齐可靠性底座"
    ]
  },
  "footer": {
    "source_note": "Page 1：强留存率、各产品使用用户数与渗透率。",
    "page_no": 4
  }
}
```

- 顶部 6-9%：navigation tab（**强制**）
- 标题区：0-12% 高（title 18pt + subtitle 9.5pt muted）
- 主体 65%：主图表（左 60-70%）+ **insight_panel（变体按 evidence_type 选，见下表）**
- 底部 8%：脚注（来源 + 页码）

**`main_chart.type` 6 种可选**（详见 `charts.md`）：
- `bar_chart`（垂直或水平条形）
- `grouped_bar`（分组条形）
- `horizontal_bar`（横向进度条形）
- `scatter`（散点图，纯 python-pptx 手动绘制）
- `matrix_table`（热力矩阵表）
- `quoted_table`（含红框高亮的表格）

> **insight_panel 变体选型（analysis_dashboard 核心决策）**：
> | evidence_type | 推荐变体 | 触发条件示例 |
> |---|---|---|
> | 多点并列洞察（无主次）| **C-2-A right-rail**（默认）| "豆包 X / DS Y / 元宝 Z" |
> | 关键反差点（单点对照）| **C-2-D callout-side** | "豆包 54% vs 元宝 19%，差距 35pp" |
> | 关联到图表某数据点 | **C-2-E inline-anchor** | "该柱 +25.2pp 是全图最高" |
> | 2-3 维度分类对比 | **C-2-F matrix-grid** | "按产品×优先级分类" |
> | 整页最关键 1-2 句话 | **C-2-B top-banner**（慎用）| 全页主轴结论 |
>
> **决策原则**：先判断 evidence 是"多点并列"还是"单点反差"——并列选 A，反差选 D；与图表某点强相关选 E；分类归类选 F；全页主轴才用 B。

### 2.4 `methodology_or_strategy`（方法论 / 行动建议）

```json
{
  "unit_type": "methodology_or_strategy",
  "headline": "研究方法：xxx",
  "process_steps": [
    { "num": "1", "label": "识别强留存" },
    { "num": "2", "label": "拆分纯白用户" },
    { "num": "3", "label": "评估文本/功能满意度" },
    { "num": "4", "label": "分析召回与流失" },
    { "num": "5", "label": "形成行动建议" }
  ],
  "metric_cards": [
    { "value": "4,174", "label": "总样本", "color_token": "color.brand.primary" }
  ],
  "navigation": { "tabs": [...], "active_tab": 0 }
}
```

- 顶部 25%：4 个 metric_cards（数据 / 标题 / 描述 / 强调色边）
- 中部 30%：process_steps（5 个编号圆圈 + 横向箭头）
- 行动建议变体：3 张路径卡（Exploit / Explore / Watch），每张含编号圆圈 + tag + 标题 + body

> **insight_panel 选型**：methodology_or_strategy 优先 **C-2-C bottom-takeaway**（行动建议 / 总结陈述），因为本页重点是"接下来做什么"，放在底部承接阅读节奏；不推荐 right-rail（与 process_steps 视觉竞争）。

### 2.5 `priority_matrix`（优先级矩阵）

```json
{
  "unit_type": "priority_matrix",
  "headline": "优先级矩阵：xxx",
  "axes": {
    "x_label": "实施复杂度",
    "y_label": "留存影响"
  },
  "quadrants": ["优先推进", "战略储备", "基础补齐", "暂缓"],
  "items": [
    { "name": "可靠性", "x": 1.4, "y": 1.2, "color_token": "color.brand.primary" }
  ]
}
```

- 二维矩阵：x 轴=实施复杂度 →, y 轴=留存影响 ↑
- 4 个象限底色（绿/橙/蓝/红浅色）
- 数据点：圆形 + 名称标签

> **insight_panel 选型**：priority_matrix 天然适合 **C-2-F matrix-grid**——把矩阵中"每个象限的 takeaway"组织成 2x2 卡片，与主图视觉一致。

## 3. 通用禁止（v3 起严格执行）

- ❌ **禁止**新增未实证的 layout_type。如果需要新模式（如 `dashboard_kpi_grid`），先在 `evals/rubrics.json` 添加评估项 → renderer 实现并 QA 通过 → 再加入本表。
- ❌ **禁止**使用 v3 旧名（cube/quadrant_3group/lollipop 等）。
- ❌ **禁止**在同一页混用 ≥ 3 种 chart type（视觉混乱）。
- ❌ **禁止**在 analysis_dashboard 跳过 navigation tab（即便 active_tab 是 0）。
- ❌ **禁止**在 executive_summary 类型的核心发现页放任何 chart/table 图表（v3.2 起强制；该页是"观点罗列"性质）。
- ❌ **禁止**任意两个视觉 shape 的 bounding box 重叠（FMT-V3-010 强制；常见反例见 §4）。

## 4. 统一边距与无重叠规则（v3.2 新增）

### 4.1 统一页边距

- 所有内部页面（executive_summary / analysis_dashboard / methodology_or_strategy / priority_matrix）的**上下左右边距 = 0.7 inch**（见 `references/style.md §4`）
- content 区域：x ∈ [0.7, 12.633], y ∈ [0.7, 6.8], w_max = 11.933, h_max = 6.1
- cover / closing 保留 0.55 inch 边距（特殊装饰）
- 配套规则：**FMT-V3-009**（强制页边距一致）

### 4.2 避免 shape 重叠（历史 bug 清单）

| 页 | 重叠内容 | 重叠区 | 修法（v3.2 实施） |
|---|---|---|---|
| P8 (text satisfaction) | inline-anchor (bx=3.20, by=1.45, bw=2.6, bh=0.55) vs grouped_bar (0.75-6.35, 1.75-5.40) | (3.20-5.80, 1.75-2.00) | anchor 移到 grouped_bar 右侧空白区 (bx=7.0, by=1.20, bw=2.6) |
| P13 (user voice) | 6 quote cards (0.75-9.85, 1.35-5.33) vs matrix_grid (0.58-12.58, 1.6-6.2) | 几乎全画面 | 重新分两栏：6 quotes 在左半 (x=0.7-6.0, w=5.3)，matrix 在右半 (x=6.3-12.633, w=6.3) |
| P5 (driver matrix) | callout (8.5, 4.6, 3.2, 1.4) vs emphasis frame (0.62, 4.88, 8.98, 0.82) | (8.5-9.60, 4.88-5.70) | callout 移到 (9.50, 4.6, 3.0, 1.4) 或 callout 改为 insight_panel 变体 |
| P2 (executive_summary) | bar_chart 与 insight_panel rail 在右侧叠加 | 整体视觉 | **去掉 bar_chart**（v3.2 改纯文字结构化） |

### 4.3 修法总原则

1. **优先重排而不是压缩**：当两个 shape 冲突时，先想"能不能分两栏"，再想"能不能缩小"
2. **anchor/quote/matrix 优先让位给 main_chart**：因为 main_chart 是页面焦点
3. **insight_panel rail 的位置**：x=10.78, w=1.86（与 v3.1 的 10.12/2.52 相比，压缩以适配新边距 0.7）
4. **avoid inline 元素与 main_chart 共用同一 y 区间**：anchor 类的 y 起点应在 main_chart 上方或下方至少 0.2 inch
