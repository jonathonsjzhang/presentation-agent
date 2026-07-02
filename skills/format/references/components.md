# §P-2 组件库（Components）

> PPT 页面的 9 类核心组件，每类都有明确的触发条件、视觉规范、和 render.py 实现模板。**所有组件必须在 v0.9.1 渲染脚本中实际出现过**才收录。

---

## C-1. 全局导航标签栏（Navigation Tabs）

### 用途
帮助观众快速定位当前页面属于哪个分析维度；从 P2 起每页必带。

### 视觉规范
| 属性 | 规范 |
|---|---|
| 位置 | 标题下方 1.0-1.1 inch 高度处 |
| 标签数 | 3-6 个（推荐 6 个：总览/人群/文本/功能/运营/建议）|
| 标签尺寸 | 0.72 × 0.26 inch，gap 0.08 inch |
| 激活态 | 圆角矩形 + `color.brand.primary` (#0052D9) 填充 + 白色加粗 8.5pt |
| 非激活态 | 白色填充 + 浅灰边框 (RGB 205, 213, 225) + 中灰文字 (#666666) 8.5pt |
| 圆角比例 | adjustments[0] = 0.12 |

### content.json 格式
```json
{
  "navigation": {
    "tabs": ["总览", "人群", "文本", "功能", "运营", "建议"],
    "active_tab": 0
  }
}
```

### render.py 模板
```python
def add_nav(slide, active):
    top, left, h, gap = 0.78, 0.58, 0.26, 0.08
    widths = [0.72] * len(TABS)  # 6 个等宽 tab
    for i, tab in enumerate(TABS):
        x = left + sum(widths[:i]) + i * gap
        active_flag = (i == active)
        fill = COL["primary"] if active_flag else COL["white"]
        line = COL["primary"] if active_flag else RGBColor(205, 213, 225)
        s = add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, top, widths[i], h, fill, line=line, radius=True)
        add_text(slide, tab, x, top + 0.035, widths[i], h - 0.03,
                 size=8.5, bold=active_flag,
                 color=COL["white"] if active_flag else COL["muted"],
                 align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
```

---

## C-2. 发现面板（Insight Panel）— v3.1 扩展为 6 种变体

### 用途
提炼该页核心洞察，作为图表数据的"翻译"。**每页 analysis_dashboard 必带**（v3.1 起位置和形态按 evidence_type 灵活选择，**不强制右侧**）。

### v3.1 关键变更
v3 阶段位置写死为"页面右侧 (x=10.15, y=1.35, w=2.52, h=4.35)" + 形态写死为"编号圆圈+文字"。
v3.1 起按 evidence_type 灵活选择 6 种变体之一，让复杂证据组织成"可快速理解的视觉关系"。

### 6 种变体速查表

| 变体 ID | 名称 | 适用 evidence_type | 触发条件 | 位置（英寸） | 形态 |
|---|---|---|---|---|---|
| **C-2-A** | right-rail | 多点并列洞察 | 2-4 条编号洞察，**无主次** | x=10.12, y=1.35, w=2.52, h=4.35 | 浅灰 panel + 左侧竖线 + 编号圆圈 |
| **C-2-B** | top-banner | 整页关键结论 | 1-2 句最核心 takeaway | x=0.58, y=1.05, w=12.0, h=0.45 | 横条 + 左侧粗竖线 + 大字 13pt |
| **C-2-C** | bottom-takeaway | 行动建议 / 总结陈述 | closing 页 / method 页 / 行动建议 | x=0.58, y=6.30, w=12.0, h=0.58 | 底部横条 + 强调色边 + 多列分块 |
| **C-2-D** | callout-side | 关键反差点 | 单点对照（如"豆包 X / 元宝 Y"） | 自由位置（左/右/上） | 对话气泡 + 大字 + 强调色 |
| **C-2-E** | inline-anchor | 关联图表某数据点 | 需"引线+标注"指向图表内某柱/某点 | 锚定 x,y（指向数据点） | 引线 + 小气泡 + 编号 |
| **C-2-F** | matrix-grid | 2-3 维度分类对比 | 优先级矩阵 / 维度归类 | 中心区域（避开 nav/footer） | 2x2 / 3x1 卡片矩阵 + 维度标题 |

> **默认**：analysis_dashboard 仍优先 C-2-A（与 v0.9.1 视觉一致）。其余 5 种变体为 v3.1 新增，按 evidence 选型。
> **强制**：每页必须显式在 `insight_panel.variant` 字段选 1 种变体（见 rubrics.json FMT-V3-008）。

### 通用视觉规范（所有变体共用）
| 属性 | 规范 |
|---|---|
| 主色 | `color.brand.primary` (#0052D9) |
| 强调色 | `color.accent.success` (#22C55E) / `color.accent.warning` (#EF4444) |
| 中性底 | #F5F7FA（panel 背景）/ #FFFFFF（卡片底） |
| 文字主色 | navy #051C2C / 中灰 #666666 |
| 圆角比例 | 0.12 |
| 字体 | 标题 Microsoft YaHei UI / 正文 Microsoft YaHei |

---

### C-2-A. right-rail（默认）— v3.2 位置调整为适配 0.7 inch 边距

| 属性 | 规范 |
|---|---|
| 位置 | 页面右侧 **x=10.78, y=0.7, w=1.86, h=5.0**（v3.2 适配 0.7 inch 边距） |
| 标题 | "关键洞察" 12pt 加粗 navy |
| 背景 | 浅灰 (#F5F7FA) |
| 左侧竖线 | 0.045 inch 宽，`color.brand.primary` |
| 条目数 | 2-4 条（推荐 3 条） |
| 每条结构 | 编号圆圈（20px primary 色）+ 文字 10.2pt 中灰黑 |
| 条目间距 | 0.86 inch（4 条最大） |

> **v3.1 vs v3.2 位置对比**：
> | 版本 | x | y | w | h |
> |---|---|---|---|---|
> | v3.1 | 10.12 | 1.35 | 2.52 | 4.35 |
> | v3.2 | **10.78** | **0.7** | **1.86** | **5.0** |
>
> 原因：v3.1 的 x=10.12 + w=2.52 = 12.64（右边距 0.69）；v3.2 改为 x=10.78 + w=1.86 = 12.64（与 v3.1 右边界对齐，但起点更靠右因为新边距 0.7）。新 y=0.7 起点让 panel 与 title 区齐平。

**适用**：2-4 条并列洞察，**无主次**。比如"豆包强留存率为元宝 2.8 倍 / DS 居中但用户规模接近豆包 / 元宝需先补齐可靠性底座"。

**content.json 格式**：
```json
{
  "insight_panel": {
    "variant": "right-rail",
    "title": "关键洞察",
    "items": [
      "豆包强留存率为元宝 2.8 倍",
      "DS 居中但用户规模接近豆包",
      "元宝需先补齐可靠性底座"
    ]
  }
}
```

---

### C-2-B. top-banner

| 属性 | 规范 |
|---|---|
| 位置 | 页面顶部 x=0.58, y=1.05, w=12.0, h=0.45（位于 nav 与 title 之间）|
| 标题 | "核心结论" 13pt 加粗 navy |
| 内容 | 1-2 句核心 takeaway，11.5pt 中灰黑 |
| 背景 | 浅灰 (#F5F7FA) |
| 左侧粗竖线 | 0.08 inch 宽 `color.brand.primary` |
| 文字对齐 | 左对齐 + 上下居中 |

**适用**：整页最关键 1-2 句话，**全页主轴**。比如"豆包强留存率为元宝 2.8 倍；元宝应优先补齐可靠性与多模态体验"。

**content.json 格式**：
```json
{
  "insight_panel": {
    "variant": "top-banner",
    "title": "核心结论",
    "text": "豆包强留存率为元宝 2.8 倍；元宝应优先补齐可靠性与多模态体验。"
  }
}
```

---

### C-2-C. bottom-takeaway

| 属性 | 规范 |
|---|---|
| 位置 | 页面底部 x=0.58, y=6.30, w=12.0, h=0.58（位于 footer 之上）|
| 标题 | "行动建议" / "总结陈述" 11pt 加粗 navy |
| 内容 | 2-3 列分块（如 "立即做 / 短期做 / 中期探索"）|
| 列分隔 | 0.02 inch 宽浅灰竖线 |
| 背景 | 浅灰 (#F5F7FA) |
| 顶部粗线 | 0.05 inch 宽 `color.brand.primary` |

**适用**：closing 页 / method 页 / 行动建议页，**承接"接下来做什么"**。比如"立即做：补可靠性底座 / 短期做：拍照答疑场景化 / 中期探索：陪伴+电商"。

**content.json 格式**：
```json
{
  "insight_panel": {
    "variant": "bottom-takeaway",
    "title": "行动建议",
    "columns": [
      { "tag": "立即做", "text": "补可靠性底座" },
      { "tag": "短期做", "text": "拍照答疑场景化" },
      { "tag": "中期探索", "text": "陪伴+电商" }
    ]
  }
}
```

---

### C-2-D. callout-side

| 属性 | 规范 |
|---|---|
| 位置 | 自由（左/右/上），不与主图表冲突 |
| 形状 | 对话气泡（带小尖角指向数据点）或 大圆角矩形 |
| 标题 | "反差" / "重点" 11pt 加粗 |
| 数字/短语 | 18-24pt 加粗 `color.accent.warning` 或 `success` |
| 背景 | 浅色（按性质：正向 success 浅绿 / 负向 warning 浅红）|
| 边框 | 1.5pt 强调色 |

**适用**：**单点反差点**——观众一眼要看到"差距有多大"。比如"豆包强留存率 54% vs 元宝 19%，**差距 35pp**"。

**content.json 格式**：
```json
{
  "insight_panel": {
    "variant": "callout-side",
    "position": "right",
    "anchor": { "x": 8.5, "y": 2.5 },
    "tone": "warning",
    "headline": "差距 35pp",
    "subline": "豆包 54% vs 元宝 19%"
  }
}
```

---

### C-2-E. inline-anchor

| 属性 | 规范 |
|---|---|
| 位置 | 锚定到图表某数据点（chart 元素的 x,y）|
| 形状 | 小气泡（圆角矩形 0.7×0.35）+ 引线 0.015 inch 宽 |
| 引线颜色 | `color.brand.primary` |
| 气泡内容 | 1 句话（10pt） 或 1 个数字（12pt 加粗）|
| 气泡底色 | 浅蓝 (#E6F0FF) |

**适用**：**关联图表内某数据点**——把洞察直接"贴"到那根柱/那个点上。比如"该柱为豆包，纯白留存 +25.2pp，是全图最高"。

**content.json 格式**：
```json
{
  "insight_panel": {
    "variant": "inline-anchor",
    "anchor": { "x": 3.2, "y": 2.8, "target": "豆包_强留存" },
    "text": "豆包纯白留存 +25.2pp，全图最高"
  }
}
```

---

### C-2-F. matrix-grid

| 属性 | 规范 |
|---|---|
| 位置 | 中心区域（避开 nav/footer/主图表）|
| 形态 | 2x2 / 3x1 / 2x3 卡片矩阵 |
| 每张卡片 | 圆角矩形 0.12，标题 10.5pt 加粗 + 描述 9pt 中灰 |
| 卡片间距 | 0.12 inch |
| 维度标题 | 矩阵上方/左侧 9pt 加粗 primary 色 |

**适用**：**2-3 维度分类对比**——把多个洞察按维度归类摆放。比如"按产品×优先级：豆包/DS/元宝 × 立即/短期/中期"。

**content.json 格式**：
```json
{
  "insight_panel": {
    "variant": "matrix-grid",
    "layout": "3x1",
    "axis_x": "产品",
    "axis_y": "建议",
    "cells": [
      { "row": "豆包", "col": "建议", "text": "保持优势，关注可靠性一致性" },
      { "row": "DS",   "col": "建议", "text": "放大功能纯白，保留速度优势" },
      { "row": "元宝", "col": "建议", "text": "补可靠性+多模态底座" }
    ]
  }
}
```

---

---

## C-3. pp 标注（百分点差异 Callout）

### 用途
直观展示两个数值之间的差异幅度（百分点 pp），避免观众自己计算。

### 视觉规范
| 属性 | 正向差异 | 负向差异 |
|---|---|---|
| 格式 | `+Npp` | `-Npp` |
| N 取值 | 整数（四舍五入） | 整数 |
| 字号 | 8.2pt 加粗 | 8.2pt 加粗 |
| 颜色 | `color.accent.success` (#22C55E) | `color.accent.warning` (#EF4444) |
| 边框 | 圆角矩形 0.58×0.24，浅绿底 (#F0FDF4) | 浅红底 |
| 位置 | 数据点附近（上/右/左），避免遮挡 | 同左 |

### render.py 模板
```python
def add_pp_callout(slide, text, x, y, color=COL["success"]):
    add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 0.58, 0.24,
              RGBColor(240, 253, 244), line=color, radius=True)
    add_text(slide, text, x + 0.02, y + 0.035, 0.54, 0.14,
             size=8.2, bold=True, color=color, align=PP_ALIGN.CENTER)
```

---

## C-4. 红框高亮（Warning Frame）

### 用途
引导视觉焦点到关键数据点（最大值、最小值、异常值）。

### 视觉规范
| 属性 | 规范 |
|---|---|
| 边框宽度 | 1.6pt 实线 |
| 颜色 | `color.accent.warning` (#EF4444) |
| 圆角 | 0.12 |
| 适用对象 | 表格单元格、KPI 卡片 |
| 使用频率 | 每页 1-3 处（避免过度使用） |

### render.py 模板
```python
# 在 matrix_table 中应用
s = add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE,
              tx + 0.12, yy + 0.08, col_w - 0.24, row_h - 0.16,
              COL["white"], line=COL["warning"], radius=True)
s.line.width = Pt(1.6)
```

---

## C-5. 编号圆圈（Numbered Marker）

### 用途
标记 Top 3 重要发现，建立阅读优先级。

### 视觉规范
| 属性 | 规范 |
|---|---|
| 形状 | 圆形 (OVAL) |
| 直径 | 20-28px（按层级） |
| 填充色 | 强调色（按上下文） |
| 文字 | 白色阿拉伯数字 7.3-9pt 加粗 |
| 位置 | 发现面板条目 / 行动建议路径 / 流程步骤 |

---

## C-6. 用户原声引用框（Quote Box）

### 用途
增加定性研究的真实感；专门承载 USER_QUOTES。

### 视觉规范
| 属性 | 规范 |
|---|---|
| 位置 | 网格排布 (i%2)*4.65 + (i//2)*1.45 |
| 尺寸 | 4.10 × 1.08 inch |
| 背景 | 浅米色 (#FFFBEB) |
| 边框 | 圆角 0.12，色彩按正/负向（正向用产品色，负向用 warning） |
| 标签字号 | 9.5pt 加粗（"X 正向"/"X 负向"） |
| 引用字号 | 10.3pt |
| 引用字体 | **KaiTi**（楷体）模拟手写感 |
| 内容包裹 | 中文左右双引号 `"..."` |

---

## C-7. 脚注与页码（Footer）

### 用途
提供数据来源可追溯性 + 页码定位。

### 视觉规范
| 属性 | 规范 |
|---|---|
| 位置 | y=7.08（页面底部上方 0.4 inch）|
| 分隔线 | 上方 0.01 inch 浅灰 (#E0E0E0) 横线 |
| 来源文字 | 7.8pt 中灰，宽度 10.6 inch，左对齐 |
| 页码 | 8.5pt 中灰，宽度 0.55 inch，右对齐 |
| 来源前缀 | "注：" |

---

## C-8. 标题块（Title Block）

### 视觉规范
| 属性 | 规范 |
|---|---|
| 主标题 | x=0.55, y=0.32, w=12.0, h=0.42, size=18 加粗 navy (#051C2C) |
| 副标题 | x=0.58, y=0.76, w=9.6, h=0.28, size=9.5 中灰 (#666666) |
| 字体 | 标题用 `Microsoft YaHei UI`，其他用 `Microsoft YaHei` |

---

## C-9. 卡片（Card）

### 用途
承载 metric_cards / finding cards / auxiliary 文本块。

### 视觉规范
| 属性 | 规范 |
|---|---|
| 形状 | 圆角矩形 0.12 |
| 填充 | 白色 |
| 边框 | 1px #E2E8F0 |
| 左侧装饰 | 0.045 inch 宽强调色竖线（红/绿/蓝/橙） |
| 编号圆圈 | 28px OVAL，强调色填充 + 白色数字 |
| 标题 | 11.5pt 加粗 navy |
| 描述 | 9.2pt 中灰黑 |

### content.json 格式（metric card 变体）
```json
{
  "metric_cards": [
    {
      "value": "4,174",
      "label": "总样本",
      "description": "问卷投放回收",
      "color_token": "color.brand.primary"
    }
  ]
}
```

---

## 避免 shape 重叠规则（v3.2 新增，强制）

> **配套规则**：FMT-V3-010（无重叠，P0 强制）。本节给出每类组件的"避让优先级"和位置约束。

### 避让优先级（从高到低）

1. **main_chart**（bar / grouped_bar / scatter / matrix_table / quoted_table）—— 页面焦点，必须独占区域
2. **callout / quote / anchor** —— 重点强调元素，应位于 main_chart 之外的空白区
3. **insight_panel rail / banner / takeaway / matrix-grid** —— 总结提炼，位置见 C-2 各变体
4. **nav / title / subtitle / footer** —— 框架元素，已固定位置
5. **metric_card / block / pp_callout** —— 辅助元素，让位给上述

### 位置约束速查

| 组件类型 | 位置约束 | 不能与什么重叠 |
|---|---|---|
| main_chart | 0.7 ≤ x, y + h ≤ 6.8 | quote / callout（除 banner 变体）|
| callout (callout-side) | 自由，但不能与 main_chart 重叠 | main_chart / insight_panel |
| anchor (inline-anchor) | y 起点 ≥ main_chart.y - 0.2 OR y + h ≤ main_chart.y | main_chart（除引线端点）|
| matrix-grid | 中心或右半，不能与 quote_items 重叠 | quote_items / callout |
| quote_items | 6 卡片 2x3 网格，宽度限制 5.3 inch | matrix-grid（必须分两栏）|
| insight_panel rail | x=10.78, w=1.86, y=0.7, h=5.0 | main_chart（main_chart.w 应 ≤ 10.0）|

### 实战修法（v3.2 修复清单）

- **P8 anchor 越界**：原 (bx=3.20, by=1.45) 压住 grouped_bar，改 (bx=7.0, by=1.20)
- **P13 quote vs matrix 重叠**：6 quote 改 3x2 grid 在左半 (x=0.7-6.0)，matrix 改 2x1 简版在右半 (x=6.3-12.633)
- **P5 callout vs emphasis_frame**：callout (8.5, 4.6, 3.2, 1.4) 改 (9.50, 4.6, 3.0, 1.4) 让位 emphasis_frame
- **P2 移除 bar_chart**：核心发现页改纯文字（v3.2 关键变更，见 layouts.md §2.2）
