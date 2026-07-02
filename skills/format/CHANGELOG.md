# Format Skill v3.11 — 公开 CHANGELOG（高层概览）

> **本目录 = format skill v3 完整快照**（v3.11，2026-07-02 14:32 封版）
>
> 详细小版本变更日志（v3 → v3.1 → v3.2 → ... → v3.11 每版 diff）见用户本地开发目录
> `format skill 迭代/format.skill.v3.11/CHANGELOG.md`（约 800 行）。本文件只列**对外可见的
> 关键能力与门禁**。

---

## v3 关键能力（按版本倒序）

### v3.11（2026-07-02）— **中英文字体分离**
- **中文用"楷体"（Kaishu），英文/数字用 "arial"**
- 通过 lxml 给每个 run 同时设 `<a:latin>` + `<a:ea>` + `<a:cs>` 三个 typeface 元素
- python-pptx 的 `p.font.name` 默认只设 `<a:latin>`，中文走 `<a:ea>` 需独立设
- 新增 `_set_dual_font()` helper；`add_text` / `add_para_text` 改用 dual-font 路径
- **跨平台字体备份**（待办）：楷体 macOS/Linux → `"STKaiti"` / `"Noto Serif CJK SC"`

### v3.10（2026-07-02）— **P3 顶部 blocks 文字逻辑重构**
- 旧：`(人话名, 用户数, 描述)` — 读者看不到指标含义
- 新：`(维度名, 数量, 枚举值) + 用户数附加信息` — 三行结构
- 示例："产品组合" (灰 9pt) → "3" (彩色 26pt) + "种产品" → "元宝 / DS / 豆包" (navy 12pt)
- 符合用户反馈的"产品/3/元宝/DS/豆包"逻辑顺序

### v3.9（2026-07-02）— **5 重门禁 + 修 20 处文字溢出**
- 引入 `debug_text_overflow.py` 综合诊断工具（段宽溢出 + 总高溢出 + 隐式 box wrap）
- 修复 20 处真实垂直溢出（Slide 2 5 张 cards body h 0.07→0.22 + Slide 5 driver matrix 列宽调整）
- 5 重门禁全绿：FMT-V3-009 边距 / 010 重叠 / 011 P2 no rail / 012 底部 panel / 013 右 rail

### v3.8（2026-07-02）— **P6 baseline 5.40 全 PPT 统一**
- 修复 P6 scatter + side bars 底差 1.32 inch 问题
- 引入"baseline 5.40"全局视觉基线：所有内容图表/矩阵/表格 baseline = 5.40
- scatter_plot h 4.55→3.98 + side bars base 4.65→5.40 + callout y 4.95→5.70
- 未来 v3.x 候选：FMT-V3-014 baseline 对齐门禁

### v3.7（2026-07-02）— **修 11 处 shape-shape 重叠**
- 引入 `debug_shape_overlap.py` 综合诊断（text-text + shape-shape + text-overflow 三合一）
- 修复 7 张内容页的 11 处真实重叠（P2/P4/P5/P7/P8/P10/P11/P15）
- 最重大修复：P10 删冗余 matrix_table（与 bar chart + callouts 信息 100% 重复）
- 保留 2 张设计意图 slide（cover 装饰圆 + P15 圆点居边界）作为豁免清单

### v3.6（2026-07-02）— **4 区填充 + bottom_summary 第 7 变体**
- 基于用户反馈的"丰富度/多样性/页边距统一"问题
- 强制 P3-P15 填满 4 区：顶部蓝 nav + 左侧主图/主表 + 右侧"发现" rail + 底部 panel
- 新增 `add_bottom_summary()` 第 7 类 insight_panel 变体
- 新增 FMT-V3-012（底部 panel 必备）+ FMT-V3-013（右 rail 必备）
- P4 重构：bar chart 与 data table baseline 完全平行（5.40 统一）✓

