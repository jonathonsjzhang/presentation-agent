# Page Filling v2 修正方案

> 日期：2026-07-01
> 目标：把现有 v2 从“方向正确的设计稿”修成真正进入运行链路、可审查、可被 Format 消费的生产契约。

## 1. 修正原则

1. **先贯通再增强**：先消除 `SKILL.md=v2`、runtime/config=v1 的冲突，再增加质量约束。
2. **证据优先于文案**：任何数字、比较、因果和行动目标都必须带来源；输入不足时降级结论或回退上游。
3. **页面厚度按证据角色判断**：不以 bullet 数量衡量密度，而检查主证据、辅助对比/拆解、边界信息是否形成闭环。
4. **上游变厚必须下游可见**：Page Filling 声明必须上屏的证据，Format 必须逐项确认已呈现或解释省略原因。
5. **案例只使用已核验事实**：示例中的所有数值必须能在所附人工稿中定位；禁止用“示意数字”伪装真实案例。

## 2. 四个实施 Gate

### Gate A：运行契约贯通

- `page_filling.output_schema` 改为 `page_content.v2`。
- `format.input_schema` 改为 `page_content.v2`。
- 更新测试、Web fallback、文档和 renderer 注释中的版本声明。
- 编译测试必须断言生成 prompt 实际加载 v2 schema，而非只检查文件存在。

**验收**：离线 pipeline 生成的 page filling artifact 标记为 `page_content.v2`，schema gate 通过。

### Gate B：证据与 Reference 可达

- 为 skill package 增加显式 `reference_manifest.json`。
- Runtime 按 manifest 将必要 reference 确定性注入生成 instruction；不再依赖模型自行读取本地路径。
- Page Filling projected context 增加 evidence bank、完整论据、用户研究和数据表字段。
- 大字段仍需保留投影与来源路径，但主证据不能只剩前三条 preview。

**验收**：compiled package 中可见页型、充分性、论证链和 gotcha 指引；关键 evidence 字段进入 Worker context。

### Gate C：结构化质量与 Format 保真

- `page_type` 改为受控页型枚举；`claim_strength` 每页必填。
- 量化证据增加 `source_ref`，comparison matrix、qualitative evidence、visual layers 和上屏证据清单补齐内部必填项。
- 新增 `storyline_change_requests`：页面过载、缺方法论页或证据不足时，允许向 Manager 请求拆页/回退，而不是静默删证据。
- Rubric severity 统一为 P0/P1；软提示使用 P1，避免不存在的 `warning` 级别。
- Format 增加 v2 专用消费规则及 `evidence_trace`，记录已上屏与被省略证据。

**验收**：空 comparison matrix、缺 claim strength、缺关键 evidence ref 无法通过；Format review 能看到上游上屏契约。

### Gate D：回归与效果验证

- 增加 Page Filling v2 的结构化 eval cases：数据深挖、对比矩阵、证据不足降级。
- 增加 v2 编译、schema、machine check、context projection 与 Format handoff 测试。
- 后续用同一输入跑旧版/v2，按 E2E rubric 做盲评；至少覆盖留存分析、业务进展、竞品分析三类题材。

**验收**：

- 量化判断的来源覆盖率 100%；
- 对比页 matrix 非空且实体/维度/单元格可追溯；
- 无来源数字与目标值为 0；
- Page Filling 声明的 must-render evidence 在 Format 中均有呈现或省略理由；
- 同案例 E2E 信息密度和信息呈现分数较旧版有稳定提升。

## 3. 本轮实施范围

本轮完成 Gate A、B、C 的基础实现和 Gate D 的自动化回归骨架。真实模型旧版/v2 盲评需要单独运行完整 pipeline，作为下一轮效果验收，不以单次 schema 通过替代。
