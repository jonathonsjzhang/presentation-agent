# §P-3 样式 Token（Style Tokens）

> v3 的 token 量化值**全部来自 v0.9.1 渲染脚本的 Python 常量**，不再用 v3 表格里那些没有渲染脚本背书的"理论值"。

## 1. 配色方案（color tokens）

### 1.1 默认品牌色（PPT / Document / HTML 三载体共享）

```python
COL = {
    "primary":   RGBColor(0, 82, 217),     # #0052D9  专业蓝（品牌主色，导航激活态、强调）
    "navy":      RGBColor(5, 28, 44),      # #051C2C  深蓝（封面/结论页背景、标题文字）
    "product_a": RGBColor(34, 197, 94),    # #22C55E  成功绿（产品A 相关数据点）
    "product_b": RGBColor(37, 99, 235),    # #2563EB  深蓝（产品B 相关数据点）
    "product_c": RGBColor(147, 197, 253),  # #93C5FD  浅蓝（产品C 相关数据点）
    "success":   RGBColor(34, 197, 94),    # #22C55E  正向差异（pp 标注、强调）
    "warning":   RGBColor(239, 68, 68),    # #EF4444  负向差异、红框高亮
    "orange":    RGBColor(245, 158, 11),   # #F59E0B  次要强调
    "panel_bg":      RGBColor(245, 247, 250),  # #F5F7FA  发现面板背景
    "panel_blue":    RGBColor(232, 244, 253),  # #E8F4FD  备选面板背景
    "text":      RGBColor(51, 51, 51),     # #333333  主文本
    "muted":     RGBColor(102, 102, 102),  # #666666  辅助文本
    "light":     RGBColor(224, 224, 224),  # #E0E0E0  分割线、表格边框
    "white":     RGBColor(255, 255, 255),  # #FFFFFF
    "black":     RGBColor(0, 0, 0),        # #000000
}
```

### 1.2 产品色映射（PCOL）

```python
PCOL = {
    "豆包": COL["product_a"],
    "DS":  COL["product_b"],
    "元宝": COL["product_c"],
}
PLIGHT = {
    "豆包": RGBColor(230, 255, 239),  # 浅绿
    "DS":  RGBColor(232, 240, 255),  # 浅蓝
    "元宝": RGBColor(239, 247, 255),  # 极浅蓝
}
```

> **可定制**：`content.json` 的 `brand_colors` 字段可覆盖 PCOL；缺省使用上述默认。

### 1.3 深色主题变体（cover / closing 用）

```python
# 封面专用
DARK_BG_OVERLAY = RGBColor(15, 52, 86)   # 装饰圆深色版
DARK_BG_ACCENT = RGBColor(0, 82, 217)    # 装饰圆主色版
DARK_TEXT = RGBColor(255, 255, 255)
DARK_MUTED = RGBColor(215, 225, 240)
DARK_LABEL = RGBColor(190, 204, 220)
DARK_FOOTER = RGBColor(175, 190, 205)
```

## 2. 字体（typography tokens）

| Token            | 字体                                | 用途           |
| ---------------- | --------------------------------- | ------------ |
| `font.family.sans`  | `Microsoft YaHei`                 | 正文（默认）       |
| `font.family.title` | `Microsoft YaHei UI`             | 标题（带加粗权重更明显） |
| `font.family.quote` | `KaiTi`（楷体）                     | 用户原声引用       |
| `font.family.mono`  | `Consolas`                       | 数据 / 编号     |

### 2.1 字号表（v0.9.1 实测）

| Token              | 数值      | 用途           |
| ------------------ | ------- | ------------ |
| `font.size.cover_title` | 30pt  | 封面主标题（大号）    |
| `font.size.title`      | 18pt  | 页面标题         |
| `font.size.subtitle`   | 9.5pt | 页面副标题        |
| `font.size.h2`         | 13pt  | 二级标题（执行摘要、卡片标题）|
| `font.size.h3`         | 12pt  | 三级标题         |
| `font.size.body`       | 9.2pt | 正文 / 发现面板条目  |
| `font.size.footnote`   | 7.8pt | 脚注           |
| `font.size.cover_subtitle` | 14pt | 封面副标题     |
| `font.size.callout`    | 8.2pt | pp 标注 / 红框文字 |
| `font.size.tab`        | 8.5pt | 导航标签         |
| `font.size.metric_value` | 19pt | metric card 数值 |
| `font.size.table_cell` | 8.4pt | 表格单元格        |
| `font.size.quote`      | 10.3pt | 用户原声引用      |
| `font.size.legend`     | 8.3pt | 图例           |
| `font.size.axis_label` | 7.3pt | 图表轴标签        |
| `font.size.bar_value`  | 13pt  | 柱状图数值标签      |
| `font.size.bar_value_small` | 6.7pt | 分组柱状图数值标签 |
| `font.size.matrix_header` | 8.5pt | 矩阵表头     |
| `font.size.matrix_cell`   | 8.4pt | 矩阵单元格     |

### 2.2 字重 & 行距

| Token              | 数值  |
| ------------------ | --- |
| `weight.bold`      | True / 加粗 |
| `weight.regular`   | 常规    |
| `line.height.tight`   | 0.9 |
| `line.height.normal`  | 1.0 |
| `line.height.relaxed` | 1.2 |

