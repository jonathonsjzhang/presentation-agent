# Page Filling v2 改造设计文档

> 状态：已按修正方案进入实现；最新实施边界与验收标准见 `docs/page_filling_v2_remediation_plan.md`
> 适用范围：`skills/page_filling/`，并作为后续改造 `format` 等下游 skill 的参考蓝本
> 关联诊断：人工版（23页 PDF）vs AI 版（10页 PPTX）"AI产品用户留存"对比
> 日期：2026-06-30

---

## 0. 一句话目标

> **让 page_filling 产出的不再是"用判断组织一些数据"，而是"用数据论证一个判断"——补齐证据密度、可溯源、多实体对比、用户原声四条腿，同时不退化已有的论证链与 caveat 保护能力。**

---

## 1. 背景与诊断修正

### 1.1 最初诊断

人工版相对 AI 版的核心差距（按严重度）：

1. **证据密度**：人工版每页有表格、精确数字（如"元宝纯白 27% vs 非纯白 12% / +14pp"）、竞品同行对比；AI 版多为概括性表述。
2. **多实体对比**：人工版元宝/DS/豆包始终保持同行对比矩阵；AI 版沦为并列描述。
3. **方法论透明度**：人工版有 2 页问卷设计与可信性检验；AI 版完全缺失。
4. **用户原声**：人工版每 2-3 页有一条用户引用；AI 版没有。
5. **结论分层**：人工版"核心发现 → 子发现 → 数据"层层递进；AI 版较扁平。

### 1.2 核查后的关键修正（重要）

动手前核查了现状代码，**修正了一个重大误判**：

> ❌ 误判："v1 SKILL.md 太薄、schema 太弱，所以内容空洞。"
> ✅ 事实：**v1 的 schema 其实相当完整**，缺的不是字段，是"怎么写好"的指引、以及几个专用结构。

现状 `page_content.v1.json` 已经具备：

| 已有能力 | 字段 |
|---|---|
| 论证链 | `proof_chain`（claim / evidence_steps / logic_bridge / so_what / confidence）|
| 可溯源 | `sources`（source / evidence_ref / timeframe / metric_definition / confidence）|
| 缺口标记 | `data_gaps`（gap / impact / needed_input / blocking_level）|
| 用户引用位 | `content_blocks[].quote_attribution`、`draft_material...quote_blocks` |
| Format 交接 | `format_handoff_notes`（primary_focus / must_keep_caveats / layout_risks）|
| 内容策略 | `page_brief.content_strategy` |

**因此 v2 的定位从"推翻重写"修正为"补强 + 接通"**：补 3 个薄弱结构、接通"指引层"（references）、把 rubrics 从"查字段存在"升级到"查论证质量"。

### 1.3 系统自身已确认的证据

`data/agents/page_filling/memory_summary.json` 里 loop 自己学到的一条（M-001）正好印证诊断：

> "page_filling 给 format 的 handoff 中需明确每页哪些证据必须进入主视觉…**不得让关键数据只停留在 JSON 深层字段**。"

这条会直接写进 v2 的 `format_handoff` 设计原则。

### 1.4 一个被搁置但需记录的前提风险

本轮按用户决策**先改 skill**，但保留一个未排除的底层风险：

> **输入侧丢数风险**：`capabilities.json` 里 `context_mode: "projected"`。若 projected context 把原始数据表当大字段"preview"掉，page_filling 根本拿不到 granular 数字，则无论 skill 改得多好都补不出数据厚度。

**触发回查条件**：若 v2 改造后产出仍缺具体数值，应立即 dump 那次案例 page_filling 实际收到的 projected context，确认 granular 数据/用户原声是否进入 Worker 输入。这是治本与治标的分界。

---

## 2. v1 vs v2：为什么"并行"而不是"替换"

### 2.1 两条路的本质

- **替换 v1**：原地改 `page_content.v1.json` → 干净，但 format 侧输入契约瞬间对不上，连锁改动大、易断链。
- **v2 并行**（本方案采纳）：新建 `page_content.v2.json`，v1 保留；page_filling 先产出 v2，format 分阶段迁移（先能读 v2 → 稳定后废弃 v1）。

### 2.2 核查发现：迁移压力比预想小

发现两份 `page_content.v1.json` 并不一致：

- `skills/page_filling/schemas/page_content.v1.json` = **权威详细版**（字段全展开）
- `skills/format/schemas/page_content.v1.json` = **宽松镜像版**（字段退化为 `{"type":"object"}`，只做浅校验）

