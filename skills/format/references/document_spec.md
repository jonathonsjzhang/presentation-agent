# §D-1 format.document 专用规则（占位）

> **状态**：v3 当前阶段 document 载体**未实测过**，本文件仅做占位说明。**禁止**在 document 能力上声称通过 v0.9.1 验证。

## 1. 能力定位

完整报告（多章节，可独立阅读；跨页表格；罗马+阿拉伯页码）。

## 2. 与 format.ppt 的差异

| 维度        | PPT                     | Document             |
| --------- | ----------------------- | -------------------- |
| 字号单位      | pt                      | pt                   |
| 字号 title  | 18pt                    | 22pt                 |
| 字号 body   | 9.2pt                   | 11pt                 |
| 字号 footnote | 7.8pt                  | 8pt                  |
| 行距        | 1.0                     | 1.5                  |
| margin    | 0.55 inch               | 2.5cm                |
| 栏数       | 12 网格                   | 1                    |
| 表格       | 无斑马纹（仅数据）              | 全框                   |
| Logo      | 角落                      | 页眉 / 页脚（每页）          |

## 3. Layout 库（待实测）

v3 旧版罗列的 document layout 在 v3 阶段未实测。**禁止**声称这些 layout 通过验证：

- `doc.cover` / `doc.chapter_title` / `doc.body_text` / `doc.table` / `doc.footnote` / `doc.appendix`

## 4. 工作流（待实测）

1. 复用 format.ppt 的 5 类实证 layout（cover / executive_summary / analysis_dashboard / methodology_or_strategy / priority_matrix）
2. 在 document 中这些 layout 的字号/间距按 §2 调整
3. 跨页表格用 docx 原生表格，禁止切片

## 5. v3 强制要求

- v3 不强制实现 format.document 能力。如需运行，必须在 `evals/rubrics.json` 添加评估项并实测通过。
- v3 默认走 format.ppt 路径。