## 3. 间距（spacing tokens）

| Token        | 数值（inch） | 用途             |
| ------------ | -------- | -------------- |
| `space.xs`   | 0.03     | 文本框内边距          |
| `space.sm`   | 0.05     | 段落小间距           |
| `space.md`   | 0.10     | 卡片内边距           |
| `space.lg`   | 0.20     | 卡片间距 / 模块间距     |
| `space.xl`   | 0.40     | 章节间距            |
| `space.2xl`  | 0.80     | 页边距（cover / closing 装饰） |

## 4. 网格（grid tokens）

| Token             | 数值                  | 用途                |
| ----------------- | ------------------- | ----------------- |
| `grid.columns`    | 12                  | 12 栏网格（不是 12 列实际）|
| `grid.gutter`     | 0.08 inch           | 标签 gap            |
| `grid.margin`     | **0.7 inch**（v3.2 起，左右上下统一）| **页边距**（所有内部页面）|
| `grid.margin_cover` | 0.55 inch          | 页边距（cover / closing 装饰页，保留原状）|
| `grid.safe_area`  | 0.7 ~ 6.8 / 0.7 ~ 12.633 | 安全区（内部页面，content 落点必须在 0.7-12.633 × 0.7-6.8 内）|
| `grid.cover_safe_area` | 0.55 ~ 12.78 / 0.55 ~ 6.95 | 安全区（cover/closing）|

### 4.1 统一边距规则（v3.2 新增，强制）

> **强制规则**：所有内部页面（layout_type ∈ {executive_summary, analysis_dashboard, methodology_or_strategy, priority_matrix}）的**上下左右页边距必须完全一致 = 0.7 inch**。这意味着：
> - **左**：所有 shape 的 x ≥ 0.7
> - **右**：所有 shape 的 x + w ≤ 13.333 - 0.7 = 12.633
> - **上**：所有 shape 的 y ≥ 0.7
> - **下**：所有 shape 的 y + h ≤ 7.5 - 0.7 = 6.8
> - **content 区域**：x ∈ [0.7, 12.633], w_max = 11.933；y ∈ [0.7, 6.8], h_max = 6.1
>
> **例外**：cover / closing 类型页面（layout_type = cover）保留原 0.55 inch 边距，因为它们用大字号 + 装饰圆，需要更多可用空间。
>
> **历史问题**：v3.0/v3.1 阶段使用 0.55 inch 边距，但实际页面用 0.55-0.78 inch 不一致（左 0.55 / 右 0.78），导致左右留白不均。v3.2 起统一为 0.7 inch。
>
> **示例**：
> - 标题区：x=0.7, y=0.7, w=11.933, h=0.5（4 行标题可放下）
> - 导航：x=0.7, y=1.25, w=11.933, h=0.3
> - 主体：x=0.7, y=1.6, w=11.933, h=4.6
> - 脚注：x=0.7, y=6.4, w=11.933, h=0.3
>
> **配套规则**：FMT-V3-009（强制）、FMT-V3-010（无重叠）

## 5. 画布尺寸

```python
prs.slide_width  = Inches(13.333)  # 16:9 widescreen
prs.slide_height = Inches(7.5)
W, H = 13.333, 7.5
```

## 6. 信息密度方案（4 选 1）

> **强制规则**：v3 起每页必须显式选择一种方案。禁止"混搭"。

| 方案        | 适用场景              | 占比 (v0.9.1 实证) | 典型页 |
| --------- | ----------------- | ---------------- | --- |
| **A: 左图右文** | 数据分析 / 对比页（默认）   | ~60%             | P4, P5, P6, P7, P8, P10, P12 |
| **B: 三栏布局** | 多维对比（多个并列数据集）   | ~20%             | P11 |
| **C: 上下分层** | 方法论 / 总结 / 矩阵页  | ~15%             | P3, P15 |
| **D: 纯文字结构化** | 执行摘要 / 行动建议 / 结论 | ~5%             | P2, P14, P16 |

### 6.1 方案 A（左图右文，默认）

```
[标题 0-0.78"]
[导航 0.78-1.04"]
[主图 60-70% | 发现面板 25%] 1.35-5.7"
[脚注 7.08-7.30"]
```

### 6.2 方案 B（三栏）

```
[标题 + 导航]
[数据A 32% | 数据B 32% | 数据C 18% | 发现 18%]
[脚注]
```

### 6.3 方案 C（上下分层）

```
[标题 + 导航]
[概览 50%]
[详细分析 35%]
[脚注 15%]
```

### 6.4 方案 D（纯文字结构化）

```
[大标题]
[1. 标题
    └─ 子要点 1.1
    └─ 子要点 1.2]
[2. ...]
```

## 7. 强制规则（style invariants）

- ❌ **禁止**使用非 token 表中的颜色（防止品牌色不一致）
- ❌ **禁止**使用非 token 表中的字号（防止视觉漂移）
- ✅ **必须**通过 `get_brand_color(name)` 获取颜色对象
- ✅ **必须**确保同一产品/维度在不同页面使用相同颜色
- 🟢 **可选**：通过 `content.json` 的 `brand_colors` 字段自定义品牌色
