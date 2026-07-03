---
name: format
description: "[v3.12] Convert approved page content into a render-ready formal deliverable. v3.12 is the first stable release of the v3 series (a.k.a. 'format skill v3'). It consolidates the v3.6→v3.11 cumulative improvements (4-zone filling, 7-variant insight_panel, baseline 5.40 alignment, text-overflow fixes, P3 顶部 4 blocks 重构, 中英文字体分离 via lxml) on top of the v0.9.1 visual system, and adds the v3.12 hotfix that resolves P0/P1/P2 code-quality issues: (1) extracts 8 layout constants (BLANK_LAYOUT_IDX=6, CONTENT_LEFT=0.7, CONTENT_W=11.933, DISCOVERY_X=10.00, DISCOVERY_W=2.63, DISCOVERY_H=4.10, BOTTOM_Y=5.55, BOTTOM_H=1.10) replacing 16 hardcoded prs.slide_layouts[6] / 0.7 / 11.933 magic numbers across 16 page builders; (2) fixes add_discovery_panel default drift (10.20/1.30/2.83/5.20 → 10.00/1.30/2.63/4.10) aligning with 12 actual caller values; (3) strict mode for silent fallbacks (dict.get('可用性', 0) → dict(...)[...] raising KeyError instead of drawing zero-height bars); (4) removes 8 dead functions (rgb_hex, add_red_box, add_not_significant, add_insight_panel_rail/banner/callout, add_insight_panel alias, add_legend), 1 unused import (MSO_LINE_DASH_STYLE), 1 unused kwarg (layout='3x1'), 1 unused constant (TITLE_EA_FONT); (5) all 5 QA gates green (FMT-V3-009/010/011/012/013). v3.12 preserves v0.9.1 invariants: top blue nav #003D82 + Tencent logo + 内部汇报·仅供参考 保密标签 + vS content title #1E6FE0 + right-side 发现 gray panel + 3-way product palette + 注1:... footnote + #D32F2F red highlight + uniform 0.7-inch margins (FMT-V3-009) + no text overlap (FMT-V3-010) + executive_summary no rail (FMT-V3-011) + bottom_summary required (FMT-V3-012) + discovery rail required (FMT-V3-013) + 4-zone filling (top nav + left main + right rail + bottom panel) + 7-variant insight_panel system."
---

# Format Skill v3.12 (hotfix: layout 漂移修复 + 死代码清理 + strict 模式)

