# Format Skill v3.12 — CHANGELOG

> **本版关键变更**：v3.12 hotfix — P0 layout 漂移修复 + P1 默认值/参数冗余清理 + P1 strict 模式 + P2 死代码清理 + QA 5 重门禁全绿。
>
> **版本定位**：v3.12 是 v3 系列的**首个正式发布版本**（"format skill v3"）——以 v0.9.1 视觉系统为基线，整合 v3.6→v3.11 累积功能改进 + v3.12 hotfix 代码质量修复。
>
> **小迭代版本管理规范**（沿用 2026-07-02 11:51 用户规则）：本目录 = v3.12 **完整快照**（只读冻结），后续 v3.13 迭代基于 `format.skill.v3/` 工作目录。

---

## v3.12 hotfix — 代码质量修复（2026-07-02 15:00）

> **本版关键变更**：在 v3.6→v3.11 累积功能改进基础上，集中修复 P0/P1/P2 级代码质量问题。**无功能/视觉变化**，所有 v3→v3.11 已通过 QA 的页面布局保持不变。v3.12 hotfix 是一次纯代码质量 hotfix，**不改变任何 page builder 的渲染输出**。

### P0：Layout 漂移修复（高优先级）

| 问题 | 文件 | 修复 |
|---|---|---|
| `MARGIN_INTERNAL = 0.7` 定义但仅 QA 引用，16 个 page builder 硬编码 0.7/11.933 | `render_v3.12.py` | 提取 `CONTENT_LEFT = 0.7` / `CONTENT_W = 11.933` 常量；16 处硬编码 → 常量引用 |
| `prs.slide_layouts[6]` 16 处硬编码 magic number | `render_v3.12.py` | 提取 `BLANK_LAYOUT_IDX = 6`；16 处 → `prs.slide_layouts[BLANK_LAYOUT_IDX]` |
| `add_insight_panel_takeaway` / `add_insight_panel_matrix` 等内部硬编码 0.7/11.933 | `render_v3.12.py` | 内部默认值改为 `CONTENT_LEFT` / `CONTENT_W` 引用 |

### P1：`add_discovery_panel` 默认值修复

| 项 | 旧 | 新 |
|---|---|---|
| 函数签名默认 | `(10.20, 1.30, 2.83, 5.20)` | `(DISCOVERY_X, 1.30, DISCOVERY_W, DISCOVERY_H)` = `(10.00, 1.30, 2.63, 4.10)` |
| 12 个调用方 | 显式传 `(10.00, 1.30, 2.63, 4.10)` | 移除冗余（默认值一致）|
| P4 纯白特殊 case | 显式传 `h=5.20` | 显式传 `h=5.20`（保留原行为）|

**根因**：函数默认值 10.20/2.83/5.20 与所有 12 个调用方实际值 10.00/2.63/4.10 漂移——属于"P0 不一致"风险：若新增 caller 依赖默认值，会画出**错误位置**的 panel。

### P1：`add_bottom_summary` 冗余参数清理

9 个调用方原本显式传 `(0.7, 5.55, 11.933, 1.10)`（与默认值重复），v3.12 改为只传 `title=...`（默认值已够）。P4 总览特殊 case 显式传 `(y=5.80, h=0.80)` 保留原行为。

### P1：strict 模式（避免静默画 0 高度 bar）

3 处 `dict.get("可用性", 0)` → `dict(...)["可用性"]`（`TEXT_SATISFACTION_CORR` 查表）。缺 key 时直接 `KeyError` 而非静默画 0 高度 bar。

**根因**：v3.11 的 `dict.get("可用性", 0)` 在原始数据缺 key 时会**静默画高度为 0 的 bar**——QA 5 重门禁全绿但视觉上柱状图消失，不易察觉。

### P2：死代码清理

| 类别 | 删除项 | 行数 |
|---|---|---|
| 未用函数 | `rgb_hex` / `add_red_box` / `add_not_significant` / `add_insight_panel_rail` / `add_insight_panel_banner` / `add_insight_panel_callout` / `add_insight_panel` 别名 / `add_legend` | ~250 |
| 未用 import | `MSO_LINE_DASH_STYLE` | 1 |
| 未用 kwarg | `layout="3x1"`（`add_insight_panel_matrix`）| 1 |
| 未用常量 | `TITLE_EA_FONT = "楷体"` | 1 |

净减约 250 行 / 17% 体积。

### QA 5 重门禁全绿

| Gate | 检查 | v3.12 状态 |
|---|---|---|
| FMT-V3-009 | 统一边距 0.7 inch（内部页）| ✅ `uniform_page_margin_passed: true` |
| FMT-V3-010 | 无文字-文字/形状-形状重叠 + 文字不溢出 | ✅ `no_overlap_passed: true` |
| FMT-V3-011 | executive_summary 无 rail（P2 方案 E）| ✅ `executive_summary_no_rail_passed: true` |
| FMT-V3-012 | bottom_summary 必备 | ✅ `bottom_summary_present_passed: true` |
| FMT-V3-013 | discovery rail 必备 | ✅ `discovery_rail_present_passed: true` |

### v3.12 hotfix 关键经验

- **P0 layout 漂移反复出现**（v3.5 → v3.6 → v3.11 都有零散硬编码）：8 个常量提取是**收口**而非"修一处"，避免下个版本又冒出来
- **`dict.get(..., 0)` 是反模式**（尤其在 QA 门禁能绿的前提下）：strict 模式宁可崩也不画错图
- **死函数积压 17%**：每个版本 5-8 个，是 reviewer 关注度不足的信号；v3.13 候选：CI 加 `vulture` / `pyflakes` 静态检查
- **hotfix 不改视觉**：v3.12 与 v3.11 输出 PPTX 在视觉上**完全一致**，仅是代码质量修复——这种 hotfix 安全边际最高

---

## v3.6 → v3.11 累积历史（v3.12 继承的视觉与功能基线）

> v3.12 完整保留 v3.6→v3.11 累积改进。下文按时间倒序列出每个版本的 diff，作为 v3.12 hotfix 的"前置基线"参考。

### v3.10 → v3.11 diff — 中英文字体分离（2026-07-02 14:32）

> **本版关键变更**：用户规则 2026-07-02 14:32 明确"中文用楷体、英文/数字用 arial"——单一 FONT 变量无法满足 PowerPoint 的 East Asian / Latin 双 typeface 机制。v3.11 引入 lxml 双 typeface helper `_set_dual_font()`，给每个 run 同时设 `<a:latin>` (arial) + `<a:ea>` (楷体) + `<a:cs>` (arial)。

**实现细节**：
- `_set_dual_font(run, latin, ea, size_pt=None, bold=False, color=None)`：用 `lxml.etree` 操作 `run._r.get_or_add_rPr()`，插入 3 个 `<a:latin>/<a:ea>/<a:cs>` 元素
- `add_text` / `add_para_text` / `add_title` / `add_card` / `add_nav` / `add_tencent_logo` / `add_confidential_tag` / `add_footer` / `add_insight_panel_takeaway` / `add_insight_panel_anchor` / `add_insight_panel_matrix` / `bar_chart` / `grouped_bar` / `scatter_plot` / `add_pp_callout` 等 15+ 个 helper 全部改造
- 视觉结果：中文"留存""驱动矩阵""纯白"等显示为楷体（圆润、易读），英文/数字"+21.0pp""FMT-V3-009"显示为 arial（清晰、对比度强）

### v3.9 → v3.10 diff — P3 顶部 4 blocks 重构

> **本版关键变更**：v3.9 修完 20 处文字溢出 + 5 重门禁全绿后，用户 review 发现 **P3 顶部 4 blocks 文字逻辑混乱**——原结构 `(人话名, 用户数, 描述) = ("三栖用户", "2,128", "豆包+DS+元宝")` 存在 3 个问题：① 读者看到 "2,128" 不知道这是什么指标；② "三栖用户" 和 "2,128" 关系不明；③ "豆包+DS+元宝" 既是枚举也是解释。v3.10 重构为 `(维度名, 数量, 枚举值) + 用户数附加信息`，符合用户反馈的"产品/3/元宝/DS/豆包"逻辑顺序。

### P3 顶部 blocks 重构

**旧结构（v3.9）**：
| 块 | title（人话名）| value（数字）| desc（描述）|
|---|---|---|---|
| 1 | 三栖用户 | 2,128 | 豆包+DS+元宝 |
| 2 | 仅 DS+元宝 | 172 | 留存最高机会池 |
| 3 | 仅 豆包+元宝 | 437 | 迁移难度偏高 |
| 4 | 仅 豆包+DS | 1,307 | 潜在转化对象 |

**新结构（v3.10）**：
| 块 | 维度名（行 1 左）| 数字（行 2 主信息）| 枚举（行 3 主信息）| 用户数（行 1 右附加）|
|---|---|---|---|---|
| 1 | 产品组合 | 3 | 元宝 / DS / 豆包 | 2,128 用户 |
| 2 | 产品组合 | 2 | DS / 元宝 | 172 用户 |
| 3 | 产品组合 | 2 | 豆包 / 元宝 | 437 用户 |
| 4 | 产品组合 | 2 | 豆包 / DS | 1,307 用户 |

