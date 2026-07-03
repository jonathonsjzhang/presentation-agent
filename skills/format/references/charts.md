# §P-4 图表库（Charts）

> v3 的图表库**只**收录 v0.9.1 渲染脚本实际实现过的 6 类。MckEngine 自带 layout 不在本表（v0.9.1 已验证：纯 python-pptx 手动绘制才是 v0.9.1 高质量产出的根因）。

## 1. 图表类型总览

| chart_type         | 中文名      | 适用场景          | 实证页（v0.9.1） |
| ------------------ | ------- | ------------- | ----------- |
| `bar_chart`        | 条形图      | 单维度对比（1-3 类）  | P2, P4, P12   |
| `grouped_bar`      | 分组条形     | 多类别 × 多系列     | P8, P11       |
| `horizontal_bar`   | 横向进度条形   | 长文本标签 / 进度感   | P5            |
| `scatter`          | 散点图      | 双维度分析         | P6            |
| `matrix_table`     | 矩阵表      | 多列对比 + 高亮     | P4, P9, P10   |
| `quoted_table`     | 引文表      | 含红框高亮         | (变体)         |

---

## 2. 详细规范

### 2.1 `bar_chart`（条形图）

**数据格式**：
```json
{
  "type": "bar_chart",
  "data": { "豆包": 54, "DS": 34, "元宝": 19 },
  "max_val": 60,
  "horizontal": false,
  "percent": true,
  "show_values": true
}
```

**视觉规范**：
- 垂直模式：bw = w / (n * 1.8), gap = bw * 0.8
- 横向模式：row_h = h / n, 进度条 0.18 inch 高
- 数值标签：垂直模式 13pt 加粗，水平模式 8.5pt 加粗
- 颜色：每个 name 映射到 `PCOL[name]`
- 基线：底部 0.01 inch 浅灰横线

### 2.2 `grouped_bar`（分组条形）

**数据格式**：
```json
{
  "type": "grouped_bar",
  "categories": ["豆包", "DS", "元宝"],
  "series": {
    "可靠性": [0.224, 0.158, 0.131],
    "可用性": [0.213, 0.119, 0.079]
  },
  "max_val": 0.25,
  "colors": ["color.brand.primary", "color.brand.product_b", "color.brand.orange"]
}
```

**视觉规范**：
- group_w = w / n_categories, bw = group_w / (n_series + 1.4)
- 每个 group 内：每个 series 占 1 bw，bw 实际宽度 = bw * 0.75
- 数值标签：6.7pt 中灰
- 图例：放在顶部 y - 0.28，每个图例 0.12×0.12 + 文字 7.5pt
- 基线：底部 0.01 inch 浅灰横线

### 2.3 `horizontal_bar`（横向进度条形）

**数据格式**：
```json
{
  "type": "horizontal_bar",
  "items": [
    ["拍照答疑", 21.0, "纯白"],
    ["深度思考", 20.2, "纯白"],
    ["速度及稳定性", 20.1, "5分满意"]
  ],
  "max_val": 21.0,
  "value_format": "+{:.1f}pp"
}
```

**视觉规范**：
- 每行 row_h = h / n
- 标签：左 0.95 inch，8.0pt
- 进度条：x + 1.0 起，宽 1.45 inch，高 0.14，圆角 0.12
  - 底色：RGB(237, 242, 247)
  - 填充色：`PCOL[name]`
- 数值：x + 2.50 起，宽 0.46，7.5pt 加粗 success
- 类型标签：x + 2.98 起，宽 0.45，6.6pt 中灰

### 2.4 `scatter`（散点图）

**数据格式**：
```json
{
  "type": "scatter",
  "points": [
    { "name": "豆包", "x": 10, "y": 60, "label": "+10pp", "shape": "circle" },
    { "name": "DS", "x": 18, "y": 45, "label": "+18pp", "shape": "triangle" },
    { "name": "元宝", "x": 14, "y": 26, "label": "+14pp", "shape": "circle" }
  ],
  "x_label": "纯白留存提升（pp）",
  "y_label": "纯白用户强留存率（%）",
  "x_max": 20,
  "y_max": 65
}
```

