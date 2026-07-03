# §P-5 数据真实性提取规则（Data Extraction）

> v3 的"数据真实性"规则继承自 v0.7（已纳入 v1.0），本文件作为单文件拆分，给 renderer 单独查阅。

## 1. 强制规则

### 1.1 数据来源（必填）
- 所有图表数据（柱数值、折线坐标、表格单元格、矩阵 cell）**必须**从 `source_refs[]` 引用的原始文档中提取
- 提取后应填写 `data_source_extraction` 字段，记录提取位置（如 `AI产品用户留存分析_文档资料.pdf §3.2 Table 2`）

### 1.2 禁止模拟数据
- ❌ **禁止**使用模拟数据 / 示例数据填充图表
- ❌ **禁止**为"看起来更丰富"而编造数据
- ❌ **禁止**在没有原始数据时用"≈"或"~"估算代替

### 1.3 数据缺失的处理
- 若原始文档中无对应数据：
  - 在 `gap_display.visible_note` 中声明"数据缺失"
  - 将 `quality_status` 设为 `partial`
  - 在 `open_design_tasks` 记录"需补充数据 / 需人工核对"
- 缺数据图表 → 改用安全版式（如 `priority_matrix` 的 fallback 文本框）+ 写 `open_design_tasks`
- **不得**伪造 `complete`

### 1.4 文档/图片型数据的提取
- 若原始文档为 PDF/图片，需使用 OCR（如 PyMuPDF 文本层 + 人工核对）
- 在 `open_design_tasks` 中记录"需人工核对数据"
- v0.9.1 实证工作流：PyMuPDF 提取文本层 → AI 识别图表 → 人工校对 → 写入 data dict

## 2. 发现面板的洞察生成

### 2.1 强制规则
- 发现面板（insight panel）的洞察要点**必须**：
  - 从原始文档的分析/结论部分提取，**或**
  - 由 AI 模型基于原始文档数据生成（推理链可追溯）
- ❌ **禁止**手动编写无依据的洞察
- ❌ **禁止**为了让面板"看起来丰富"凑 4 条（2-3 条亦可）

### 2.2 引用原始段落
- 每条洞察应当可追溯到具体页码 / 段落
- 在 `data_source_extraction` 中标注来源（如 `doc §4 "豆包的功能杠杆..."`）

## 3. 颜色映射的真实性

- ❌ **禁止**为"区分度更好"而擅自修改产品色映射
- ✅ **必须**沿用上游 `product_color_mapping`（一般由 `draft_material` 阶段锁定）
- 若产品色需要更新，应回到上游重做，不在 format 阶段改

## 4. 数值与单位的真实性

| 维度    | 规则                            |
| ----- | ----------------------------- |
| 数值    | 严格等于原始数据，不四舍五入（除非要显示整数 pp 标注）|
| 单位    | 严格保留（%、pp、人、份）              |
| 口径    | 严格保留（强留存率 vs 周留存率 vs 月留存率） |
| 时间范围  | 严格保留（2025.11.11-13 不简化为 11 月）|

## 5. 审计 trail（v0.9.1 实证）

每张 PPT 渲染后应输出 QA 文件，包含：
- 实际数据 dict（与 `data_source_extraction` 对照）
- 数据点数量（每个 chart 的 n）
- 是否有 placeholder 命中（应为 0）
- 是否通过 evals.json 的所有检查

```json
{
  "file": "AI 产品用户留存分析_skill_v3.pptx",
  "slide_count": 16,
  "data_audit": {
    "all_charts_have_data": true,
    "all_insights_have_source": true,
    "no_placeholder_hits": true
  },
  "passed": true,
  "issues": []
}
```

## 6. 与上游的协作

- format worker **不**重新做论点、故事线或逐字稿
- 数据若发现错误 → 写 `open_design_tasks` 回退到上游 page_content
- 不可在 format 阶段"顺手修正"数据