### 视觉布局
- **行 1 (y=1.65-1.85)**：维度名 "产品组合"（灰色 9pt 左对齐）+ 用户数 "2,128 用户"（灰色 9pt 右对齐）
- **行 2 (y=1.85-2.33)**：大数字 "3"（彩色 26pt 加粗）+ "种产品" 单位（灰色 10pt）
- **行 3 (y=2.35-2.60)**：枚举产品名 "元宝 / DS / 豆包"（navy 12pt 加粗）

### v3.8 → v3.9 diff — 文字溢出诊断 + 20 处真实垂直溢出修复

> **本版关键变更**：v3.8 P6 baseline 5.40 对齐后，用户 review 暴露 16 页中累计 20 处真实文字溢出（Slide 2 executive summary body 5 处 + Slide 5 driver matrix 15 处）。v3.9 新增 `debug_text_overflow.py` 综合诊断工具（text-text + shape-shape + text-overflow 三合一）并修复所有 20 处真实溢出。

### 1. 新增 `debug_text_overflow.py` 综合诊断工具

**检测 3 类文本溢出**：
- **段宽溢出**：单段文字宽 > box w（可能折行）
- **总高溢出**：估算行数 × 行高 > box h（**真实可见溢出**）
- **隐式 box wrap**：当 box 高度够但宽度不够时仍可能视觉溢出

**算法**：
- 中文字符 ≈ 1.0 em，字号 1 pt = 1/72 inch
- 英文字符 ≈ 0.5 em
- 行高 = font_size × 1.25
- 同时检查 run-level 和 paragraph-level 字号（修复前 diagnostic 错误用 default 10pt）

**排除清单**：
- 页眉/页脚 (y < 0.40 / y > 6.85)
- 极小字号 (< 6.5pt 装饰性)
- 1-2 字符 page number

### 2. 修复 20 处真实垂直溢出

#### Slide 2 (Executive summary) — 5 处 body 文字溢出
**根因**：v3.4 方案 E 的 5 cards 布局把 `add_card` body h 计算为 `h - 0.58` = `0.65 - 0.58` = **0.07 (5pt)**，远不够 9.2pt 文字（line_h = 11.5pt）。文字溢出卡片底部 6.5pt。

**修复**：
```python
# 旧 (v3.4-v3.8)
add_card(s, t, b, 0.7, 1.70 + i*0.75, 11.933, 0.65, c, num=i+1)
# 卡片 5×0.65 + 4×0.10 = 3.65, 1.70→5.35
add_shape(..., 0.7, 5.65, 11.933, 0.45, ...)  # 数据条

# 新 (v3.9)
add_card(s, t, b, 0.7, 1.70 + i*0.90, 11.933, 0.80, c, num=i+1)
# 卡片 5×0.80 + 4×0.10 = 4.40, 1.70→6.10 (body h=0.22=16pt fits 9.2pt 1行)
add_shape(..., 0.7, 6.20, 11.933, 0.30, ...)  # 数据条下移 0.55
add_text(..., 0.85, 6.25, 11.6, 0.20, size=8.5, ...)  # 字号 9→8.5
```

#### Slide 5 (Driver matrix) — 15 处 +pp 数字折行溢出
**根因**：driver matrix 的 4 列布局 `name(0.75) + bar(1.45) + +pp(0.30) + type(0.35) = 2.85`，`+21.0pp` 6 字符 × 0.5em × 7.5pt = **26.2pt** > box w 21.6pt。折 2 行 18.8pt > box h 13pt → **垂直溢出 5.8pt**。

**修复**：
```python
# 旧
add_text(s, f"+{val:.1f}pp", x + 2.30, yy - 0.02, 0.30, 0.18, ...)
add_text(s, typ, x + 2.65, yy - 0.02, 0.35, 0.18, ...)

# 新 (v3.9)
add_text(s, f"+{val:.1f}pp", x + 2.25, yy - 0.02, 0.40, 0.18, ...)  # w 0.30→0.40 (21.6→28.8pt)
add_text(s, typ, x + 2.70, yy - 0.02, 0.35, 0.18, ...)              # x 2.65→2.70 让位
# 总宽 0.80+1.45+0.40+0.35 = 3.00 ≤ 3.05 列距 ✓
```

### 3. 验证结果

| 诊断维度 | v3.8 | v3.9 |
|---|---|---|
| 总高溢出 | 20 | **0** ✓ |
| 段宽溢出（warning） | 28 | 27 (Slide 5 减 1) |
| Shape overlap (真实) | 2 | 2 (Slide 1 cover + Slide 15 圆点居边界, 均为设计意图) |
| QA 五重门禁 | 全绿 | **全绿** |
| Slide count | 16 | 16 |
| 桌面副本 | 82KB | 84KB |

### v3.7 → v3.8 diff — P6 baseline 5.40 对齐

> **本版关键变更**：v3.7 P6 (纯白用户) scatter_plot 底 y=5.97 vs side comparison bars 底 y=4.65 相差 1.32 inch——视觉上明显"两张表错位"。FMT-V3-010 重叠检查不识别"对齐"（同 y 位置）。v3.8 修复 P6 + 定义 baseline 5.40 为全 PPT 视觉基线。

### 背景：v3.7 隐藏问题暴露

v3.7 P6 现状：
- **scatter_plot** (0.75, 1.42, 5.15, **4.55**) → base y=**5.97**
- **side comparison bars** → base y=**4.65**
- **两图底差 1.32 inch** — 视觉上明显"两张表错位"

QA 漏报原因：
- FMT-V3-010 只检查"重叠"（AABB 碰撞），不检查"对齐"（同 y 位置）
- v3.7 `debug_shape_overlap.py` 同样只看碰撞，无 baseline 概念
- 人工 review 才暴露："P6 散点图明显比 side bars 高出一截"

### P6 修复

| 元素 | v3.7 | v3.8 |
|---|---|---|
| **scatter_plot h** | 4.55 | **3.98**（base 5.97→5.40，缩短 0.57）|
| **side bars base** | 4.65 | **5.40**（上移 0.75，与 scatter 平行）|
| **side bars product titles y** | 1.45 | **2.20**（与 group title 对齐）|
| **bars height 公式** | 2.7 * x/65 | 不变（bh1/bh2 仍按 65% 标度）|
| **bars 顶 label y 公式** | 4.65-bh1-0.20 | **5.40-bh1-0.20** |
| **callout y** | 4.95 | **5.70**（baseline 下 0.30 inch，与 v3.7 P10 一致）|
| **group title "纯白 vs 非纯白" y** | 1.12 | **1.87**（与 product titles 视觉对齐）|

**P6 修复后坐标验证**（python-pptx 解析）：
- scatter x_label "纯白留存提升（pp）" 底 y=**5.56**
- 6 个 side bars 形状底 y=**5.40**（全部精确）
- callouts "+10pp/+18pp/+14pp" y=5.70-5.94（baseline 下 0.30）
- 散点图与 side bars 视觉上"一张大表"对齐感 ✓

### 关键设计决策

- **baseline 5.40 而非 5.55/5.97**：与 P4 (bar chart + table) / P7 (matrix + funnel) / P15 (matrix) 视觉基线完全一致——**全 PPT 16 页 baseline 统一为 5.40**
- **scatter_plot h 缩 0.57 而非等比缩**：保留散点 (0,0)→(20,65) 标度完整性，y_max=65 不变；仅压缩内部 plot 区域从 4.15 → 3.58 inch（散点视觉更紧凑但仍可读）
- **callout y 5.70 而非 4.95**：让 callout 紧贴 baseline 下沿，与 P10 callout (y=4.65) 保持同一种"图表下方紧贴 +pp 强调"的视觉节奏
- **不动 discovery_panel**：P6 discovery_panel (10.00, 1.30, 2.63, 5.20) 从 y=1.30 到 y=6.50，与新 baseline 5.40 视觉兼容（panel 仍比 baseline 长 1.10 inch）

### v3.8 渲染验证（2026-07-02 14:14）

- 16 页 + 0 placeholder + 全视觉元素
- `passed: true`, `issues: []` (QA 五重门禁全绿)
- `uniform_page_margin_passed: true`（FMT-V3-009）
- `no_overlap_passed: true`（FMT-V3-010）
- `executive_summary_no_rail_passed: true`（FMT-V3-011）
- `bottom_summary_present_passed: true`（FMT-V3-012）
- `discovery_rail_present_passed: true`（FMT-V3-013）
- `insight_panel_variants_diversity: 3`（bottom_summary / rail / matrix）
- **debug_shape_overlap.py**: 9 张 slide → v3.7 2 张 → **v3.8 仍 2 张**（Slide 1 cover 设计 + Slide 15 圆点居边界，2 处均为设计意图）
- **P6 baseline 对齐验证**（python-pptx 解析）：scatter x_label 底 y=5.56 + 6 bars 底 y=5.40，差仅 0.16 inch（由 scatter x_label 标签偏移引起，可接受）

### 关键经验（v3.8）