**视觉规范**：
- 坐标系：x 轴底部，y 轴左侧，0.01 inch 浅灰线
- 刻度：x_max / 5 一格，y_max / 10 一格
- 标签：6.5pt 中灰
- 数据点：18px 形状
  - `circle` → OVAL
  - `triangle` → ISOSCELES_TRIANGLE
  - 颜色：`PCOL[name]`
  - 边框：白色 1px
- 名称标签：右 0.10 + 上 0.09 offset，7.4pt 中灰黑
- 数值标签：上 0.31 offset，7.2pt 加粗 success，居中

### 2.5 `matrix_table`（矩阵表）

**数据格式**：
```json
{
  "type": "matrix_table",
  "headers": ["产品", "拍照答疑", "深度思考", "最高功能纯白"],
  "rows": [
    ["豆包", "+10pp", "+6pp", "拍照答疑 +10pp"],
    ["DS", "+17pp", "+15pp", "拍照答疑 +17pp"]
  ],
  "highlight_cells": [[0, 1], [1, 1], [0, 3]]
}
```

**视觉规范**：
- 表头：navy 底色 (#051C2C)，8.5pt 加粗白色，居中
- 数据行：斑马纹（每 2 行交替 RGB(248, 250, 252) / white），边框 RGB(226, 232, 240)
- 高亮单元格：白底 + warning 边框 1.6pt + 加粗 8.4pt
- 单元格文本：8.4pt 中灰黑，居中
- 行高：h / (n_rows + 1)

### 2.6 `quoted_table`（引文表）

**数据格式**：
```json
{
  "type": "quoted_table",
  "items": [
    { "label": "元宝正向", "text": "回答速度非常快、稳定性好（16%用户提到）", "color_token": "color.brand.product_c" },
    { "label": "元宝负向", "text": "可靠性差，希望答案更准确、索引更权威（51%）", "color_token": "color.accent.warning" }
  ]
}
```

**视觉规范**：
- 网格排布：(i%2)*4.65 + (i//2)*1.45
- 单格：4.10 × 1.08 inch
- 背景：浅米色 #FFFBEB
- 边框：圆角 0.12，色彩按 color_token
- 标签：9.5pt 加粗 color_token
- 引用：10.3pt KaiTi，中文左右双引号 `"..."`

---

## 3. 通用图表规则

- ✅ **必填字段**：`type`, `data/points/items/headers+rows`
- ✅ **可选字段**：`max_val`（自动计算时 = max * 1.1）, `colors`, `highlight_cells`
- ❌ **禁止**同一页混用 ≥ 3 种 chart type
- ❌ **禁止**为节省空间把坐标轴/标签字号降到 6pt 以下
- ❌ **禁止**使用 v3 旧名（`bar_chart_horizontal` / `heatmap_table` / `scatter_plot` / `user_voice`）
- 🟢 **可选**：辅助红框高亮（红框不超过 3 处/页）

## 4. MckEngine vs 纯 python-pptx 的取舍

v0.9.1 实证结果：

| 维度        | MckEngine     | 纯 python-pptx（v0.9.1 用） |
| --------- | ------------- | ------------------- |
| 图表精度      | 中（layout 固定） | 高（坐标/标签完全可控）         |
| 散点图       | ❌ 不支持         | ✅ 手绘（v0.9.1 P6 实证）  |
| 矩阵表红框    | 🟡 受限         | ✅ 完全可控（v0.9.1 P10 实证） |
| 视觉密度     | 中             | 高（v0.9.1 16 页高质量）  |
| 学习曲线     | 高（68 个 layout） | 低（6 类手绘 chart）    |
| 稳定性      | 🟡 API 文档与代码不一致 | ✅ python-pptx 1.0 稳定 |

**v3 决定**：renderer 优先用纯 python-pptx，**不**调用 MckEngine 的 68 个 layout。如果未来需要 MckEngine 的 cube/quadrant_3group 等，必须先按 `evals/rubrics.json` 评估通过再加入本表。