**含义**：format 对输入只做浅结构校验，**v2 新增字段不会让 format 立刻 schema 报错**。这给了我们安全的渐进迁移窗口——page_filling 可以先产出 v2，format 在不改 schema 的情况下仍能跑通，再从容升级 format 去真正消费新字段。

### 2.3 并行期的契约关系

```
page_filling ──产出──> page_content.v2  ──消费──> format
                            │
              v1 仍保留（回退用），但 page_filling 默认产 v2
              format 镜像 schema 暂不收紧，按需逐字段消费 v2
```

---

## 3. v2 Schema 增量设计

**原则**：v2 = v1 的超集（向后兼容字段语义），只做"补强"和"显式化"，不删既有字段。下面只列**相对 v1 的增量**。

### 3.1 增量 A：量化证据的结构化（解决"证据密度"）

现状 `proof_chain.evidence_steps[]` 只有 `evidence_ref_or_material / supports / source_status`，模型可以填一句"留存率差异明显"就过。

v2 在 evidence step 上增加**可选的量化承载位**（不是硬性必填，配合 density 软期望使用）：

```jsonc
"evidence_steps": [
  {
    "evidence_ref_or_material": "...",        // 既有
    "supports": "...",                         // 既有
    "source_status": "...",                    // 既有
    "quant": {                                 // 新增（可选）
      "value": "26%",                          // 主数值
      "baseline": "非纯白用户 12%",            // 对比基线
      "delta": "+14pp",                        // 差值/相对变化
      "metric": "最近一周主用该产品的比例",      // 口径
      "unit_scope": "元宝 / 产品纯白用户",       // 实体·分群；未知样本量不编造
      "source_ref": "人工稿-P6-元宝纯白对比"      // 可定位来源
    }
  }
]
```

> 关键：`quant` **可选**。数据页"期望"填它（density 软期望），方法论页/行动页不强制 → 避免一把尺子量所有页。

### 3.2 增量 B：多实体对比矩阵（解决"对比沦为并列"）

现状只能用 `relation: comparison` 一个 tag 表达对比，无法逼出"实体 × 维度"矩阵。

v2 在 page 级别新增**可选**的 `comparison_matrix`：

```jsonc
"comparison_matrix": {                          // 新增（可选，对比型页面期望）
  "entities": ["元宝", "DeepSeek", "豆包"],
  "dimensions": ["纯白用户占比", "强留存率", "主要获客渠道"],
  "cells": [
    ["38%", "27%", "学校/单位"],
    ["—",   "—",   "—"],
    ["—",   "—",   "—"]
  ],
  "reader_takeaway": "元宝在纯白人群留存上领先，但获客依赖线下渠道",
  "source_refs": ["S-03", "S-07"]
}
```

> 配套 gotcha：「对比型页面不能写成三段并列描述，必须落到 entities × dimensions 矩阵」。

### 3.3 增量 C：定性证据 / 用户原声（解决"无用户引用"）

v1 只有 `content_blocks[].quote_attribution` 一个字段，散落且无强制语义。v2 在 page 级新增**可选**的 `qualitative_evidence`，让用户原声成为一类一等证据：

```jsonc
"qualitative_evidence": [                        // 新增（可选）
  {
    "quote": "我就是查个资料，平时也不会专门打开它",
    "attribution": "非纯白用户 / 访谈 U-12",
    "supports": "解释非纯白用户低频的机制",
    "role": "mechanism",                         // mechanism | illustration | counterpoint
    "source_ref": "S-访谈记录"
  }
]
```

> 约束（写进 invariant）：定性证据**只能用于机制说明或例证，不能单独支撑量化结论**。

### 3.4 增量 D：claim 强度显式化（保护"结论不强于证据"）

v1 的 `proof_chain.confidence` 偏模糊。v2 在 page 级新增 `claim_strength` 枚举，与 caveat 保护配套：

```jsonc
"claim_strength": "finding"   // fact | finding | implication | recommendation | hypothesis
```

> rubric 据此判断 `page_takeaway` 是否超出证据能支持的强度（详见 §6 PAGE-INFER）。

### 3.5 不改的部分（明确声明）

- `proof_chain` 整体结构、`sources`、`data_gaps`、`format_handoff_notes`、`draft_material`、`visual_plan` **保留**。
- `visual_plan` **不压缩进 handoff**（与外部方案不同）——它在 v1 是独立富结构，压缩会弱化 gotcha #6 想强化的"图表要说明证明什么"。保留 + 在 references 里强化指引。

---

## 4. 目标目录结构（progressive disclosure）