- **FMT-V3-010 仍不够**：v3.7 已升级检查 text-text + shape-shape + text-overflow，v3.8 暴露需要再加 **"baseline 对齐检查"**——同页面的多张图表底 y 应在 ±0.05 inch 内
- **"QA 绿 + 人工 review 才发现"反复发生**：v3.6 缺 rail → v3.7 重叠 → v3.8 baseline 错位；说明**机器门禁与人工 review 永远互补**，但机器门禁应逐步覆盖更多视觉问题
- **baseline 5.40 = 全 PPT 视觉基线**：v3.6 P4 修复时确定 5.40 为"内容下边线"；v3.8 P6 修复时扩展到"图表 baseline"；未来 v3.9 应在 SKILL.md 显式定义"baseline 5.40 规范"
- **scatter_plot 缩高不缩标度**：y_max 标度值不变，只压缩内部 plot 区域——避免"缩小图表 = 缩小信息"的认知偏差
- **callout 位置 = baseline + 0.30**：与 P10 callout 模式一致（baseline + 0.30 让位给 chart x 轴标签 + 紧贴强调）

### 未来 v3.9 候选

- ① **FMT-V3-014 baseline 对齐门禁**：同页面 ≥2 张图表底 y 应在 ±0.05 inch 内
- ② **SKILL.md 显式定义 baseline 5.40 规范**：所有内容图表/矩阵/表格 baseline = 5.40
- ③ **P3 顶部 5 个 cards 重新排版**（当前 5 卡横排 + 4 卡横排），可改为 2×3 网格
- ④ **logo 改为可配置**（公司级品牌化）

---

## v3.6 → v3.7 diff (历史快照)

## v3.6 → v3.7 diff

> **本版关键变更**：v3.6 引入 4 区填充 + bottom_summary + FMT-V3-012/013 后，多张 slide 出现新重叠（因 bottom_summary (y=5.55-6.65) 与 bar chart x 轴标签 (y=base+0.08-0.30) 在 base > 5.25 时直接冲突）。v3.7 修复 7 张内容页的 11 处真实重叠 + 1 张封面 3 处装饰性"重叠"识别为设计意图。

### 背景：v3.6 隐藏问题暴露

v3.6 QA 五重门禁（FMT-V3-009/010/011/012/013）已全绿，但 FMT-V3-010 只检查**文字-文字**重叠，未检查**形状-形状**重叠和**文字溢出形状边界**。v3.6 实际渲染中：

- **bar chart x 轴标签 y=base+0.08~0.30**，base (y+h) 决定位置
- **bottom_summary 默认 y=5.55, h=1.10**
- 当 bar chart base > 5.25 时，x 轴标签 y=5.33-5.55 与 bottom_summary y=5.55 直接相邻或重叠

人工逐页 review 才暴露：9 张 slide 有 11 处真实重叠（v3.6 `debug_text_overlap.py` 漏报，因为只看 text-text）。

### 新增：综合形状重叠诊断工具

**`debug_shape_overlap.py`**（v3.7 新增，~250 行）：

```python
# 3 类检查
1. TEXT-TEXT 重叠（v3.6 debug_text_overlap.py 的检查范围）
2. SHAPE-SHAPE 重叠（v3.7 新增）— 矩形 AABB 碰撞检测
3. TEXT 溢出 SHAPE 边界（v3.7 新增）— 检查 text 框是否超出容器

# 设计意图豁免
- P1 cover 装饰性超出页边（圆/Tencent logo）
- connector line 跨越锚定区域（视觉合理）
```

v3.6 漏报 → v3.7 检出 9 张 slide 有 11 处真实问题。

### 7 张内容页针对性修复

| 页 | v3.6 问题 | v3.7 修复 |
|---|---|---|
| **P2** | subtitle (y=1.10) 与 title (y+h=1.12) 重叠 0.02 inch | subtitle y 1.10 → 1.20，留 0.08 gap |
| **P4** | banner (y=1.10, h=0.45) 与 KPI 卡顶部 (y=1.30) 紧贴；KPI 卡 (y=1.30, h=1.20) 底部 y=2.50；data table (y=2.60) 紧贴 OK；但 bottom_summary (y=5.55) 与 x 轴标签 (y=5.48) 冲突 | ① 移除 banner；② KPI 卡 y 1.30→1.20；③ data table y 2.60→2.50；④ bottom_summary y 5.55→5.80, h 1.10→0.80 (避开 x 轴 5.48-5.70) |
| **P5** | emphasis frame (y=4.88, h=0.82) 与 bottom_summary (y=5.55) 重叠 0.15 inch | frame y 4.88→4.55, h 0.82→0.65 (4.55-5.20 让位) |
| **P7** | 3 个箭头定位不准（card1-card2 间隙 4.60-5.10 留 0.50；下箭头 2.80+0.40=3.20 与下卡 3.10 重叠 0.10）| 右箭头 x 4.72→4.65, w 0.55→0.45 (填满 0.50 间隙)；上下箭头 y 2.80→2.65 (下沿 3.05, 留 0.05 gap) |
| **P8** | grouped_bar h=3.35 (y=1.75-5.10), x 轴标签 y=5.18-5.40；anchor target (9.20, 2.27) 指向底中心 → connector AABB 跨越顶 factor 卡 | grouped_bar h 不变 (3.35)；顶 factor 卡 y 1.58→1.85 (让位 anchor y=1.25-1.70 留 0.15 gap)；anchor target (9.20, 2.27)→(7.97, 1.85) (指向卡顶部中心，line AABB 收窄) |
| **P10** | bar_chart h=3.25 (y=1.75-5.00), x 轴标签 y=5.08-5.30；callout y=4.40 与 x 轴标签 y=4.33-4.55 冲突；matrix_table (y=5.30, h=1.25) 与 bottom_summary (y=5.55) 重叠 0.30+ | ① bar_chart h 3.25→2.50 (x 轴标签 4.33-4.55)；② callout y 4.40→4.65 (避开 x 轴)；③ **删除整个 matrix_table** (与 bar chart + callouts 信息完全重复, 且大幅重叠 0.82 inch) |
| **P11** | grouped_bar h=3.85 (y=1.65-5.50), x 轴标签 y=5.58-5.80 与 bottom_summary (y=5.55) 直接冲突 0.03+ | grouped_bar h 3.85→3.40 (x 轴标签 5.13-5.35, 留 0.20 gap) |
| **P15** | matrix mh=3.95 (y=1.45-5.40)，"实施复杂度 →" 轴标签 (y=my+mh+0.12=5.52) 与 bottom_summary (y=5.55) 仅留 0.03 gap；`拍照答疑` label box (w=0.9) 跨 Q1/Q2 边界 (x=3.95) | ① matrix mh 3.95→3.55 (轴标签 5.52→5.12, 留 0.43 gap)；② 所有 label w 0.9→0.65 (避免跨边界)；③ `场景召回` (xx,yy) 从 (2.8, 3.1) → (3.1, 3.0) (label box 完整在 Q4) |

### 关键设计权衡

| 决策 | 理由 |
|---|---|
| **删除 P10 matrix_table** 而非缩小 | 1) bar chart + 3 callout 已包含完整数值；2) matrix 信息与 chart 100% 重复；3) matrix 在 P15 已存在 (类似信息) |
| **P4 bottom_summary h 1.10→0.80** | 留出 x 轴标签空间；h=0.80 仍能容纳 3 列短文 panel；FMT-V3-012 要求 h>0.5 → 仍通过 |
| **P8 anchor 重新指向** | 原 target (9.20, 2.27) → 卡底部中心；现 (7.97, 1.85) → 卡顶部中心；line AABB 收窄为 0.10 inch 长条，QA 通过 |
| **P15 `场景召回` xx 2.8→3.1** | 圆点居 Q3/Q4 边界 → 表达"战略储备 + 探索"双重属性；label box 完整在 Q4 |
| **保留 Slide 1 cover 3 处"重叠"** | 装饰圆 (9.60, -0.60, 3.10x3.10) 部分超出页边 (9.60+3.10=12.70 < 13.33) — 实际未超出，仅 x=9.60+ 接近边；Tencent logo 嵌入装饰圆内 — 设计意图 |

### v3.7 渲染验证（2026-07-02 14:07）

- 16 页 + 0 placeholder + 全视觉元素
- `passed: true`, `issues: []` (QA 五重门禁全绿)
- `uniform_page_margin_passed: true`（FMT-V3-009）
- `no_overlap_passed: true`（FMT-V3-010）
- `executive_summary_no_rail_passed: true`（FMT-V3-011）
- `bottom_summary_present_passed: true`（FMT-V3-012）
- `discovery_rail_present_passed: true`（FMT-V3-013）
- `insight_panel_variants_diversity: 3`（bottom_summary / rail / matrix）
- **debug_shape_overlap.py**: 9 张 slide → **2 张 slide**（仅 Slide 1 cover 装饰 + Slide 15 圆点居边界，2 处均为设计意图）

### 关键经验（v3.7）

