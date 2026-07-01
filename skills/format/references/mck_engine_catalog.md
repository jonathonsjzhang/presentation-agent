# MckEngine 版式模板库（72 种）

> 基于 MckEngine 源码和 Layout Catalog 整理的完整可复用模板库。
> 按 13 个类别组织，给出每种的方法签名、schema layout_type 映射和使用场景。

## A: 结构导航（Structure & Navigation）

| 方法 | schema layout_type | 适用场景 |
|------|-------------------|---------|
| `cover(title, subtitle, author, date)` | `cover` | 封面页，仅第 1 页 |
| `toc(title, items)` | — 🚫 禁止 | 目录页，format.skill 禁止生成 |
| `section_divider(label, title)` | — 🚫 禁止 | 章节分隔页，format.skill 禁止生成 |
| `appendix_title(title, subtitle)` | `key_takeaway` | 附录标题页 |
| `closing(title, message)` | `closing` | 结束页 |

## B: 数据统计（Data & Stats）

| 方法 | schema layout_type | 适用场景 |
|------|-------------------|---------|
| `big_number(title, number, unit, description)` | `key_takeaway` | 单个关键数据展示 |
| `two_stat(title, stats, detail_items)` | `key_takeaway` | 双数据对比 |
| `three_stat(title, stats, detail_items)` | `key_takeaway` | 三指标仪表盘 |
| `data_table(title, headers, rows, col_widths)` | `data_table` | 结构化数据表格 |
| `metric_cards(title, cards)` | `key_takeaway` | 3-4 并行指标卡片 |
| `metric_comparison(title, metrics)` | `key_takeaway` | 指标前后对比 |

## C: 框架矩阵（Frameworks & Matrices）

| 方法 | schema layout_type | 适用场景 |
|------|-------------------|---------|
| `matrix_2x2(title, quadrants, axis_labels)` | `matrix_2x2` | 四象限矩阵/BCG矩阵 |
| `table_insight(title, headers, rows, insights)` | `data_table` | ⭐ 表格+洞见面板（开篇推荐） |
| `pyramid(title, levels)` | `process_chevron` | 金字塔结构 |
| `process_chevron(title, steps)` | `process_chevron` | 3-5 步流程箭头 |
| `staircase(title, steps)` | `process_chevron` | 阶梯进化图 |

## D: 对比评估（Comparison & Evaluation）

| 方法 | schema layout_type | 适用场景 |
|------|-------------------|---------|
| `side_by_side(title, options)` | `key_takeaway` | 左右选项对比 |
| `before_after(title, before, after)` | `key_takeaway` | 前后对比 |
| `pros_cons(title, pros, cons)` | `key_takeaway` | 优劣分析 |
| `rag_status(title, headers, rows)` | `data_table` | 红绿灯状态表 |
| `scorecard(title, items)` | `data_table` | 多维度评分卡 |
| `swot(title, quadrants)` | `matrix_2x2` | SWOT 分析 |
| `checklist(title, columns, rows)` | `data_table` | 检查清单 |

## E: 内容叙事（Content & Narrative）

| 方法 | schema layout_type | 适用场景 |
|------|-------------------|---------|
| `executive_summary(title, headline, items)` | `executive_summary` | ✅ 必在封面后第 1 页 |
| `key_takeaway(title, left_text, takeaways)` | `key_takeaway` | 核心洞见+详述 |
| `quote(quote_text, attribution)` | `key_takeaway` | 引言/用户原声页 |
| `two_column_text(title, columns)` | `key_takeaway` | 双栏文字（全局≤1 张） |
| `four_column(title, items)` | `key_takeaway` | 四栏概览 |
| `numbered_list_panel(title, items)` | `key_takeaway` | 编号列表+侧边栏 |

## F: 时间流程（Timeline & Process）

| 方法 | schema layout_type | 适用场景 |
|------|-------------------|---------|
| `timeline(title, milestones)` | `key_takeaway` | 时间轴/路线图 |
| `vertical_steps(title, steps)` | `process_chevron` | 垂直步骤 |
| `funnel(title, stages)` | `horizontal_bar` | 漏斗转化图 |
| `value_chain(title, stages)` | `process_chevron` | 价值链/水平流程 |

## G: 团队专题（Team & Cases）

| 方法 | schema layout_type | 适用场景 |
|------|-------------------|---------|
| `action_items(title, actions)` | `key_takeaway` | ✅ 行动计划（末页推荐） |
| `case_study(title, sections)` | `key_takeaway` | 案例研究 |

## H: 柱线图（Bar/Line Charts）

| 方法 | schema layout_type | 适用场景 |
|------|-------------------|---------|
| `grouped_bar(title, categories, series, data)` | `grouped_bar` | ⭐ 多品类分组柱状图 |
| `stacked_bar(title, categories, series, data)` | `grouped_bar` | 堆叠柱状图 |
| `horizontal_bar(title, items)` | `horizontal_bar` | ⭐ 排名/长标签水平条 |
| `line_chart(title, categories, series, data)` | `line_chart` | ⭐ 时序趋势折线 |
| `stacked_area(title, categories, series, data)` | `line_chart` | 堆叠面积图 |

## I: 圆形图表（Circular Charts）

| 方法 | schema layout_type | 适用场景 |
|------|-------------------|---------|
| `donut(title, segments)` | `donut` | 环形图（≤6 段）|
| `pie(title, segments)` | `pie` | 饼图（≤6 段）|
| `gauge(title, pct, label)` | `key_takeaway` | 仪表盘 |

## J: 高级图表（Advanced Charts）

| 方法 | schema layout_type | 适用场景 |
|------|-------------------|---------|
| `waterfall(title, items)` | `waterfall` | ⭐ 瀑布图/数值分解 |
| `pareto(title, items)` | `line_chart` | 帕累托分析 |
| `progress_bars(title, items)` | `horizontal_bar` | KPI 进度条 |
| `bubble(title, points)` | `key_takeaway` | 气泡散点图 |
| `risk_matrix(title, items)` | `matrix_2x2` | 风险矩阵 |
| `harvey_ball(title, headers, rows)` | `data_table` | Harvey Ball 状态表 |

## K: 仪表盘（Dashboards）

| 方法 | schema layout_type | 适用场景 |
|------|-------------------|---------|
| `dashboard_kpi(title, kpis, chart_data, takeaways)` | `dashboard_kpi_chart` | KPI+图表+洞见 |
| `dashboard_table(title, table_data, chart_data, factoids)` | `dashboard_table_chart` | 表格+图表+事实 |

## Content-to-Layout 快速匹配

| 内容类型 | 推荐方法 |
|---------|---------|
| 单个关键数据 | `big_number` |
| 2 个选项对比 | `side_by_side`, `before_after` |
| 3-4 个并列概念 | `table_insight`(⭐), `metric_cards`, `four_column` |
| 流程/步骤 | `process_chevron`, `vertical_steps`, `value_chain` |
| 时间线 | `timeline` |
| 数据表格 | `data_table`, `scorecard` |
| 案例研究 | `case_study` |
| 摘要/结论 | `executive_summary`, `key_takeaway` |
| 多 KPI | `three_stat`, `dashboard_kpi` |
| 时间序列数据 | `grouped_bar`, `line_chart`, `stacked_bar` |
| 占比/构成 | `donut`, `pie` |
| 风险/评估矩阵 | `risk_matrix`, `swot`, `matrix_2x2` |
| 开篇高影响力 | `table_insight`(#1), `big_number`(#2), `key_takeaway`(#3) |