### v3.5（2026-07-02）— **case1.vs 视觉系统全面升级**
- 基于 case1.vs 人工手绘 PDF 量化 8 大视觉元素到 renderer
- 顶部蓝 nav (#003D82) + Tencent logo + "内部汇报·仅供参考" 保密标签
- vS 蓝 (#1E6FE0) content title + 三方精确品牌色（元宝 #3FBF6F / DS #1E6FE0 / 豆包 #BBD8F8）
- rail panel 改"发现"灰底 (#F5F5F5) + 注1 脚注格式 + #D32F2F 红框强调
- 新增 helper：`add_tencent_logo` / `add_confidential_tag` / `add_discovery_panel` / `add_red_box`

### v3.4（2026-07-02）— **P2 executive_summary 方案 E 全宽**
- 旧：5 cards (左 8.5 inch) + rail (右 3.13 inch) 视觉冗余
- 新：5 cards 全宽 11.933 + 数据底层 strip 全宽
- 移除冗余右栏 rail（核心发现页 = 观点罗列性质）
- 新增 FMT-V3-011（executive_summary 禁止 rail）防止误回

### v3.3（2026-07-02）— **修 6 处文字-文字碰撞 + debug_text_overlap.py**
- FMT-V3-010 父子豁免（容差 0.10）有盲区，需 diagnostic 工具补位
- 修复 Slide 3/4/5/10/12/14 的 6 个 AABB 真实文字碰撞
- 引入 `debug_text_overlap.py`（过滤 3 类误报：空 text / 容器子元素 / 页眉页脚条带）

### v3.2（2026-07-02）— **统一边距 0.7 inch + P2 纯文字化**
- 所有内部页面 上下左右 = **0.7 inch**（cover/closing 保留 0.55）
- P2 executive_summary 改纯文字（5 cards + 数据底层 strip，去 bar_chart）
- 修复 P8 anchor / P13 matrix / P5 callout 3 处文本/图表重叠
- 新增 FMT-V3-009 边距门禁 + FMT-V3-010 重叠门禁

### v3.1（2026-07-02）— **6 类 insight_panel 变体**
- 旧：单一"右侧固定 panel"
- 新：6 变体（right-rail / top-banner / bottom-takeaway / callout-side / inline-anchor / matrix-grid）
- 选型决策树：多点并列=rail, 单点反差=callout, 关联图表某点=anchor, 分类=matrix, 主轴=banner, 行动=takeaway
- 新增 FMT-V3-008（evidence_to_variant_binding）门禁

### v3（基线）— **layout 库收敛 + 拆分 presentation_spec**
- 旧：v2 罗列 20+ 类 layout（cube/quadrant_3group/lollipop 等从未被 renderer 调用）
- 新：5 类实证 layout（cover / executive_summary / analysis_dashboard / methodology_or_strategy / priority_matrix）
- 拆分 1943 行 monolith 为 5 个聚焦文件（layouts / components / style / charts / data_extraction）
- 量化值全部从 v0.9.1 渲染脚本取值（title 18pt / body 9.2pt / footnote 7.8pt）
- 新增 FMT-V3-001 ~ 007 P0/P1 审查项

---

## QA 五重门禁（强制）

| ID | 名称 | 检查内容 | 豁免 |
|---|---|---|---|
| **FMT-V3-009** | 边距 | 内部页 (x,y,w,h) 必须在 (0.7, 0.7, 11.933, 6.1) 范围 | P1/P16 cover/closing |
| **FMT-V3-010** | 重叠 | 任意两 shape AABB 不能重叠（除背景/锚线/分隔线）| 同上 |
| **FMT-V3-011** | P2 无 rail | executive_summary 禁止 right-rail 变体 | 仅 P2 |
| **FMT-V3-012** | 底部 panel 必备 | P3-P15 必须有 w>10 h>0.5 y≥5.4 的底部 panel | P1/P2/P16 |
| **FMT-V3-013** | 右 rail 必备 | P3-P15 x>9.5 必须有"发现"或灰底 panel | P1/P2/P16 |

---

## 3 个诊断工具（开发者用）

| 工具 | 位置 | 检查什么 |
|---|---|---|
| `tools/debug_text_overlap.py` | v3.3+ | text-text 真实碰撞（过滤 3 类误报）|
| `tools/debug_shape_overlap.py` | v3.7+ | text-text + shape-shape + text-overflow 三合一 |
| `tools/debug_text_overflow.py` | v3.9+ | 段宽溢出 + 总高溢出 + 隐式 box wrap |

---

## 已知未覆盖（v3 → v4 待办）

- [ ] format.document 实际渲染验证（v3 阶段仅占位）
- [ ] format.html 实际渲染验证（v3 阶段仅占位）
- [ ] 跨平台字体备份：楷体 macOS/Linux → `"STKaiti"` / `"Noto Serif CJK SC"`
- [ ] FMT-V3-014 baseline 对齐门禁（同页面 ≥2 张图表底 y ±0.05 inch 内）
- [ ] 自动化 QA 流水线（render → QA五门禁 → shape_overlap → text_overflow）
- [ ] MckEngine 68 个 layout 的真实可用性（如有需求可考虑）
- [ ] 图表交互（hover / drill-down）等高级功能（PPT 不需要，HTML 需要）

---

## 引用关系

- **本地开发目录**：`format skill 迭代/format.skill.v3.11/` — 含 render_v3.11.py + 3 个 debug 工具 + 桌面 PPT 样本
- **renderer**：python-pptx（推荐路径，禁止 MckEngine v2 旧 layout）
- **上一版**：v2.1（已弃用，5 类实证 layout 不支持）
- **下一版规划**：v3.12 候选 = FMT-V3-014 baseline 对齐 + 跨平台字体备份 + add_data_card helper