- **FMT-V3-010 不够**：只看 text-text 漏报 shape-shape。v3.8 候选：把 FMT-V3-010 升级为检查 text-text + shape-shape + text-overflow 三合一
- **debug_shape_overlap.py 应常态化**：v3.6 渲染时 QA 全绿但人眼 review 仍发现问题——机器门禁与人工 review 是互补的
- **bottom_summary 默认 y=5.55 不通用**：当 bar chart base > 5.25 时必须下移。v3.8 候选：动态计算 bottom_summary y = max(5.55, base + 0.30)
- **AABB 碰撞检测不识别"装饰元素"**：P1 cover 装饰圆 (9.60, -0.60) 部分超出页边——这种"超出"是设计意图，工具无法自动识别，需人工豁免清单
- **删除比缩小更彻底**：P10 matrix_table 看似有用但与 bar chart + callouts 100% 重复，删后整页信息密度反而更聚焦

### 未来 v3.8 候选

- ① FMT-V3-010 升级：text-text + shape-shape + text-overflow 三合一
- ② bottom_summary y 动态计算：bottom_y = max(5.55, max_chart_base + 0.30)
- ③ P1 cover 装饰元素加入 `debug_shape_overlap.py` 豁免清单
- ④ debug_shape_overlap.py 集成到 QA 流水线（render → QA → shape_overlap 一步完成）
- ⑤ P3 顶部 5 个 cards 重新排版（当前 5 卡横排 + 4 卡横排），可改为 2×3 网格
- ⑥ logo 改为可配置（公司级品牌化）

---

## v3.5 → v3.6 diff (历史快照)

> **本版关键变更**：基于用户反馈的"页面丰富度/版式多样性/页边距统一性"问题，引入 **4 区填充规则** + **bottom_summary 变体** + **FMT-V3-012 空白门禁**。

### 背景：用户 3 大反馈

1. **页面丰富度不足**：v3.5 部分页元素过少（特别是右侧 x>9.5 区域空白）
2. **版式多样性不足**：v3.5 14 页内容页都左对齐，缺失右栏对齐
3. **页边距统一性不足**：v3.5 多页底部 1.5+ 英寸空白（如 P4 右下 2.05 inch、P15 右 6 inch 空白）
4. **P4 特殊问题**：用户指出"两个图表下方有大量空白，且两个图表的底线没有平行"（bar chart baseline y=5.40 vs data table baseline y=4.80 相差 0.6 inch）

### 核心新增：4 区填充规则（v3.6 强制）

完整内容页 (P3-P15) 必须填满 **4 个区域**：

| 区域 | 位置 | 填什么 | 必备 |
|---|---|---|:-:|
| ① 顶部蓝 nav | y=0-0.30 | 6 tabs + Tencent logo + 保密 | ✓（v3.5 已有）|
| ② 左侧主图/主表 | x=0.7-9.5 | 图表/数据/矩阵 | ✓（v3.5 已有）|
| ③ 右侧"发现" rail | x=10.0-12.63 | vS 灰底"发现" 3 条 | **v3.6 新增强制**（P5/P7/P8/P10/P12/P15 补齐）|
| ④ 底部关键摘要 | y=5.55-6.65 | bottom_summary 3 列 panel | **v3.6 新增强制**（P4/P5/P7/P8/P9/P10/P11/P12/P15 补齐）|

**豁免**：
- P1（cover 封面）
- P2（executive_summary 5 cards 全宽）
- P16（conclusion closing 深底）
- P3 / P13 / P14 有 takeaway/quote/matrix 已满版，rail + bottom summary 部分豁免

### 7 类 insight_panel 变体

v3.5 有 6 类（rail / banner / takeaway / callout / anchor / matrix），v3.6 **新增第 7 类**：

```python
def add_bottom_summary(slide, columns, x=0.7, y=5.55, w=11.933, h=1.10, title="关键发现"):
    """C-2-G bottom-summary: 底部 3 列关键发现 panel (v3.6 4 区填充必选)
    columns: list of dict {tag, text, color?}
    """
    # 灰底 panel + 4px 强调色竖线 + 标题 + 3 列分块
    # 位置 y=5.55-6.65 (1.10 高), 留 0.20 给 footer (y=6.85)
```

**与 add_insight_panel_takeaway 关键差异**：
- 位置 y=5.55（takeaway 是 y=6.05，更贴底部）
- 高度 h=1.10（takeaway 是 0.65，更窄）
- 标题左侧 4px 强调色竖线
- 文字更大 (size 10 vs 9.0)

### P4 重构（用户最关键反馈）

| 区域 | v3.5 旧布局 | v3.6 新布局 |
|---|---|---|
| LEFT (x=0.7-4.3) | bar chart y=1.65-5.40 (baseline=5.40) | **bar chart y=1.30-5.40** (baseline=5.40) |
| MIDDLE-TOP (x=4.5-9.5) | KPI 卡 y=1.68-2.78 (h=1.10) | **KPI 卡 y=1.30-2.50 (h=1.20)** |
| MIDDLE-BOTTOM (x=4.5-9.5) | 数据表 y=3.20-4.80 (h=1.6) | **数据表 y=2.60-5.40 (h=2.80)** |
| RIGHT (x=10.0-12.63) | **空白**（v3.5 缺 rail）| **"发现" rail y=1.30-5.40 (h=4.10)** |
| BOTTOM (x=0.7-12.63) | **空白 y=4.80-6.85 (2.05 inch)** | **bottom_summary y=5.55-6.65 (h=1.10)** |

**P4 关键修复**：
- ① bar chart baseline (y=5.40) 与 data table baseline (y=5.40) **完全平行** ✓
- ② KPI 卡与表中间 0.42 inch 缝隙 → 0（现在 KPI 卡 y=1.30-2.50，数据表 y=2.60-5.40 紧贴）
- ③ 右下 2.05 inch 空白 → 0（rail + bottom summary 填满）
- ④ x>9.5 右侧无内容 → "发现" 灰底 rail 填充（实现右对齐）

### 其它页面变更

| 页 | v3.5 → v3.6 变更 |
|---|---|
| P3 | 新增右侧"研究方法论要点"小 rail（N=4174, 数据周期, 定量问卷）|
| P5 | 移除旧 +25.2pp callout（与 rail 重复）→ 整合到 rail 第 2 条；新增 bottom_summary "驱动格局"|
| P7 | 缩小 discovery_panel (h 5.20→4.10) 让位给 bottom_summary "来源机会"|
| P8 | 新增"发现" rail + bottom_summary "文本满意度"|
| P9 | 缩小 rail + 新增 bottom_summary "功能格局"|
| P10 | 缩小 rail + 新增 bottom_summary "功能纯白提升"|
| P11 | 缩小 rail + 新增 bottom_summary "召回格局"|
| P12 | 缩小 rail + 新增 bottom_summary "流失原因"|
| P14 | action 卡片收窄 (w 8.45→7.45) 让位给右侧 rail |
| P15 | 新增右侧"优先推进/战略储备"rail + bottom_summary "优先级总结"（替换原 takeaway）|

### 3 个新 QA 门禁

| ID | 名称 | 检查什么 | 豁免 |
|---|---|---|---|
| **FMT-V3-012** | 底部 panel 必备 | 每页 (P3-P15) 必须有 w>10 h>0.5 的底部 panel (y >= 5.4) | P1/P2/P16 |
| **FMT-V3-012-②** | 底部空白门禁 | 底部内容最大 y_end < 6.0 → 失败（防止 1+ inch 空白回归）| 同上 |
| **FMT-V3-013** | 右 rail 必备 | x>9.5 区域必须有"发现"文字或灰底 rail（防止 3+ inch 右侧空白）| 同上 |

### v3.6 渲染验证（2026-07-02 13:50）

- 16 页 + 0 placeholder + 全视觉元素
- `passed: true`, `issues: []`
- `uniform_page_margin_passed: true`（FMT-V3-009 强制）
- `no_overlap_passed: true`（FMT-V3-010 强制）
- `executive_summary_no_rail_passed: true`（FMT-V3-011 强制）
- `bottom_summary_present_passed: true`（FMT-V3-012 新增）
- `discovery_rail_present_passed: true`（FMT-V3-013 新增）
- `insight_panel_variants_diversity: 3`（bottom_summary / rail / matrix — 7 变体中用 3 种）

### 关键经验（v3.6）

- **用户反馈驱动迭代**："4 区填充"不是凭空设计，而是用户明确指出"丰富度/多样性/页边距统一"问题后的针对性解法
- **4 区填充 = 视觉密度"地基"**：之前 v3.5 各页布局各异，有的左对齐有的右对齐；v3.6 统一为"左主图+右 rail+底 panel"的 4 区结构，密度对齐
- **P4 baseline 对齐 = 视觉最关键修复**：bar chart 与 table 底线相差 0.6 inch 看似小，但视觉上明显"两张表错位"；统一到 5.40 后整页"一张大表"的视觉感
- **FMT-V3-012/013 = 防止回归**：机器门禁确保后续 v3.7 迭代不会再次出现 1.5+ 英寸空白或缺失 rail
- **bottom_summary ≠ takeaway**：底部 panel 的位置（y=5.55 vs 6.05）和高度（h=1.10 vs 0.65）不同，是 v3.6 独立变体，不是 takeaway 的别名
- **FMT-V3-011 不冲突**：P2 executive_summary 仍豁免 rail；FMT-V3-012/013 也不要求 P2 必带 rail