```text
skills/page_filling/
├── SKILL.md                          # 瘦身：核心角色/工作流/输出 + "何时读哪个 reference" 触发器
├── rubrics.json                      # 升级：查论证链/caveat/可溯源 + density 软提示
├── schemas/
│   ├── page_content.v1.json          # 保留（回退用）
│   ├── page_content.v2.json          # 新增：v1 超集 + §3 四个增量
│   └── storyline.v1.json             # 既有，不动
├── references/
│   ├── argument_chain.md             # 页内论证链：evidence → relation → inference → takeaway
│   ├── information_sufficiency.md     # 信息充分性：主证据/辅助证据/边界信息
│   ├── page_archetypes.md            # 【替代硬 gate】页型 → 内容范式（density 软期望落点）
│   └── gotchas.md                    # 高频反例（6 条起步，附维护原则）
└── examples/
    └── retention_manual_vs_ai.md     # 起始样例：人工稿 vs AI 稿差距（标注"易过拟合本案例"）
```

**核心约束**：
- SKILL.md 保持短（目标 < 现有 2 倍体积，控制在 prompt budget `generation_instruction_tokens: 4000` 内有余量）。
- 复杂经验放 references，**靠 SKILL.md 里的显式触发器**让模型按需读，而非堆在主文件。

---

## 5. SKILL.md 改造要点

保持现有四段式（Role / Workflow / Invariants / Output / Failure），**增量如下**：

### 5.1 Workflow 增加"按页型定内容范式"一步

在现有 5 步前插入认知步骤：

```
0. 读取该页 page_type / role_in_story，去 references/page_archetypes.md 对照该页型的内容范式与"看起来够厚"的期望。
```

### 5.2 新增"何时读哪个 reference"触发器（关键）

progressive disclosure 的成败在此。SKILL.md 末尾加一节：

```markdown
## 何时查阅 references（按需读，不要全量加载）

- 不确定一页该放哪些证据层次 → 读 references/information_sufficiency.md
- 要把零散证据串成论证 → 读 references/argument_chain.md
- 不确定这一页型该长什么样 / 该多厚 → 读 references/page_archetypes.md
- 写完后自检是否踩了高频坑 → 读 references/gotchas.md
- 想看人工稿 vs AI 稿的差距对照 → 读 examples/retention_manual_vs_ai.md
```

### 5.3 Invariants 增补 3 条

```
- 量化结论必须落到「数值 + 对比基线 + 口径」三要素（数据型页面期望，非数据页豁免）。
- 定性证据（用户原声）只服务机制说明或例证，不单独支撑量化结论。
- 关键数据/caveat 不得只停留在 JSON 深层字段，必须进入 format_handoff 的上屏意图（源自 loop memory M-001）。
```

### 5.4 Output 改为产出 v2

```
严格输出 page_content.v2（v1 超集）：在 v1 基础上，数据页补 quant，
对比页补 comparison_matrix，有访谈则补 qualitative_evidence，每页标 claim_strength。
```

---

## 6. Rubrics 升级（从"查存在"到"查质量"）

现状 4 条（PAGE-CORE-001~004）只验证"字段存在/可追溯/不重复"。v2 **保留这 4 条**，新增以下，且 **density 全部为软提示（warning）不拦截**：

| ID | 严重度 | 维度 | 标准 | 检查 | 修复 |
|---|---|---|---|---|---|
| PAGE-INFO-001 | **warning** | information_sufficiency | 数据型 deep-dive 页期望含主证据+辅助证据+边界信息；全是概括表述时提示 | 对照 page_archetypes 该页型期望 | 建议补具体数值/对比，但**不判不通过** |
| PAGE-LOGIC-001 | P1 | argument_chain | 每条证据需说明 supports 什么，证据间非纯并列 | 检查 relation 是否有意义 | 补 relation / inference |
| PAGE-INFER-001 | P1 | claim_calibration | page_takeaway 不强于 claim_strength 与证据能支持的强度 | 比对 takeaway 措辞 vs claim_strength | 降结论强度或补证据 |
| PAGE-CAVEAT-001 | P0 | caveat_protection | 影响结论强度的 caveat 必须页面可见，且不得被反向改写成行动建议 | 核对 data_gaps/caveat 是否被吞或反转 | 恢复 caveat |
| PAGE-COMPARE-001 | **warning** | comparison_quality | 对比型页期望用 entities×dimensions 矩阵，而非并列描述 | 检查 comparison_matrix 是否存在/退化 | 建议结构化为矩阵 |
| PAGE-HANDOFF-001 | P1 | format_handoff | 必须说明主视觉表达什么、哪些数字上屏、哪些 caveat 保留 | 检查 format_handoff_notes 完整度 | 补 handoff 意图 |

