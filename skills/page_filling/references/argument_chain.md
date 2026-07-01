# 页内论证链

论证链不是证据列表。它要说明每条证据与结论的关系，以及多条证据为什么能共同推出 takeaway。

```text
主证据 → 对比/拆解 → 机制或反例 → 边界 → inference → takeaway
```

## `evidence_steps[].relation`

| relation | 作用 |
|---|---|
| `direct_support` | 直接证明核心判断 |
| `comparison` | 给出同行、对照组、历史或时段基线 |
| `decomposition` | 按人群、功能、渠道、时间等拆解主结果 |
| `mechanism` | 解释行为路径或原因；用户原声通常在此 |
| `caveat` | 限定样本、口径、适用范围或替代解释 |

## 合格标准

- 每一步都有 `source_ref` 或可定位的 `evidence_ref_or_material`；
- `supports` 写清“这条证据证明哪一步”，不能复述数字；
- `logic_bridge` 解释证据如何共同推出结论，不能只写“综上”；
- 相关性不升级为因果，局部样本不升级为全局；
- 关键证据同步进入 `format_handoff_notes.must_render_evidence`。

## 退化信号

- 两条 evidence 是同义重复；
- baseline、delta 或 metric 只有文字描述，没有结构化 quant；
- 结论需要两页才能证明，却被压进一个大标题；
- caveat 只藏在 data gap，没有进入上屏契约。