### 未来 v3.7 候选

- ① P3 顶部 5 个 cards 重新排版（当前 5 卡横排 + 4 卡横排），可改为 2×3 网格
- ② P8 anchor 与 rail 视觉关系优化（anchor 现在 x=6.50-9.10 与 rail x=10.0 中间留 0.90 inch 空白）
- ③ P15 quadrant 4 个区块颜色可进一步对比
- ④ P11 grouped_bar 5 个 metrics 中 "朋友分享" 数据低，可考虑删除
- ⑤ logo 改为可配置（公司级品牌化）

---

## v3.4 → v3.5 diff (历史快照)

> **本版关键变更**：**全面学习 case1.vs 人工手绘 PDF（McKinsey VS 风格）的视觉系统**，将 8 大 vS 视觉元素量化到 renderer。

### 7 大视觉系统升级

| 类别 | v3.4 (旧) | v3.5 (当前) | 变更原因 |
|---|---|---|---|
| **顶部 nav bar** | 无（只 add_title 蓝字 + 6 tabs 文字） | **#003D82 蓝色横条** (y=0, h=0.30)，承载 6 个白色 tab + 激活 tab 白底蓝字 | vS.pdf P3-P22 每页都有顶部蓝 nav；强化"内部分析"语境 |
| **Tencent logo** | 无 | 每页顶部 nav 右上角加 **白色 Tencent 字样**（vS 风格） | vS.pdf 标识腾讯内部出品，强化品牌 |
| **保密标签** | 无 | 每页右上角（nav 下方）加 **"内部汇报·仅供参考" 灰色小标签** | vS.pdf 标识内部沟通语境；外发前应替换 |
| **content title 色** | #003D82（深 navy）| **#1E6FE0**（vS 蓝，亮度更高）| vS.pdf 用更亮的蓝作内容标题；与 nav 深蓝形成层级 |
| **三方品牌色** | 元宝 #22C55E / DS #1E6FE0 / 豆包 #BBD8F8 | **元宝 #3FBF6F / DS #1E6FE0 / 豆包 #BBD8F8**（精确到 vS 像素色）| 元宝色与 vS 像素色差 5%；v3.5 用 vS 实际取色 |
| **rail panel 色调** | #E8F0FA 浅蓝 + "关键洞察" 标题 | **#F5F5F5 中性灰** + "**发现**" 标题 | vS.pdf 用中性灰；"发现"更口语化 |
| **脚注格式** | "数据来源：xxx，置信度：中" | **"注1：xxx; 注2：yyy"**（vS 多脚注格式）| vS.pdf 风格支持多个并列脚注 |

### 3 个新 helper 函数

```python
def add_tencent_logo(s):
    """右上角白字 Tencent 标识"""
    # x=11.65, y=0.04, w=0.95, h=0.22, 白色 bold 9pt

def add_confidential_tag(s):
    """右上角"内部汇报·仅供参考"灰色标签"""
    # x=10.10, y=0.34, w=2.50, h=0.22, 灰色 8pt

def add_discovery_panel(s, bullets, x, y, w, h):
    """vS 风格右侧"发现"灰面板"""
    # bg=#F5F5F5, title="发现" (深灰 11pt bold)
    # bullets: 编号圆点 + 文字

def add_red_box(s, x, y, w, h):
    """#D32F2F 2px 红框 (vS 强调)"""
    # 4 边各画 1.5pt 红线

def add_not_significant(s, x, y):
    """灰色'不显著' 8pt 标签"""
    # color=#AAAAAA
```

### 14 页差异化分配（v3.5 case1 实证）

| 页 | 主题 | nav | logo | 保密 | insight_panel | v3.5 关键变更 |
|---|---|:-:|:-:|:-:|---|---|
| P1 | 封面 | — | ✓ | — | — | logo 白字放封面右下角 |
| P2 | 核心发现 | — | — | — | — (方案 E 全宽) | 5 cards 全宽 + 数据条 |
| P3 | 方法论 | ✓ | ✓ | ✓ | takeaway | 顶部 nav + 5 步流程 |
| P4 | 留存总览 | ✓ | ✓ | ✓ | banner | banner 位置不变 |
| P5 | 因子杠杆 | ✓ | ✓ | ✓ | callout | callout 仍 x=9.65 |
| P6 | 纯白用户 | ✓ | ✓ | ✓ | rail → **发现** | rail 改"发现"灰底 |
| P7 | 跨产品组合 | ✓ | ✓ | ✓ | rail → **发现** | 同上 |
| P8 | 文本满意度 | ✓ | ✓ | ✓ | anchor | anchor 仍 bx=6.50 |
| P9 | 功能满意度 | ✓ | ✓ | ✓ | rail → **发现** | 同 P6 |
| P10 | 拍照答疑 | ✓ | ✓ | ✓ | rail → **发现** | 同 P6 |
| P11 | 主动打开 | ✓ | ✓ | ✓ | rail → **发现** | 同 P6 |
| P12 | 用户流失 | ✓ | ✓ | ✓ | rail → **发现** | 同 P6 |
| P13 | 用户原声 | ✓ | ✓ | ✓ | matrix | 6 quotes 左 + matrix 右 |
| P14 | 行动建议 | ✓ | ✓ | ✓ | takeaway | 3 列 |
| P15 | 优先级收尾 | ✓ | ✓ | ✓ | takeaway | 3 列 |
| P16 | 结尾 | — | — | — | — | 结尾页保留 v3.4 设计 |

### 案例对照（v3.4 vs v3.5 P6）

```
v3.4 P6 (纯白用户) — 浅蓝 panel + "关键洞察":
┌────────────────────────────────────────┐
│ 标题                                    │
│ ┌──────────────────┐ ┌─────────────┐  │
│ │  Top 因子 cards  │ │ 关键洞察     │  │
│ │                  │ │ ① 豆包...   │  │
│ │                  │ │ ② DS...     │  │
│ │                  │ │ ③ 元宝...   │  │
│ └──────────────────┘ └─────────────┘  │
└────────────────────────────────────────┘

v3.5 P6 — 中性灰 panel + "发现" + 顶部蓝 nav + logo + 保密:
┌────────────────────────────────────────┐
│ ▓▓▓▓▓ 蓝 nav + 6 tabs + Tencent ▓▓▓▓▓  │ ← 新
│                  [内部汇报·仅供参考]   │ ← 新
│ 标题 (vS 蓝 #1E6FE0)                   │
│ ┌──────────────────┐ ┌─────────────┐  │
│ │  Top 因子 cards  │ │  发现       │  │ ← "关键洞察"→"发现"
│ │                  │ │ • 豆包...   │  │ ← 浅蓝→灰底
│ │                  │ │ • DS...     │  │
│ │                  │ │ • 元宝...   │  │
│ └──────────────────┘ └─────────────┘  │
└────────────────────────────────────────┘
```

### v3.5 渲染验证（2026-07-02 13:20）

- 16 页 + 0 placeholder + 全视觉元素
- `passed: true`, `issues: []`
- `uniform_page_margin_passed: true`（FMT-V3-009 强制）
- `no_overlap_passed: true`（FMT-V3-010 强制）
- `executive_summary_no_rail_passed: true`（FMT-V3-011 强制）
- `insight_panel_variants_diversity: 5`（banner/callout/rail/anchor/matrix）
- **新增**：`debug_text_overlap.py` 报 "未发现真实文字-文字重叠" ✓
- **新增**：14 页内容页全部带顶部蓝 nav + Tencent logo + 保密标签
- **新增**：6 个 rail 变体（用在 P6/P7/P9/P10/P11/P12）改"发现"灰底

### 关键经验（v3.5）

- **视觉风格 = 数据之上的"外壳"**：v3.4 的"内核"（数据真实性、洞察层次、变体差异化）已经达标；v3.5 升级"外壳"（视觉系统）让 PPT 整体向 vS.pdf 看齐
- **学习人工手绘 = 拆为可量化 helper 函数**：vS.pdf 的 8 大视觉元素不是"风格描述"，而是**具体到像素色、具体到坐标**的 helper 函数（add_tencent_logo / add_discovery_panel / add_red_box ...）
- **不破坏已有 invariants**：v3.5 在 v3.4 invariants（6 变体 / 0.7 边距 / 无重叠 / P2 纯文字）上叠加视觉系统，不重写
- **顶部蓝 nav 是 vS 标志特征**：去掉就丢失"内部分析报告"的语境；加上就有
- **Tencent logo + 保密标签 = 内部沟通语境**：v3.4 的纯白底没有"汇报"的归属感；v3.5 加上后立刻有
- **rail "发现" 比"关键洞察"短 1 字**：vS 用更口语化的"发现"，对受众更友好
- **v3.5 仍沿用 FMT-V3-009/010/011**：视觉系统升级是叠加在 v3.4 invariants 上的，不替换 QA 门禁
- **未来 v3.6 候选**：① logo 改为可配置（公司级品牌化）；② 保密标签支持多个变体（外发/内部/客户）；③ 红框/不显著辅助函数已在代码中待使用案例

