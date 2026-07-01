---
name: ppt
description: Adapt report structure for a presentation with page-level claims, one question and conclusion per page, controlled length, and appendix split.
---

# PPT Format

Use this atomic capability only when `output_format=ppt`. Storyline units are pages and each page advances one claim.

## PPT 版式核心规则

### 1. 页面结构
- ❌ **不生成**目录页、章节分隔页
- ✅ 封面后第一页必须是 **Execution Summary**（核心发现摘要）
- ✅ 每页必须包含**至少一个视觉元素**（图表/表格/形状/矩阵），**禁止纯文字页**
- ✅ 图表类型选择不受限，根据数据特征选择最合适的方式

### 2. 信息密度要求
- 每页三个信息层级：**行动标题** → **主视觉区域（~70%）** → **来源与注释**
- 正文页建议包含主视觉 + 2-4 条 insight bullet + 脚注

### 3. 数据真实性
- 所有图表数据必须从 `source_refs[]` 引用的原始文档中提取
- 禁止使用模拟数据、占位数据或示例数据填充图表
- 数据缺失时必须在 `gap_display.visible_note` 中声明

### 4. 文本溢出预防
- 标题 ≤ 40 字（中文）
- 表格单元格启用 word_wrap，内容 ≤ 50 字符/单元格
- insight 要点数 ≤ 5 条，每点 ≤ 80 字符

### 5. 布局约束
- 使用安全区约束（距离幻灯片边界至少 0.5 英寸）
- 形状之间保持至少 0.1 英寸间距

## Reference

- `references/presentation_style_guide.md` — 专业咨询风格指南
