# MckEngine API 参数格式参考

> 基于 `mck_ppt/engine.py` 源码确认的正确参数格式。
> `references/framework/engine-api.md` 中的文档可能与实际代码不一致，以本表为准。

## 颜色参数处理

JSON 无法存储 `RGBColor` 对象，需在 `render.py` 中添加转换函数：

```python
from pptx.util import RGBColor

COLOR_MAP = {
    'NAVY': RGBColor(0, 51, 102),
    'WHITE': RGBColor(255, 255, 255),
    'BLACK': RGBColor(0, 0, 0),
    'BG_GRAY': RGBColor(245, 245, 245),
    'ACCENT_BLUE': RGBColor(30, 111, 224),
    'ACCENT_GREEN': RGBColor(46, 125, 50),
    'ACCENT_ORANGE': RGBColor(255, 152, 0),
    'ACCENT_RED': RGBColor(211, 47, 47),
}

def get_color(color_val):
    if not isinstance(color_val, str):
        return color_val
    if color_val in COLOR_MAP:
        return COLOR_MAP[color_val]
    return RGBColor(0, 51, 102)
```

## 常用布局方法参数格式

| 方法 | content.json 格式 | 常见错误 |
|------|------------------|---------|
| `cover` | `{title, subtitle, author, date}` | — |
| `executive_summary` | `items: [["1","标题","描述"], ...]` | ❌ 字典列表 |
| `metric_cards` | `cards: [["A","标题","描述"], ...]` | ❌ 字典列表 |
| `three_stat` | `stats: [{"label":"","value":"","detail":""}]` | — |
| `table_insight` | `headers: [...], rows: [[...], ...], insight_items: [["◆","文本"], ...]` | ❌ insight 格式 |
| `funnel` | `stages: [["阶段","数值",0.5], ...]` | ❌ 字典列表 |
| `grouped_bar` | `series: [["系列名","color_str"], ...]` | ❌ 字符串列表，不支持 `bottom_bar` |
| `horizontal_bar` | `items: [["项名", 百分比整数, "color_str"], ...]` | ❌ 字典列表 |
| `action_items` | `actions: [["标题","时间","描述","负责人"], ...]` | ❌ 字典列表 |
| `four_column` | `items: [["标题","数值","描述"], ...]` | ❌ 字典列表 |

## 常见错误排查

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `unexpected keyword argument 'bottom_bar'` | 方法不支持此参数 | 删除 `bottom_bar` |
| `too many values to unpack (expected 2)` | series 格式错误 | 改为 `(name, color_str)` 元组 |
| `assigned value must be type RGBColor` | 颜色是字符串 | 添加 hex_to_rgb 转换逻辑 |
| `not enough values to unpack` | 元组长度不对 | 检查元组元素个数 |

> 如遇参数错误，查看 `mck_ppt/engine.py` 中对应方法的 `def` 签名为准。