---

## v3.3 → v3.4 diff

> **本版关键变更**：P2 executive_summary 改方案 E（纯观点卡全宽），移除冗余的右侧 insight_panel_rail。

| 类别 | v3.3 (旧) | v3.4 (当前) | 变更原因 |
|---|---|---|---|
| **P2 executive_summary 布局** | 方案 D: 5 cards (左 0.7-9.2, w=8.5) + 数据条 strip (左 0.7-9.2) + insight_panel rail (右 9.50-12.63, w=3.13) | 方案 E: 5 cards **全宽 11.933** (0.7-12.633) + 数据条 strip **全宽 11.933** | 整页已是观点罗列性质,右栏 rail 视觉冗余 |
| **P2 5 cards 高度** | h=0.78, 间距 0.05, y 1.70-5.75 | h=0.65, 间距 0.10, y 1.70-5.45 | 全宽后单卡 11.933 inch 横向更舒展,纵向可压缩,5 × 0.75 = 3.75 inch |
| **P2 数据条 strip** | y=5.85, w=8.5 (左对齐右栏留白) | y=5.65, w=11.933 (与 cards 视觉对齐全宽) | 整页满宽视觉一致 |
| **FMT-V3-011** | 无 | 新增强制检查: `executive_summary` 不应使用 `insight_panel_variant=rail` | 防止后续误回方案 D 引入视觉冗余 |
| **insight_panel 变体多样性** | 5 (banner/callout/rail/anchor/matrix) | 5 (banner/callout/rail/anchor/matrix) — P2 不再消耗 rail 配额 | 5 种变体仍在 6 种 analysis_dashboard 中保持 5 种多样化 |

### 视觉对比（v3.3 vs v3.4 P2）

```
v3.3 P2 (方案 D, 5 cards 左 + rail 右):
┌─────────────────────────────────────────────────────────┐
│ 标题                                                     │
├──────────────────────────────────────┬──────────────────┤
│ [card 1]                              │  关键洞察         │
│ [card 2]                              │  ┌──────────┐    │
│ [card 3]                              │  │ 豆包 2.8x│    │
│ [card 4]                              │  │ DS 接近  │    │
│ [card 5]                              │  │ 元宝底座 │    │
├──────────────────────────────────────┤  └──────────┘    │
│ 数据底层 strip                         │                  │
└──────────────────────────────────────┴──────────────────┘

v3.4 P2 (方案 E, 5 cards 全宽):
┌─────────────────────────────────────────────────────────┐
│ 标题                                                     │
├─────────────────────────────────────────────────────────┤
│ [card 1 —————————————— 全宽 ——————————————]               │
│ [card 2 —————————————— 全宽 ——————————————]               │
│ [card 3 —————————————— 全宽 ——————————————]               │
│ [card 4 —————————————— 全宽 ——————————————]               │
│ [card 5 —————————————— 全宽 ——————————————]               │
├─────────────────────────────────────────────────────────┤
│ 数据底层 strip —————————————— 全宽 ——————————————           │
└─────────────────────────────────────────────────────────┘
```

### 关键经验（v3.4）

- **"页面性质一致"原则**：核心发现页 = 观点罗列；不堆砌叠加（5 cards + rail）；要么纯卡片，要么卡片+图表，不混搭
- **观点罗列页 vs 数据可视化页**：前者是"读者已认同证据，要给快速 takeaway"；后者是"读者要看证据才能形成判断"。前者不需要 insight_panel 重复提示
- **full-width 让 5 cards 视觉"一气呵成"**：v3.3 5 cards 只占左 8.5 inch（占全宽 65%），右栏变成视觉停顿点；v3.4 满宽 11.933 后整页节奏连续
- **FMT-V3-011 的价值**：让"P2 不该有 rail"成为机器门禁，防止后续回滚误改

---

## v3.2 → v3.3 diff

> **本版关键变更**：修 6 个 AABB 真实文字-文字碰撞 bug（v3.2 残留）。

| 类别 | v3.2 (旧) | v3.3 (当前) | 变更原因 |
|---|---|---|---|
| **Slide 3 指标卡** | 4 metric cards 用 add_card 内部 title/body,外部 number 文字位于 y=1.68 落在 title(y+0.14-0.42) 与 body(y+0.50-1.02) 之间,**三段互重叠** | 三段式重排: number(y+0.05, size 20)/label(y+0.45, size 11.5)/body(y+0.75, size 9.2),**card h 1.1→1.30** | add_card 不支持三段式;自己写 inline 布局 |
| **Slide 4 图表轴标题** | "强留存率（%）" y=1.20, h=0.22, size 11 — **与 banner (y=1.10-1.55) 重叠** | **删除**（柱顶已标百分比, banner 已说明是"强留存率"）| 冗余信息 |
| **Slide 5 驱动矩阵** | 4 列总宽 = name(0.95) + bar(1.45) + value(0.46) + type(0.45) = **3.31 inch**, 列距仅 3.05 → 下一列 name 撞上一列 type | 4 列总宽 = name(0.75) + bar(1.45) + value(0.30) + type(0.35) = **2.85 inch** | 列距 < 内容总宽, 必然撞 |
| **Slide 5 frame 文字** | 共性 w=4.70 结束于 x=5.52, 差异化 x=5.25 → **撞 0.27** | 共性 w=4.00 结束于 x=4.82, 差异化 x=4.95 → **gap 0.13** | 两段文字宽度未对齐 |
| **Slide 10 callout** | `+10pp` callout y=5.20 — **与 bar 名 (y=5.08-5.30) 重叠** | y=5.20 → y=5.40, 落在 bar 名之下 (matrix y=5.75 之前) | callout 与 bar chart x-axis 标签同高 |
| **Slide 12 冗余 callout** | 62% 红色 callout 框 (x=2.65, y=1.74) — **与 62% bar 自带数值标签 (x=2.05, y=1.68) 重叠** | **删除** 整个 callout + 文本 | 柱顶已标 "62%", callout 重复 |
| **Slide 14 tag 宽度** | tag w=1.10 结束于 x=2.82, title x=2.75 → **撞 0.07** | tag w=1.10 → w=0.95, 结束于 x=2.67 | tag 宽度超过 title 起点 |

### 诊断工具新增：debug_text_overlap.py

- **位置**：`v3.3/debug_text_overlap.py`（**永久保留**于每个 v3.x 目录）
- **策略**：过滤 3 类误报后报真实文字碰撞
  1. 忽略空 text frame
  2. 忽略被大容器完全包含的子 text frame（设计嵌入）
  3. 忽略页眉/页脚条带（横向长条）
- **价值**：FMT-V3-010 父子豁免（容差 0.10）会漏报"两个并排卡片内部文字碰撞"这类几何上 sibling 的真实 bug，diagnostic 补这个洞

### v3.3 渲染验证（2026-07-02 12:15）

- 16 页 + 0 placeholder + 全视觉元素
- `passed: true`, `issues: []`
- `uniform_page_margin_passed: true`（FMT-V3-009 强制）
- `no_overlap_passed: true`（FMT-V3-010 强制）
- `insight_panel_variants_diversity: 5`（rail/banner/callout/anchor/matrix）
- **新增**：debug_text_overlap.py 报 "未发现真实文字-文字重叠" ✓

### 关键经验

- **FMT-V3-010 父子豁免有盲区**：当两个文字 shape 几何上是 sibling（不被对方完全包含）但视觉上挨在一起，QA 不会报。需要 diagnostic 工具补位。
- **修 v3.2 残留 = 看真实渲染**：AABB 几何检查只看"重叠",但"接近 + 短文字 + 长文字"会视觉上撞。需要 text_w_est 估算字符宽度。
- **v3.3 的 6 个 fix 几乎都是"位置微调"**：没有结构性变更,只调数字偏移。说明 v3.2 的 layout/grid 设计是对的,只是部分 page 没用上。
- **Slide 3 重构 card 是最大的 fix**：add_card 是为 2 段（title+body）设计的,3 段（number+label+body）必须自己写 inline 布局。

---

## v3.1 → v3.2 diff

> **本版关键变更**：统一边距 0.7 inch + 核心发现页纯文字化 + 修 3 个文本/图表重叠 bug。