> 受 `review_rubric_tokens: 3000` 约束，rubrics 文案需精简；warning 级别确保"逼厚度但不误杀方法论页/行动页"。

---

## 7. references 内容规格

### 7.1 page_archetypes.md（替代硬 gate 的核心）

为每种页型定义"内容范式 + 软期望"。至少覆盖：

| 页型 | 必备要素 | density 软期望 |
|---|---|---|
| 方法论页 | 问卷/样本设计、口径定义、可信性检验 | 期望交代样本量/显著性，**不期望** quant 主数值 |
| 核心发现页 | 1 个主判断 + 分层子发现 | 期望主数值 + 至少 1 个对比基线 |
| Deep-dive 页 | 主证据 + 辅助拆解 + 机制 + 边界 | 期望 quant 三要素 + 可选用户原声 |
| 对比页 | 实体 × 维度矩阵 | 期望 comparison_matrix 非空 |
| 行动建议页 | 建议 + 证据强度 + caveat | **不期望**编造目标值，期望标 claim_strength |

### 7.2 gotchas.md（采纳用户 6 条 + 补 2 条）

直接采纳用户提供的 6 条（不写成摘要页 / caveat 不改行动 / 探索不改否定 / 不编目标值 / 标题不强于证据 / 图表要说明证明什么）。**补 2 条**对应新结构：

```
7. 对比页不要写成三段并列 → 必须落到 entities × dimensions 矩阵。
8. 用户原声不要当量化证据 → 只用于机制/例证，不单独支撑数字结论。
```

维护原则沿用用户版：只记真实高频问题、每条含错误表现+正确做法、不写泛泛原则。

### 7.3 examples/retention_manual_vs_ai.md

取本案例 1-2 页的人工稿 vs AI 稿对照（如"纯白用户留存"那页），标注差距点。**顶部注明**："起始样例，易过拟合本案例；后续 review 发现新高频问题再补，勿长成案例库。"

---

## 8. Format 侧迁移影响（连锁改动清单）

v2 不是孤立改动，下游 Format 已在 2026-07-01 的修正中同步接入：

| 影响项 | 现状 | v2 后动作 | 时机 |
|---|---|---|---|
| `skills/format/schemas/page_content.v2.json` | v2 镜像已加入 | 保留 v1 仅作历史兼容 | 已完成 |
| format SKILL.md 输入消费 | 读 v2 字段 | 消费 quant / matrix / qualitative evidence / must-render evidence | 已完成 |
| format rubrics | v2 evidence rubrics | 检查关键证据、矩阵、quote、caveat 是否上屏 | 已完成 |
| format invariant | 不改上游结论 | 不变（v2 兼容） | — |

**迁移节奏**：
1. 已完成：Page Filling 与 Format 契约切换到 v2，reference 注入、evidence trace 和回归测试接通。
2. 待完成：用真实模型跑旧版/v2 同输入盲评，验证信息密度和呈现分数是否提升。

---

## 9. 实施顺序（当前状态）

```
1. [完成] v2 schema、SKILL、rubrics、references 与经核验案例
2. [完成] Runtime/AgentSpec/Format 全链路切换 v2
3. [完成] granular evidence 与完整 pages 的投影上限修正
4. [完成] Format evidence trace 与上游证据契约 review
5. [完成] 自动化回归骨架
6. [待执行] 真实模型旧版/v2 留存案例对照
7. [条件触发] 若仍缺数，检查 raw brief 与 evidence bank 的实际输入完整度
```

---

## 10. 作为通用蓝本的可复用原则（供改其他 skill 参考）

本次改造提炼出的、可迁移到其他 skill 的原则：

1. **schema 升级走 vN 并行，不原地替换**——尤其当下游有消费方时。
2. **先核查现状再下结论**——本次最大教训：原以为 schema 太薄，实际是指引缺失。动手前必须读真实文件。
3. **指引层与契约层分离**：schema 管"能放什么"，references 管"怎么写好"，rubrics 管"写得够不够好"，SKILL.md 管"何时读哪层"。
4. **质量约束优先用"按类型的软期望"而非"全局硬 gate"**——避免生搬硬套误杀异质单元。
5. **反例（gotchas）比正面规则更高信号**——从真实失败案例提取，每条含错误表现+正确做法。
6. **progressive disclosure 必须配显式触发器**——否则只是把文件拆开放着，模型不会主动读。
7. **利用 loop memory 作为诊断证据**——agent 自己学到的 learning 往往已指向真问题。
```