> **本版关键变更（v3.12 hotfix）**：
> 1. **P0 layout 漂移修复**：8 个 layout 常量提取（`BLANK_LAYOUT_IDX=6` / `CONTENT_LEFT=0.7` / `CONTENT_W=11.933` / `DISCOVERY_X=10.00` / `DISCOVERY_W=2.63` / `DISCOVERY_H=4.10` / `BOTTOM_Y=5.55` / `BOTTOM_H=1.10`）；16 个 page builder 中 `prs.slide_layouts[6]` 16 处 → `prs.slide_layouts[BLANK_LAYOUT_IDX]`；`add_insight_panel_takeaway` / `add_insight_panel_matrix` 等内部硬编码的 0.7/11.933 全部常量化。
> 2. **P1 `add_discovery_panel` 默认值修复**：函数签名默认 `(10.20, 1.30, 2.83, 5.20)` → `(10.00, 1.30, 2.63, 4.10)`（与 12 个调用方实际值对齐）；12 个调用方移除冗余参数；P4 纯白特殊 case 显式传 `h=5.20` 保留原行为。
> 3. **P1 `add_bottom_summary` 冗余参数清理**：9 个调用方移除冗余的 `(0.7, 5.55, 11.933, 1.10)` 默认参数（默认就够），P4 总览特殊 case 显式传 `(y=5.80, h=0.80)` 保留原行为。
> 4. **P1 strict 模式**：3 处 `dict.get("可用性", 0)` → `dict(...)["可用性"]`（TEXT_SATISFACTION_CORR 查表），缺 key 时直接 `KeyError` 而非静默画 0 高度 bar。
> 5. **P2 死代码清理**：删除 8 个未用函数（`rgb_hex` / `add_red_box` / `add_not_significant` / `add_insight_panel_rail` / `add_insight_panel_banner` / `add_insight_panel_callout` / `add_insight_panel` 别名 / `add_legend`）+ 1 个未用 import（`MSO_LINE_DASH_STYLE`）+ 1 个未用 kwarg（`layout="3x1"`）+ 1 个未用常量（`TITLE_EA_FONT = "楷体"`）；净减约 250 行 / 17% 体积。
> 6. **QA 5 重门禁全绿**：`FMT-V3-009` uniform_page_margin / `FMT-V3-010` no_overlap / `FMT-V3-011` executive_summary_no_rail / `FMT-V3-012` bottom_summary_present / `FMT-V3-013` discovery_rail_present。
> 7. **保留 v0.9.1 视觉系统**：顶部蓝 nav + Tencent logo + 保密标签 + vS 内容标题 + 三方品牌色 + 灰底"发现" rail + 注1 footnote + 红框强调。
> 8. **保留 v3.6 4 区填充**：顶部 nav + 左侧主图 + 右侧 rail + 底部 bottom_summary。
> 9. **保留 v3.7 7 变体 insight_panel**：right-rail / top-banner / bottom-takeaway / callout-side / inline-anchor / matrix-grid / bottom-summary。
> 10. **保留 v3.8 baseline 5.40 对齐**：全 PPT 16 页图表 baseline = 5.40。
> 11. **保留 v3.9 文字溢出修复**：20 处真实溢出 + `debug_text_overflow.py` 综合诊断工具。
> 12. **保留 v3.10 P3 顶部 4 blocks 重构**：(维度名, 数量, 枚举值) + 用户数附加信息 结构。
> 13. **保留 v3.11 中英文字体分离**：中文 → 楷体 (`<a:ea>`) / 英文/数字 → arial (`<a:latin>`)，使用 lxml `_set_dual_font()` helper。

## Role

把 `page_content.v3` 转为 `formatted_material.v2`。你负责**正式表达、信息层级、来源与缺口呈现、renderer handoff、下游交接**，以及**具体呈现形式规则**（typography / color / spacing / chart / table / asset / 载体特有），但不重新做论点、故事线 或逐字稿。

本 Skill 定义三种载体（`format.ppt` / `format.document` / `format.html`）共有的稳定职责，以及各 capability **自带**的呈现形式规则。本轮只能依据 `output_format` **唯一激活**一个 `format.*` capability；不要自行加载或混用其他载体流程。

## Input readiness

开始前检查：

- 存在 `pages[]` 或 `draft_material.material_units[]`；
- 目标格式已在 report charter 与 active capability 中确定；
- 每个上游单元能追溯 page takeaway、证据、来源和 data gap；
- 需要的原始细节若被投影，应按 `material_refs[].artifact_path` 读取，不能根据 preview 补写事实；
- 呈现形式所需 token（typography / color / chart palette / 资产）已就位或可在 active capability 的呈现形式子节中声明；
- **数据真实性检查（v0.7 新增）**：`visual_object.chart_spec.data_ref` 或 `visual_object.table_data` 中的数据**必须**从原始文档/数据中真实提取，**禁止**使用模拟数据或示例数据。若原始文档中无对应数据，必须在 `gap_display.visible_note` 中声明"数据缺失"，并将 `quality_status` 设为 `partial`。详见 `references/data_extraction.md`。

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
- **Layout 库必须收敛到 5 类实证有效的 layout**（见 `references/layouts.md`）。v3 旧版罗列的 20+ 类 layout（含 cube/quadrant_3group/lollipop）从未被任何 renderer 实际调用过，**v3 起禁止新增**。
- **复杂证据 → 选合适的 insight_panel 变体**（v3.1 新增）。evidence 性质决定视觉关系：多点并列=right-rail，单点反差=callout-side，关联图表某点=inline-anchor，分类归类=matrix-grid，全页主轴=top-banner，行动建议=bottom-takeaway。详见 `references/components.md §C-2` 与 `references/layouts.md §insight_panel 选型`。