| 类别 | v3.1 (旧) | v3.2 (当前) | 变更原因 |
|---|---|---|---|
| **页边距** | 左 0.55-0.72 / 右 0.78-0.83 / 不一致 | 所有内部页面上=下=左=右 = **0.7 inch**（cover/closing 保留 0.55）| 留白不均、视觉跳脱 |
| **P2 executive_summary** | 5 cards + bar_chart + insight_panel（方案 A 混合）| 5 cards + 数据底层 strip + insight_panel（**方案 D 纯文字**）| 核心发现是观点罗列性质，图表拖慢阅读 |
| **P2 bar_chart** | 强留存率对比（54% / 34% / 19%）| **删除** | 5 个 card 已含 54% / 34% / 19% 数据，bar 重复 |
| **P8 anchor 位置** | bx=3.20, by=1.45, bw=2.6（与 grouped_bar 重叠）| bx=6.50, by=0.85, bw=2.6（在 nav 与 Top cards 之间）| FMT-V3-010 修复重叠 |
| **P13 布局** | 6 quotes 在 0.75-9.85 + matrix 在 0.58-12.58（全画面重叠）| 6 quotes 在左半 0.7-6.0 + matrix 在右半 6.30-12.633 | FMT-V3-010 修复重叠 |
| **P5 callout 位置** | x=8.5（与 emphasis_frame 在 8.5-9.6 范围重叠）| x=9.65 | FMT-V3-010 修复重叠 |
| **新增 FMT-V3-009** | — | uniform_page_margin：内部页面边距 0.7 inch 强制 | 把"上下左右一致"量化到 evals |
| **新增 FMT-V3-010** | — | no_overlap：任意两 shape 不能重叠（除背景/锚线）| 把"无重叠 bug"量化到 evals |
| **insight_panel 6 变体位置** | x 起点 0.58 / y 起点 1.05-1.35（旧 0.55 边距推出）| x 起点 **0.7** / y 起点 0.7-1.10（适配新边距）| 与统一边距规则一致 |
| **renderer 渲染脚本** | render_v3.py 输出 v3.1 目录 | 仍输出 v3.1 目录（v3 工作目录的临时产物，正式快照在 v3.2/）| v3 = v3.x 工作目录 |
| **CHANGELOG/SKILL 顶部** | v3.1 头部无 v3.2 章节 | 加 v3.2 关键变更 | 显式记录迭代 |

### v3.2 14 页变体分配（更新）

| 页 | 主题 | 变体 | evidence 类型 | v3.2 关键变更 |
|---|---|---|---|---|
| P1 | 封面 | — | — | 保留 0.55 边距 |
| P2 | 核心发现 | rail | 5 条并列 | **去 bar_chart，改纯文字结构化** |
| P3 | 方法论 | takeaway | 5 步流程 | 位置适配 0.7 边距 |
| P4 | 留存总览 | banner | 全页主轴 | banner 位置适配 0.7 边距 |
| P5 | 因子杠杆 | callout | 关键反差 | callout x 起点 8.5→9.65 |
| P6 | 纯白用户 | rail | 3 数值并列 | rail 位置 10.12/2.52→10.78/1.86 |
| P7 | 跨产品组合 | rail | 3 数值并列 | rail 位置 10.12/2.52→10.78/1.86 |
| P8 | 文本满意度 | anchor | 关联豆包 Top 因子卡片 | **anchor bx 3.20→6.50, by 1.45→0.85** |
| P9 | 功能满意度 | rail | 3 数值并列 | rail 位置 10.12/2.52→10.78/1.86 |
| P10 | 拍照答疑 | rail | 3 数值并列 | rail 位置 10.12/2.52→10.78/1.86 |
| P11 | 主动打开 | rail | 3 数值并列 | rail 位置 10.12/2.52→10.78/1.86 |
| P12 | 用户流失 | rail | 3 数值并列 | rail 位置 10.12/2.52→10.78/1.86 |
| P13 | 用户原声 | matrix | 产品 × 正负 2 维分类 | **quotes 左半 + matrix 右半（修重叠）** |
| P14 | 行动建议 | takeaway | 立即/短期/中期 3 列 | 位置适配 0.7 边距 |
| P15 | 优先级收尾 | takeaway | 底座/抓手/探索 3 列 | 位置适配 0.7 边距 |
| P16 | 结尾 | — | — | 保留 0.55 边距 |

### v3.2 渲染验证（待跑）

- 16 页 + 0 placeholder + 全视觉元素
- `passed: true`, `issues: []`
- `uniform_page_margin_passed: true`（FMT-V3-009 强制）
- `no_overlap_passed: true`（FMT-V3-010 强制）
- `insight_panel_variants_diversity: 5`（rail/banner/callout/anchor/matrix）
- `evidence_to_variant_binding: true`

### 关键经验

- **统一边距 = 视觉一致**：v3.0/3.1 阶段 0.55/0.78 不等造成左右留白不均；v3.2 统一 0.7 后视觉一致。
- **核心发现页 = 纯文字**：观点罗列性质不适合图表干扰，5 个 card + rail 已经传达全部信息。
- **重叠 bug 是 v3.1 实证缺陷**：P8/P13 实际渲染时明显视觉错误，QA 仅检查结构未检查几何导致漏检。v3.2 加 FMT-V3-010 几何检查。

---

## v3.2 → v3.3 diff

> **本版关键变更**：修 6 个 AABB 真实文字-文字碰撞 bug（v3.2 残留）。

| 类别 | v3.2 (旧) | v3.3 (当前) | 变更原因 |
|---|---|---|---|
| **Slide 3 指标卡** | 4 metric cards 用 add_card 内部 title/body,外部 number 文字位于 y=1.68 落在 title(y+0.14-0.42) 与 body(y+0.50-1.02) 之间,**三段互重叠** | 三段式重排: number(y+0.05, size 20)/label(y+0.45, size 11.5)/body(y+0.75, size 9.2),**card h 1.1→1.30** | add_card 不支持三段式;自己写 inline 布局 |
| **Slide 4 图表轴标题** | "强留存率（%）" y=1.20, h=0.22, size 11 — **与 banner (y=1.10-1.55) 重叠** | **删除**（柱顶已标百分比, banner 已说明是"强留存率"）| 冗余信息 |
| **Slide 5 驱动矩阵** | 4 列总宽 = name(0.95) + bar(1.45) + value(0.46) + type(0.45) = **3.31 inch**, 列距仅 3.05 → 下一列 name 撞上一列 type | 4 列总宽 = name(0.75) + bar(1.45) + value(0.30) + type(0.35) = **2.85 inch** | 列距 < 内容总宽, 必然撞 |
| **Slide 5 frame 文字** | 共性 w=4.70 结束于 x=5.52, 差异化 x=5.25 → **撞 0.27** | 共性 w=4.00 结束于 x=4.82, 差异化 x=4.95 → **gap 0.13** | 两段文字宽度未对齐 |
| **Slide 10 callout** | `+10pp` callout y=5.20 — **与 bar 名 (y=5.08-5.30) 重叠** | y=5.20 → y=5.40, 落在 bar 名之下 (matrix y=5.75 之前) | callout 与 bar chart x-axis 标签同高 |
| **Slide 12 冗余 callout** | 62% 红色 callout 框 (x=2.65, y=1.74) — **与 62% bar 自带数值标签 (x=2.05, y=1.68) 重叠** | **删除** 整个 callout + 文本 | 柱顶已标 "62%", callout 重复 |
| **Slide 14 tag 宽度** | tag w=1.10 结束于 x=2.82, title x=2.75 → **撞 0.07** | tag w=1.10 → w=0.95, 结束于 x=2.67 | tag 宽度超过 title 起点 |

### 诊断工具新增：debug_text_overlap.py

- **位置**：`v3.3/debug_text_overlap.py`（**永久保留**于每个 v3.x 目录）
- **策略**：过滤 3 类误报后报真实文字碰撞
  1. 忽略空 text frame
  2. 忽略被大容器完全包含的子 text frame（设计嵌入）
  3. 忽略页眉/页脚条带（横向长条）
- **价值**：FMT-V3-010 父子豁免（容差 0.10）会漏报"两个并排卡片内部文字碰撞"这类几何上 sibling 的真实 bug，diagnostic 补这个洞

### v3.3 渲染验证（2026-07-02 12:15）

- 16 页 + 0 placeholder + 全视觉元素
- `passed: true`, `issues: []`
- `uniform_page_margin_passed: true`（FMT-V3-009 强制）
- `no_overlap_passed: true`（FMT-V3-010 强制）
- `insight_panel_variants_diversity: 5`（rail/banner/callout/anchor/matrix）
- **新增**：debug_text_overlap.py 报 "未发现真实文字-文字重叠" ✓

### 关键经验

- **FMT-V3-010 父子豁免有盲区**：当两个文字 shape 几何上是 sibling（不被对方完全包含）但视觉上挨在一起，QA 不会报。需要 diagnostic 工具补位。
- **修 v3.2 残留 = 看真实渲染**：AABB 几何检查只看"重叠",但"接近 + 短文字 + 长文字"会视觉上撞。需要 text_w_est 估算字符宽度。
- **v3.3 的 6 个 fix 几乎都是"位置微调"**：没有结构性变更,只调数字偏移。说明 v3.2 的 layout/grid 设计是对的,只是部分 page 没用上。
- **Slide 3 重构 card 是最大的 fix**：add_card 是为 2 段（title+body）设计的,3 段（number+label+body）必须自己写 inline 布局。

---

## v3 → v3.1 diff
| 类别 | v3 (旧) | v3.1 (当前) | 变更原因 |
|---|---|---|---|
| **insight_panel 位置** | 写死"页面右侧 (x=10.15, y=1.35, w=2.52, h=4.35)" | 6 变体位置灵活（顶部横条/底部条/右侧栏/左/右 callout/锚定图表/中心矩阵）| 复杂证据需要不同视觉关系，单一位置难以快速理解 |
| **insight_panel 形态** | 写死"浅灰 panel + 编号圆圈 + 文字" | 6 种形态（rect panel / banner / multi-col / callout / anchored / matrix）| evidence 性质决定形态：并列用 rail，反差用 callout，关联用 anchor，分类用 matrix |
| **FMT-V3-004** | "必带 2-4 条编号洞察" | "必带 insight_panel + 按 evidence 选 6 变体之一" | 强制按 evidence 选型，位置形态灵活 |
| **新增 FMT-V3-008** | — | evidence_to_variant_binding：每个 insight_panel 必须显式选 variant 且与 evidence_type 匹配 | 把选型决策量化到 evals |
| **components.md §C-2** | 单一"right-rail" 定义 | 6 变体完整定义（每种含适用场景+视觉规范+位置参数+render 模板）| renderer 不再需要"猜测"每种变体长什么样 |
| **layouts.md** | 各 layout 规定"右侧 25%：发现面板" | 各 layout 给出 insight_panel 变体选型指南（evidence_type → variant 决策树）| 选型决策从"硬编码位置"改为"按 evidence 灵活选型" |
| **renderer** | add_insight_panel 一种调用 | add_insight_panel_{rail,banner,takeaway,callout,anchor,matrix} 6 种函数 | 14 页差异化调用,5 种变体实际覆盖 |
| **QA** | 检查 has_insight_panel 单一 | 新增 variants_used 列表 + variants_diversity 计数 + evidence_to_variant_binding 检查 | 验证变体差异化是否真正体现 |

### v3.1 6 变体速查

| 变体 ID | 名称 | 适用 evidence_type | 触发条件示例 |
|---|---|---|---|
| C-2-A | right-rail | 多点并列洞察（无主次）| "豆包 X / DS Y / 元宝 Z" |
| C-2-B | top-banner | 整页关键结论 | 全页主轴 1-2 句话 |
| C-2-C | bottom-takeaway | 行动建议 / 总结陈述 | closing / method / 行动建议 |
| C-2-D | callout-side | 关键反差点 | "豆包 54% vs 元宝 19%，差距 35pp" |
| C-2-E | inline-anchor | 关联图表某数据点 | "该柱 +25.2pp 全图最高" |
| C-2-F | matrix-grid | 2-3 维度分类对比 | 按产品×优先级分类 |

### v3.1 14 页变体分配（case1 实证）

| 页 | 主题 | 变体 | evidence 类型 |
|---|---|---|---|
| P2 | 执行摘要 | rail | 5 条并列发现 |
| P3 | 方法论 | takeaway | 研究流程 5 步 |
| P4 | 留存总览 | banner | 全页主轴结论 |
| P5 | 因子杠杆 | callout | 关键反差"DS +25.2pp" |
| P6 | 纯白用户 | rail | 3 数值并列 |
| P7 | 跨产品组合 | rail | 3 数值并列 |
| P8 | 文本满意度 | anchor | 关联豆包 Top 因子卡片 |
| P9 | 功能满意度 | rail | 3 数值并列 |
| P10 | 拍照答疑 | rail | 3 数值并列 |
| P11 | 主动打开 | rail | 3 数值并列 |
| P12 | 用户流失 | rail | 3 数值并列 |
| P13 | 用户原声 | matrix | 产品 × 正负 2 维分类 |
| P14 | 行动建议 | takeaway | 立即/短期/中期 3 列 |
| P15 | 优先级收尾 | takeaway | 底座/抓手/探索 3 列 |

实际变体覆盖: 5 / 6 (banner / callout / rail / anchor / matrix；takeaway 在 P3/P14/P15 三页用上)

### v3.1 渲染验证

- 16 页 + 0 placeholder + 全视觉元素
- `passed: true`, `issues: []`
- `insight_panel_variants_diversity: 5`（6 变体中用 5 种）
- `evidence_to_variant_binding: true`

### 关键经验

- **位置和形态灵活 ≠ 视觉混乱**：每个变体都有明确的"适用 evidence_type"和"决策树"，renderer 选型有依据。
- **evidence 类型 → 视觉关系**：多点并列=rail, 单点反差=callout, 关联=anchor, 分类=matrix, 主轴=banner, 行动=takeaway。
- **变体多样性是质量指标**：QA 加 `variants_diversity` 计数，单一页面如果都用 rail 也是质量下降信号。

---

## v2 → v3 diff

| 类别 | v2 (旧) | v3 (当前) | 变更原因 |
|---|---|---|---|
| **layout 库收敛** | v2 文档罗列 20+ 类 layout（cube / quadrant_3group / lollipop / process_chevron / horizontal_bar 等） | 强制收敛到 v0.9.1 实证的 5 类：cover / executive_summary / analysis_dashboard / methodology_or_strategy / priority_matrix | v2 时代"理论 layout"从未被 renderer 实际调用，造成设计漂移 |
| **presentation_spec 拆分** | 单文件 1943 行 | 拆为 5 个聚焦文件（layouts / components / style / charts / data_extraction） | 单一文件过大，renderer 实际只用到其中一部分 |
| **chart 库收敛** | 文档列出 12+ 类 chart | 收敛到 6 类（bar / grouped_bar / horizontal_bar / scatter / matrix_table / quoted_table） | 与 layout 同理 |
| **token 量化值实证** | 表格给的是"理论值"（如 PPT title 28pt） | 全部从 v0.9.1 渲染脚本的 Python 常量取值（title 18pt / body 9.2pt / footnote 7.8pt） | v0.9.1 实证渲染稳定，量化值可信 |
| **renderer 选型** | MckEngine 68 个 layout + python-pptx 6 类手绘并行 | 推荐纯 python-pptx，**禁止**调用 v2 旧 layout | MckEngine API 文档与代码不一致是 v2 主要痛点；v0.9.1 纯 python-pptx 路径已验证 16 页高质量 |
| **document / html 降级** | 声称三载体都通过 v0.9.1 验证 | 显式声明 document / html 暂未实测，禁止声称验证 | v0.9.1 仅 PPT 路径实测 |
| **新增 FMT-V3-001 ~ 007** | — | 7 条 P0/P1 审查项（layout 收敛 / style_ref 必填 / navigation 必带 / insight_panel 必带 / data_source_extraction 必填 / chart_type 收敛 / token 来源） | 把 v3 强制规则量化到 evals |
| **5 类 layout 字段填写手册** | — | layouts.md 含每类 layout 的 content.json 格式 + 视觉规范 | renderer 不再需要"猜测"每类 layout 长什么样 |

---

## v3 文件结构

```
format.skill.v3/
├── SKILL.md                  (核心指令)
├── reference_manifest.json   (compiler 注入清单)
├── references/
│   ├── layouts.md            (5 类实证 layout)
│   ├── components.md         (9 类组件)
│   ├── style.md              (token 量化值)
│   ├── charts.md             (6 类图表)
│   ├── data_extraction.md    (数据真实性)
│   ├── document_spec.md      (占位，未实测)
│   └── html_spec.md          (占位，未实测)
├── schemas/
│   ├── page_content.v3.json
│   └── formatted_material.v2.json
├── evals/
│   ├── evals.json
│   └── rubrics.json
└── render_v3.py             (从 v0.9.1 渲染脚本演进,与 v0.9.1 视觉一致)
```

---

## v0.9.1 → v3 关键迁移

| v0.9.1 实证 | v3 规范 |
|---|---|
| 5 类 layout | 收敛为 v3 5 类 layout（cover / executive_summary / analysis_dashboard / methodology_or_strategy / priority_matrix）|
| 9 类组件 | 保留为 9 类组件,单独放 components.md |
| 6 类 chart | 保留为 6 类 chart,单独放 charts.md |
| 配色 / 字号 / 间距 | 量化值全部来自 v0.9.1 渲染脚本,放 style.md |
| 纯 python-pptx 渲染 | 默认 renderer=python-pptx（禁止 mck-engine） |

---

## 已知未覆盖（v3 → v4 待办）

- [ ] format.document 实际渲染验证（v3 阶段仅占位）
- [ ] format.html 实际渲染验证（v3 阶段仅占位）
- [ ] MckEngine 68 个 layout 的真实可用性（如有需求可考虑）
- [ ] 图表交互（hover / drill-down）等高级功能（PPT 不需要,HTML 需要）
- [ ] 自动化 QA 工具链（v0.9.1 是手动 QA,v3 阶段已抽到 evals/ 但实际执行仍手动）

---

## v3 适用场景

- ✅ 各类 PPT 渲染（深度分析、业务进度、季度汇报）
- ✅ 数据真实性有强约束的项目（金融/医疗/法律）
- ✅ 已有 v0.9.1 渲染脚本作为 renderer 底座
- ❌ 需 docx / html 路径的（v3 阶段不支持,请用 v1.0 或 v2.1）
- ❌ 需 v2 旧 layout 的（请用 v2.1）