## Output contract

严格输出 `formatted_material.v2`，至少包含：

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

## Format capabilities

三个 capability **共享**以下 token 骨架与字段规则，再各自定义**专属**设计能力 + **专属**呈现形式规则。

### 能力索引（_index）

#### 命名空间

```
format.ppt       — 演示稿（≤ 16 页，强叙事；动画克制；图表用 native shape；本 v3 的核心）
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
| `layout_or_structure.layout_type`            | 必须从 active capability 的合法 layout 库中选（**ppt 必须从 5 类实证 layout 中选**）                          |
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
| **字号视觉等效**     | 相同语义元素（标题 / 正文 / 脚注）的视觉等效：PPT `title 18pt` ≈ Doc `title 22pt` ≈ HTML `title 32px`（按 1m 视距测算）                                 |
| **数据一致**       | 同一数据点在三载体下数值 / 单位 / 口径必须完全一致                                                                                                 |
| **缺口标记一致**     | gap 标识符（如 `GAP-001`）在三载体下命名一致                                                                                                |
| **来源编号一致**     | 引用 id（如 `[1] report.pdf §3.2`）在三载体下完全一致                                                                                      |
| **图表配色一致**     | 同 brand 下三载体图表色板必须取自同一 `color.chart.palette[]`                                                                               |
| **token 名字一致** | 共享 token 骨架（`color.brand.primary` / `font.size.title` 等）在三载体的 `style_tokens` 中**名字必须一致**，**取值**按各载体量化表                       |

### 载体差异速查（避免混淆）

| 维度          | PPT                          | Document                | HTML             |
| ----------- | ---------------------------- | ----------------------- | ---------------- |
| 字号单位        | pt                           | pt                      | px               |
| 字号 title    | 18pt                         | 22pt                    | 32px             |
| 字号 body     | 9.2pt                        | 11pt                    | 16px             |
| 字号 footnote | 7.8pt                        | 8pt                     | 12px             |
| 字重 bold     | 600                          | 700                     | 600              |
| 行距 normal   | 1.0                          | 1.5                     | 1.6              |
| 间距单位        | px                           | cm                      | px               |
| margin      | 48px                         | 2.5cm                   | 24px             |
| 栏数          | 12                           | 1                       | 12               |
| 品牌色（v3 默认）  | #0052D9                      | #0052D9                 | #0052D9          |
| 强调色 success | #22C55E                      | #22C55E                 | #3FBF6F（屏幕明亮）    |
| 表格          | 无斑马纹（仅数据）                  | 全框                      | sticky top + 斑马纹 |
| Logo        | 角落                           | 页眉 / 页脚（每页）             | 顶部 nav 旁         |
| 视频          | 嵌入                           | 不推荐                     | 嵌入               |
| 动画          | 克制（fade / build）             | 无                       | 完整（折叠/展开 ≤0.3s）  |
| 响应式         | 无                            | 无                       | 6 断点             |
| 主题切换        | 无                            | 无                       | light / dark 双主题 |
| 脱敏          | 仅内部                          | 仅内部                     | **外发强制**         |
| 键盘导航        | 无                            | 无                       | **强制**           |
| 加载性能        | 离线                           | 离线                      | LCP ≤ 2.5s       |

> **PPT 字号速查调整说明（v3 → v3）**：v0.9.1 渲染脚本的实测字号：title 18pt / body 9.2pt / footnote 7.8pt。v3 表格给的 28/14/9 是把 vS.pdf 的"演讲字号"当成了 PPT 通用字号（演讲场景字号大，但通用 PPT 投屏 18pt 已足够）。v3 改回 v0.9.1 实证值。

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
- **v3 特有**：使用 v3 旧版罗列但 v0.9.1 未实证的 layout（cube / quadrant_3group / lollipop / quadrant_2x2 等），视为设计漂移。
