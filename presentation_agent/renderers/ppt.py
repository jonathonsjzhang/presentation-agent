"""PPT render backend — formatted_material.v1 -> .pptx.

Preferred path: use the vendored mck_ppt shape-native engine so PPT output stays
editable and can render real McKinsey-style chart layouts.

The agent emits `material_units` where each unit carries a `layout_or_structure`
hint (preferably a real mck layout name like `executive_summary`, `donut`,
`matrix_2x2`, ...) plus finalized content and an optional `visual_object`.

Fallback path: render the same material as 16:9 HTML, screenshot each slide,
and embed those images into a PPTX. Unknown layouts degrade to a safe text layout
before that fallback is needed.

Browser / python-pptx dependencies are OPTIONAL: if one path is unavailable the
renderer tries the other, then returns a clear skipped/error result if both fail.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from presentation_agent.renderers.base import RenderResult

CAPABILITY_ID = "format.ppt"
REQUIRED_TOOLS = ("presentation_agent.vendor.mck_ppt.DeckBuilder",)

# ---- color mapping -----------------------------------------------------------

# Friendly color tokens the agent may emit -> mck constant name.
_COLOR_TOKENS = {
    "blue": "ACCENT_BLUE",
    "green": "ACCENT_GREEN",
    "orange": "ACCENT_ORANGE",
    "red": "ACCENT_RED",
    "navy": "NAVY",
    "light_blue": "LIGHT_BLUE",
    "light_green": "LIGHT_GREEN",
    "light_orange": "LIGHT_ORANGE",
    "light_red": "LIGHT_RED",
}


def _resolve_color(token: Any, constants: Any, default_name: str = "ACCENT_BLUE"):
    """Map a color token (str name / hex / None) to an RGBColor from mck constants."""
    from pptx.dml.color import RGBColor

    if token is None or token == "":
        return getattr(constants, default_name)
    if isinstance(token, str):
        t = token.strip().lower()
        if t in _COLOR_TOKENS:
            return getattr(constants, _COLOR_TOKENS[t])
        # hex like #006BA6 or 006BA6
        hexs = t.lstrip("#")
        if len(hexs) == 6:
            try:
                return RGBColor(int(hexs[0:2], 16), int(hexs[2:4], 16), int(hexs[4:6], 16))
            except ValueError:
                pass
        # maybe an mck constant name directly
        if hasattr(constants, token.upper()):
            return getattr(constants, token.upper())
    return getattr(constants, default_name)


def _accent_cycle(constants: Any):
    return [constants.ACCENT_BLUE, constants.ACCENT_GREEN, constants.ACCENT_ORANGE, constants.ACCENT_RED]


# ---- per-layout builders -----------------------------------------------------
#
# Each builder takes (unit, content, visual, constants) and returns the `data`
# dict for the corresponding mck engine method. Builders are intentionally
# defensive: they coerce shapes and fill safe defaults so method(**data) never
# blows up on arity mismatch.


def _supporting_points(content: dict[str, Any]) -> list[str]:
    pts = content.get("supporting_points") or []
    if isinstance(pts, str):
        pts = [pts]
    out = []
    for p in pts:
        if isinstance(p, (list, tuple)):
            out.append(" ".join(str(x) for x in p))
        else:
            out.append(str(p))
    return [p for p in out if p.strip()]


def _build_cover(unit, content, visual, c) -> dict:
    return {
        "title": unit.get("headline") or content.get("primary_text") or "汇报标题",
        "subtitle": content.get("body") or (_supporting_points(content)[:1] or [""])[0],
        "date": content.get("date", ""),
        "author": content.get("author", ""),
    }


def _build_section_divider(unit, content, visual, c) -> dict:
    return {
        "section_label": str(content.get("section_label", "")),
        "title": unit.get("headline") or "章节",
        "subtitle": content.get("body", ""),
    }


def _build_executive_summary(unit, content, visual, c) -> dict:
    pts = _supporting_points(content)
    items = []
    for i, p in enumerate(pts[:4], 1):
        # split "标题：说明" if present
        if "：" in p:
            t, d = p.split("：", 1)
        elif ":" in p:
            t, d = p.split(":", 1)
        else:
            t, d = p[:8], p
        items.append((str(i), t.strip()[:14], d.strip()))
    if not items:
        items = [("1", "结论", unit.get("headline", ""))]
    return {
        "title": unit.get("headline") or "执行摘要",
        "headline": content.get("primary_text") or content.get("body") or "",
        "items": items,
        "source": _source(unit, content),
    }


def _build_key_takeaway(unit, content, visual, c) -> dict:
    left = content.get("body") or content.get("primary_text") or ""
    left_list = [s for s in str(left).split("\n") if s.strip()] or _supporting_points(content)
    takeaways = _supporting_points(content)[:4] or [unit.get("headline", "")]
    return {
        "title": unit.get("headline") or "核心结论",
        "left_text": left_list[:6] or ["—"],
        "takeaways": takeaways,
        "source": _source(unit, content),
    }


def _build_four_column(unit, content, visual, c) -> dict:
    pts = _supporting_points(content)
    items = []
    for i, p in enumerate(pts[:4], 1):
        if "：" in p:
            t, d = p.split("：", 1)
        elif ":" in p:
            t, d = p.split(":", 1)
        else:
            t, d = p[:10], p
        items.append((str(i), t.strip()[:12], d.strip()))
    while len(items) < 2:
        items.append((str(len(items) + 1), "要点", ""))
    return {"title": unit.get("headline") or "", "items": items[:4], "source": _source(unit, content)}


def _build_donut(unit, content, visual, c) -> dict:
    segs = _coerce_segments(visual, c, with_sub=False)
    return {
        "title": unit.get("headline") or "",
        "segments": segs,
        "center_label": (visual.get("center_label") if visual else "") or "100%",
        "center_sub": (visual.get("center_sub") if visual else "") or "",
        "summary": (visual.get("reader_takeaway") if visual else "") or None,
        "source": _source(unit, content),
    }


def _build_pie(unit, content, visual, c) -> dict:
    segs = _coerce_segments(visual, c, with_sub=True)
    return {
        "title": unit.get("headline") or "",
        "segments": segs,
        "summary": (visual.get("reader_takeaway") if visual else "") or None,
        "source": _source(unit, content),
    }


def _build_matrix_2x2(unit, content, visual, c) -> dict:
    lights = [c.LIGHT_GREEN, c.LIGHT_BLUE, c.LIGHT_RED, c.LIGHT_ORANGE]
    quads = []
    src = (visual.get("data_fields") if visual else None) or _supporting_points(content)
    for i in range(4):
        if i < len(src):
            item = src[i]
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                label, desc = str(item[0]), str(item[1])
            else:
                s = str(item)
                label, desc = (s.split("：", 1) + [""])[:2] if "：" in s else (s[:8], s)
        else:
            label, desc = f"象限{i+1}", ""
        quads.append((label[:10], lights[i], desc))
    return {
        "title": unit.get("headline") or "",
        "quadrants": quads,
        "source": _source(unit, content),
    }


def _build_process_chevron(unit, content, visual, c) -> dict:
    pts = _supporting_points(content)[:5]
    steps = []
    for i, p in enumerate(pts, 1):
        if "：" in p:
            t, d = p.split("：", 1)
        else:
            t, d = p[:6], p
        steps.append((str(i), t.strip().replace("\n", "")[:6], d.strip()[:40]))
    if not steps:
        steps = [("1", "步骤", "")]
    return {"title": unit.get("headline") or "", "steps": steps, "source": _source(unit, content)}


def _build_timeline(unit, content, visual, c) -> dict:
    pts = _supporting_points(content)
    ms = []
    for p in pts[:6]:
        if "：" in p:
            label, desc = p.split("：", 1)
        elif " " in p:
            label, desc = p.split(" ", 1)
        else:
            label, desc = p[:6], p
        ms.append((label.strip()[:6], desc.strip()))
    if not ms:
        ms = [("阶段", unit.get("headline", ""))]
    return {"title": unit.get("headline") or "", "milestones": ms, "source": _source(unit, content)}


def _build_data_table(unit, content, visual, c) -> dict:
    tables = content.get("tables") or []
    headers, rows = ["项目", "说明"], []
    if tables and isinstance(tables[0], dict):
        headers = tables[0].get("headers") or headers
        rows = tables[0].get("rows") or []
    elif tables and isinstance(tables[0], (list, tuple)):
        rows = [list(map(str, r)) for r in tables]
    if not rows:
        rows = [[p[:20], ""] for p in _supporting_points(content)[:5]] or [["—", "—"]]
    rows = [[str(cell) for cell in r] for r in rows]
    return {"title": unit.get("headline") or "", "headers": [str(h) for h in headers], "rows": rows, "source": _source(unit, content)}


def _build_table_insight(unit, content, visual, c) -> dict:
    base = _build_data_table(unit, content, visual, c)
    base["insights"] = _supporting_points(content)[:3] or [unit.get("headline", "")]
    return base


def _build_scorecard(unit, content, visual, c) -> dict:
    spec = _chart_spec(visual)
    raw_items = spec.get("items") or visual.get("data_fields") or content.get("callouts") or []
    items = []
    for item in raw_items[:6]:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("label") or "指标")
            score = str(item.get("score") or item.get("value_label") or item.get("value") or "")
            pct = _to_float(item.get("pct", item.get("progress", item.get("value", 0))), 0.0)
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            name, score, pct = str(item[0]), str(item[1]), _to_float(item[2], 0.0)
        else:
            continue
        if pct > 1:
            pct = pct / 100.0
        items.append((name[:18], score, max(0.0, min(pct, 1.0))))
    if not items:
        items = [("指标待补", "—", 0.0)]
    return {"title": unit.get("headline") or "", "items": items, "source": _source(unit, content)}


def _build_grouped_bar(unit, content, visual, c) -> dict:
    spec = _chart_spec(visual)
    categories = [str(x) for x in spec.get("categories", [])][:6]
    series = _series(spec.get("series", []), c, limit=3)
    data = _matrix(spec.get("values", spec.get("data", [])), len(categories), len(series))
    if not categories or not series or not data:
        categories, series, data = _bar_fallback_from_visual(visual, c)
    return {
        "title": unit.get("headline") or "",
        "categories": categories,
        "series": series,
        "data": data,
        "max_val": spec.get("max_val"),
        "y_ticks": spec.get("y_ticks"),
        "summary": _summary_tuple(spec, visual, content),
        "source": _source(unit, content),
    }


def _build_stacked_bar(unit, content, visual, c) -> dict:
    spec = _chart_spec(visual)
    periods = [str(x) for x in spec.get("periods", spec.get("categories", []))][:6]
    series = _series(spec.get("series", []), c, limit=5)
    data = _matrix(spec.get("values", spec.get("data", [])), len(periods), len(series))
    if not periods or not series or not data:
        periods, series, data = _bar_fallback_from_visual(visual, c)
    return {
        "title": unit.get("headline") or "",
        "periods": periods,
        "series": series,
        "data": data,
        "summary": _summary_tuple(spec, visual, content),
        "source": _source(unit, content),
    }


def _build_horizontal_bar(unit, content, visual, c) -> dict:
    spec = _chart_spec(visual)
    accents = _accent_cycle(c)
    raw = spec.get("items") or visual.get("data_fields") or []
    items = []
    for i, item in enumerate(raw[:8]):
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("label") or f"项{i+1}")
            val = _to_float(item.get("value", item.get("pct", 0)), 0.0)
            color = _resolve_color(item.get("color"), c, _COLOR_TOKENS_BY_INDEX(i))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            name = str(item[0])
            val = _to_float(item[1], 0.0)
            color = _resolve_color(item[2], c, _COLOR_TOKENS_BY_INDEX(i)) if len(item) > 2 else accents[i % len(accents)]
        else:
            continue
        if val <= 1:
            val *= 100
        items.append((name[:18], round(max(0, min(val, 100))), color))
    if not items:
        items = [("数据待补", 0, c.ACCENT_BLUE)]
    return {
        "title": unit.get("headline") or "",
        "items": items,
        "summary": _summary_tuple(spec, visual, content),
        "source": _source(unit, content),
    }


def _build_waterfall(unit, content, visual, c) -> dict:
    spec = _chart_spec(visual)
    raw = spec.get("items") or visual.get("data_fields") or []
    items = []
    for item in raw[:8]:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("name") or "项")
            value = _to_float(item.get("value"), 0.0)
            typ = str(item.get("type") or item.get("kind") or ("base" if not items else "up" if value >= 0 else "down"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            label = str(item[0])
            value = _to_float(item[1], 0.0)
            typ = str(item[2]) if len(item) > 2 else ("base" if not items else "up" if value >= 0 else "down")
        else:
            continue
        items.append((label[:8], value, typ if typ in {"base", "up", "down"} else "up"))
    if not items:
        items = [("基准", 1, "base")]
    legend_items = []
    for i, item in enumerate(spec.get("legend_items") or []):
        if isinstance(item, dict):
            legend_items.append((str(item.get("label", "")), _resolve_color(item.get("color"), c, _COLOR_TOKENS_BY_INDEX(i))))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            legend_items.append((str(item[0]), _resolve_color(item[1], c, _COLOR_TOKENS_BY_INDEX(i))))
    return {
        "title": unit.get("headline") or "",
        "items": items,
        "max_val": spec.get("max_val"),
        "legend_items": legend_items or None,
        "summary": _summary_text(spec, visual, content),
        "source": _source(unit, content),
    }


def _build_line_chart(unit, content, visual, c) -> dict:
    spec = _chart_spec(visual)
    x_labels = [str(x) for x in spec.get("x_labels", spec.get("labels", []))][:8]
    values = [_to_float(v, 0.0) for v in spec.get("values", [])[:len(x_labels) or None]]
    if not x_labels or not values:
        raw = visual.get("data_fields") or []
        x_labels = [str((r.get("label") if isinstance(r, dict) else r[0]) if r else "") for r in raw[:8]]
        values = [_to_float((r.get("value") if isinstance(r, dict) else r[1] if len(r) > 1 else 0), 0.0) for r in raw[:8]]
    if not x_labels or not values:
        x_labels, values = ["T1", "T2"], [0.0, 1.0]
    max_val = max(values) or 1.0
    normalized = [v if 0 <= v <= 1 and max_val <= 1 else v / max_val for v in values]
    y_labels = [str(x) for x in spec.get("y_labels", [])] or ["0", f"{max_val/2:g}", f"{max_val:g}"]
    return {
        "title": unit.get("headline") or "",
        "x_labels": x_labels,
        "y_labels": y_labels,
        "values": normalized,
        "legend_label": spec.get("legend_label", ""),
        "summary": _summary_text(spec, visual, content),
        "source": _source(unit, content),
    }


def _build_pareto(unit, content, visual, c) -> dict:
    spec = _chart_spec(visual)
    raw = spec.get("items") or visual.get("data_fields") or []
    items = []
    for item in raw[:8]:
        if isinstance(item, dict):
            items.append((str(item.get("name") or item.get("label") or "项")[:8], _to_float(item.get("value", 0), 0.0)))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            items.append((str(item[0])[:8], _to_float(item[1], 0.0)))
    if not items:
        items = [("数据待补", 1)]
    items = sorted(items, key=lambda x: x[1], reverse=True)
    return {
        "title": unit.get("headline") or "",
        "items": items,
        "max_val": spec.get("max_val"),
        "summary": _summary_text(spec, visual, content),
        "source": _source(unit, content),
    }


def _build_multi_bar_panel(unit, content, visual, c) -> dict:
    spec = _chart_spec(visual)
    panels = []
    for pi, panel in enumerate((spec.get("panels") or [])[:3]):
        if not isinstance(panel, dict):
            continue
        values = [_to_float(v, 0.0) for v in panel.get("values", [])[:6]]
        categories = [str(x) for x in panel.get("categories", panel.get("labels", []))[:len(values)]]
        if not values or not categories:
            continue
        panels.append({
            "title": str(panel.get("title") or f"Panel {pi+1}"),
            "unit": str(panel.get("unit") or spec.get("unit") or ""),
            "legend": str(panel.get("legend") or ""),
            "categories": categories,
            "values": values,
            "bar_color": _resolve_color(panel.get("bar_color"), c, "NAVY"),
            "cagr": panel.get("cagr") or [],
            "highlight_idx": panel.get("highlight_idx") or [],
            "highlight_color": _resolve_color(panel.get("highlight_color"), c, "ACCENT_BLUE"),
            "value_format": panel.get("value_format", "{:,.0f}"),
        })
    if not panels:
        panels = [{
            "title": "数据待补",
            "unit": "",
            "legend": "",
            "categories": ["T1", "T2"],
            "values": [0, 1],
            "bar_color": c.NAVY,
        }]
    return {
        "title": unit.get("headline") or "",
        "panels": panels,
        "connectors": spec.get("connectors"),
        "footnotes": spec.get("footnotes"),
        "source": _source(unit, content),
    }


def _build_dashboard_kpi_chart(unit, content, visual, c) -> dict:
    spec = _chart_spec(visual)
    cards = []
    for i, card in enumerate((spec.get("kpi_cards") or content.get("callouts") or [])[:4]):
        if isinstance(card, dict):
            cards.append((
                str(card.get("value") or card.get("metric") or "—"),
                str(card.get("label") or card.get("name") or "指标"),
                str(card.get("detail") or card.get("delta") or ""),
                _resolve_color(card.get("color"), c, _COLOR_TOKENS_BY_INDEX(i)),
            ))
        elif isinstance(card, (list, tuple)) and len(card) >= 3:
            cards.append((str(card[0]), str(card[1]), str(card[2]), _resolve_color(card[3], c, _COLOR_TOKENS_BY_INDEX(i)) if len(card) > 3 else _accent_cycle(c)[i % 4]))
    if not cards:
        cards = [("—", "指标待补", "", c.ACCENT_BLUE)]
    return {
        "title": unit.get("headline") or "",
        "kpi_cards": cards,
        "chart_data": spec.get("chart_data"),
        "summary": spec.get("summary") or visual.get("reader_takeaway"),
        "source": _source(unit, content),
    }


def _build_dashboard_table_chart(unit, content, visual, c) -> dict:
    spec = _chart_spec(visual)
    table_data = spec.get("table_data") or {}
    if not table_data:
        tables = content.get("tables") or []
        if tables and isinstance(tables[0], dict):
            headers = tables[0].get("headers") or []
            table_data = {
                "headers": headers,
                "col_widths": spec.get("col_widths") or _default_col_widths(len(headers)),
                "rows": tables[0].get("rows") or [],
            }
    return {
        "title": unit.get("headline") or "",
        "table_data": table_data or {"headers": ["项目", "数值"], "col_widths": _default_col_widths(2), "rows": [["数据待补", "—"]]},
        "chart_data": spec.get("chart_data"),
        "factoids": _factoids(spec.get("factoids"), c),
        "source": _source(unit, content),
    }


def _build_value_chain(unit, content, visual, c) -> dict:
    spec = _chart_spec(visual)
    raw = spec.get("stages") or _supporting_points(content)
    stages = []
    for i, item in enumerate(raw[:6]):
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("stage") or f"环节{i+1}")
            desc = str(item.get("desc") or item.get("description") or "")
            color = _resolve_color(item.get("color"), c, _COLOR_TOKENS_BY_INDEX(i))
        else:
            s = str(item)
            title, desc = (s.split("：", 1) + [""])[:2] if "：" in s else (s[:8], s)
            color = _accent_cycle(c)[i % 4]
        stages.append((title[:10], desc[:80], color))
    if not stages:
        stages = [("环节", "数据待补", c.ACCENT_BLUE)]
    return {
        "title": unit.get("headline") or "",
        "stages": stages,
        "source": _source(unit, content),
        "bottom_bar": _summary_tuple(spec, visual, content),
    }


def _build_closing(unit, content, visual, c) -> dict:
    return {
        "title": unit.get("headline") or "谢谢",
        "message": content.get("body") or content.get("primary_text") or "",
    }


def _build_text_fallback(unit, content, visual, c) -> dict:
    """Safe degrade: render anything unknown as a key_takeaway page."""
    return _build_key_takeaway(unit, content, visual, c)


# ---- shared helpers ----------------------------------------------------------


def _source(unit, content) -> str:
    sd = unit.get("source_display") or {}
    if isinstance(sd, dict) and sd.get("footer"):
        return str(sd["footer"])
    return content.get("source", "") if isinstance(content, dict) else ""


def _chart_spec(visual: Optional[dict]) -> dict[str, Any]:
    if not isinstance(visual, dict):
        return {}
    spec = visual.get("chart_spec")
    if isinstance(spec, dict):
        return spec
    mck = visual.get("mck_api")
    if isinstance(mck, dict) and isinstance(mck.get("args"), dict):
        return mck["args"]
    return {}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, str):
            value = value.strip().replace("%", "")
        return float(value)
    except Exception:
        return default


def _series(raw: Any, c: Any, limit: int) -> list[tuple[str, Any]]:
    accents = _accent_cycle(c)
    out = []
    for i, item in enumerate((raw or [])[:limit]):
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("label") or f"系列{i+1}")
            color = _resolve_color(item.get("color"), c, _COLOR_TOKENS_BY_INDEX(i))
        elif isinstance(item, (list, tuple)):
            name = str(item[0]) if item else f"系列{i+1}"
            color = _resolve_color(item[1], c, _COLOR_TOKENS_BY_INDEX(i)) if len(item) > 1 else accents[i % len(accents)]
        else:
            name = str(item)
            color = accents[i % len(accents)]
        out.append((name[:10], color))
    return out


def _matrix(raw: Any, rows: int, cols: int) -> list[list[float]]:
    if not raw or rows <= 0 or cols <= 0:
        return []
    out = []
    for r in list(raw)[:rows]:
        if not isinstance(r, (list, tuple)):
            return []
        vals = [_to_float(v, 0.0) for v in list(r)[:cols]]
        while len(vals) < cols:
            vals.append(0.0)
        out.append(vals)
    while len(out) < rows:
        out.append([0.0] * cols)
    return out


def _bar_fallback_from_visual(visual: dict, c: Any) -> tuple[list[str], list[tuple[str, Any]], list[list[float]]]:
    raw = visual.get("data_fields") or []
    categories = []
    values = []
    for i, item in enumerate(raw[:6]):
        if isinstance(item, dict):
            categories.append(str(item.get("label") or f"项{i+1}"))
            values.append(_to_float(item.get("value", item.get("pct", 0)), 0.0))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            categories.append(str(item[1]))
            values.append(_to_float(item[0], 0.0))
    if not categories:
        categories, values = ["数据待补"], [0.0]
    return categories, [("数值", c.ACCENT_BLUE)], [[v] for v in values]


def _summary_text(spec: dict, visual: dict, content: dict) -> str:
    summary = spec.get("summary") or spec.get("reader_takeaway") or visual.get("reader_takeaway") or content.get("primary_text") or ""
    if isinstance(summary, (list, tuple)):
        return "；".join(str(x) for x in summary if str(x).strip())
    return str(summary)


def _summary_tuple(spec: dict, visual: dict, content: dict) -> Optional[tuple[str, str]]:
    summary = spec.get("summary")
    if isinstance(summary, dict):
        return (str(summary.get("label") or "关键发现"), str(summary.get("text") or summary.get("value") or ""))
    if isinstance(summary, (list, tuple)) and len(summary) >= 2:
        return (str(summary[0]), str(summary[1]))
    text = _summary_text(spec, visual, content)
    return ("关键发现", text) if text else None


def _default_col_widths(n: int):
    from pptx.util import Inches

    if n <= 0:
        return []
    total = 6.2
    return [Inches(total / n) for _ in range(n)]


def _factoids(raw: Any, c: Any):
    out = []
    for i, item in enumerate((raw or [])[:4]):
        if isinstance(item, dict):
            out.append((
                str(item.get("value") or "—"),
                str(item.get("label") or item.get("name") or ""),
                _resolve_color(item.get("color"), c, _COLOR_TOKENS_BY_INDEX(i)),
            ))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append((str(item[0]), str(item[1]), _resolve_color(item[2], c, _COLOR_TOKENS_BY_INDEX(i)) if len(item) > 2 else _accent_cycle(c)[i % 4]))
    return out or None


def _coerce_segments(visual: Optional[dict], c: Any, with_sub: bool):
    """Build donut/pie segments from visual.data_fields. Enforce <=6 segments."""
    accents = _accent_cycle(c)
    raw = (visual.get("data_fields") if visual else None) or []
    segs = []
    for i, item in enumerate(raw):
        color = accents[i % len(accents)]
        if isinstance(item, dict):
            pct = float(item.get("pct", item.get("value", 0)) or 0)
            label = str(item.get("label", f"项{i+1}"))
            sub = str(item.get("sub_label", item.get("sub", "")))
            color = _resolve_color(item.get("color"), c, _COLOR_TOKENS_BY_INDEX(i))
        elif isinstance(item, (list, tuple)):
            pct = float(item[0]) if item else 0.0
            label = str(item[1]) if len(item) > 1 else f"项{i+1}"
            sub = str(item[2]) if len(item) > 2 else ""
        else:
            continue
        if pct > 1:  # accept 0-100 ints
            pct = pct / 100.0
        if with_sub:
            segs.append((pct, color, label, sub or f"{pct*100:.0f}%"))
        else:
            segs.append((pct, color, label))
    if not segs:  # safe placeholder
        segs = [(1.0, accents[0], "数据待补")] if not with_sub else [(1.0, accents[0], "数据待补", "")]
    if len(segs) > 6:  # merge tail
        head = segs[:5]
        rest = 1.0 - sum(s[0] for s in head)
        if with_sub:
            head.append((max(rest, 0.0), c.MED_GRAY, "其他", ""))
        else:
            head.append((max(rest, 0.0), c.MED_GRAY, "其他"))
        segs = head
    return segs


def _COLOR_TOKENS_BY_INDEX(i: int) -> str:
    names = ["ACCENT_BLUE", "ACCENT_GREEN", "ACCENT_ORANGE", "ACCENT_RED"]
    return names[i % len(names)]


# layout name -> builder
_LAYOUT_BUILDERS = {
    "cover": _build_cover,
    "section_divider": _build_section_divider,
    "executive_summary": _build_executive_summary,
    "key_takeaway": _build_key_takeaway,
    "four_column": _build_four_column,
    "scorecard": _build_scorecard,
    "donut": _build_donut,
    "pie": _build_pie,
    "grouped_bar": _build_grouped_bar,
    "stacked_bar": _build_stacked_bar,
    "horizontal_bar": _build_horizontal_bar,
    "waterfall": _build_waterfall,
    "line_chart": _build_line_chart,
    "pareto": _build_pareto,
    "multi_bar_panel": _build_multi_bar_panel,
    "dashboard_kpi_chart": _build_dashboard_kpi_chart,
    "dashboard_table_chart": _build_dashboard_table_chart,
    "matrix_2x2": _build_matrix_2x2,
    "process_chevron": _build_process_chevron,
    "timeline": _build_timeline,
    "data_table": _build_data_table,
    "table_insight": _build_table_insight,
    "value_chain": _build_value_chain,
    "closing": _build_closing,
}

# layouts that need a dedicated mck method name == key
_VALID_LAYOUTS = set(_LAYOUT_BUILDERS) | {"text"}


def _pick_layout(unit: dict[str, Any], index: int, total: int) -> tuple[str, bool]:
    """Choose an mck layout for this unit, honoring explicit hints.

    Returns (layout_name, degraded) — degraded=True means the visual_type was
    specified but no direct builder existed, so a heuristic or fallback layout
    was picked instead.
    """
    los = unit.get("layout_or_structure") or {}
    hint = (los.get("layout_type") or unit.get("layout_type") or "").strip().lower()
    if hint in _LAYOUT_BUILDERS:
        return hint, False

    # Check whether the agent explicitly asked for a visual that we don't
    # have a direct builder for — this is the degradation signal.
    visual = unit.get("visual_object") or {}
    vt = (visual.get("visual_type") or "").lower()
    has_visual_hint = bool(hint or vt)

    # heuristics by position / visual
    if index == 0:
        return "cover", has_visual_hint
    if index == total - 1:
        return "closing", has_visual_hint
    if vt in _LAYOUT_BUILDERS:
        return vt, False
    if "group" in vt or "分组" in vt:
        return "grouped_bar", has_visual_hint
    if "stack" in vt or "堆叠" in vt:
        return "stacked_bar", has_visual_hint
    if "horizontal" in vt or "横向" in vt or "条形" in vt:
        return "horizontal_bar", has_visual_hint
    if "waterfall" in vt or "瀑布" in vt or "桥" in vt:
        return "waterfall", has_visual_hint
    if "line" in vt or "折线" in vt or "趋势" in vt:
        return "line_chart", has_visual_hint
    if "pareto" in vt or "帕累托" in vt or "排名" in vt:
        return "pareto", has_visual_hint
    if "multi" in vt or "panel" in vt or "多面板" in vt:
        return "multi_bar_panel", has_visual_hint
    if "dashboard" in vt and "table" in vt:
        return "dashboard_table_chart", has_visual_hint
    if "dashboard" in vt or "kpi" in vt:
        return "dashboard_kpi_chart", has_visual_hint
    if "donut" in vt or "饼" in vt or "占比" in vt:
        return "donut", has_visual_hint and vt not in ("donut", "pie")  # not an exact match
    if "时间" in vt or "timeline" in vt or "里程碑" in vt:
        return "timeline", has_visual_hint
    if "矩阵" in vt or "matrix" in vt or "象限" in vt:
        return "matrix_2x2", has_visual_hint
    if "流程" in vt or "process" in vt or "步骤" in vt:
        return "process_chevron", has_visual_hint
    if "表" in vt or "table" in vt:
        return "table_insight", has_visual_hint
    return "executive_summary", has_visual_hint


# In draft (wireframe) fidelity we only keep structural layouts; every
# content/chart page degrades to a plain text takeaway so agent4 ships a fast,
# obviously-low-fidelity skeleton that agent5 later refines into the final deck.
_DRAFT_STRUCTURAL = {"cover", "section_divider", "closing"}


def _node_executable() -> str | None:
    bundled = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
    )
    if bundled.exists():
        return str(bundled)
    return shutil.which("node")


def _render_html_first_ppt(
    material: dict[str, Any],
    out_dir: Path,
    fidelity: str,
    file_stem: str,
) -> RenderResult:
    """Render PPT by first laying pages out as HTML, then rasterizing to slides.

    The resulting deck is less editable than a shape-native PPT, but it preserves
    the stronger HTML visual system and avoids re-implementing layout decisions
    in two separate renderers.
    """
    from presentation_agent.renderers.html import build_html_document

    units = material.get("material_units") or []
    if not units:
        return RenderResult(status="no_units", fmt="ppt", fidelity=fidelity)

    node = _node_executable()
    if not node:
        return RenderResult(
            status="skipped_missing_dep",
            fmt="ppt",
            fidelity=fidelity,
            unit_count=len(units),
            detail="需要 Node.js + Playwright + pptxgenjs 执行 HTML-first PPT 转换",
        )

    suffix = "draft" if fidelity == "draft" else "final"
    html_path = out_dir / f"{file_stem}_{suffix}.ppt-source.html"
    pptx_path = out_dir / f"{file_stem}_{suffix}.pptx"
    html_path.write_text(build_html_document(material, fidelity=fidelity, export_mode="ppt"), encoding="utf-8")

    script = Path(__file__).with_name("html_to_ppt.js")
    project_root = Path(__file__).resolve().parents[2]
    try:
        proc = subprocess.run(
            [node, str(script), str(html_path), str(pptx_path)],
            cwd=str(project_root),
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except Exception as exc:
        return RenderResult(
            status="error",
            fmt="ppt",
            fidelity=fidelity,
            unit_count=len(units),
            detail=f"HTML-first PPT 转换未执行：{exc}",
        )

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return RenderResult(
            status="error",
            fmt="ppt",
            fidelity=fidelity,
            unit_count=len(units),
            detail=detail[:2000] or f"html_to_ppt.js exited {proc.returncode}",
        )

    size = pptx_path.stat().st_size if pptx_path.exists() else 0
    return RenderResult(
        status="rendered",
        fmt="ppt",
        fidelity=fidelity,
        output_path=str(pptx_path),
        file_bytes=size,
        unit_count=len(units),
        warnings=[f"HTML-first PPT：版式源 {html_path}"],
    )


def material_to_storyline(
    material: dict[str, Any], constants: Any, fidelity: str = "final"
) -> tuple[list[dict], list[str], list[dict[str, Any]]]:
    """Convert formatted_material.v1 -> mck storyline list.

    Returns (storyline, warnings, degraded_info).
    degraded_info entries: {unit_id, visual_type, chosen_layout, reason}
    """
    units = material.get("material_units") or []
    warnings: list[str] = []
    degraded: list[dict[str, Any]] = []
    storyline: list[dict] = []
    total = len(units)
    draft = fidelity == "draft"
    for i, unit in enumerate(units):
        content = unit.get("finalized_content") or {}
        visual = unit.get("visual_object") or {}
        layout, is_degraded = _pick_layout(unit, i, total)
        if draft and layout not in _DRAFT_STRUCTURAL:
            layout = "key_takeaway"  # wireframe: collapse charts/tables to text
        builder = _LAYOUT_BUILDERS.get(layout, _build_text_fallback)
        if is_degraded:
            vt = (visual.get("visual_type") or "").strip()
            degraded.append({
                "unit_id": unit.get("unit_id", i),
                "visual_type": vt or "unspecified",
                "chosen_layout": layout,
                "reason": f"无直接 builder 支持 visual_type={vt or '(空)'}，降级为 {layout}",
            })
        try:
            data = builder(unit, content, visual, constants)
            storyline.append({"type": layout, "data": data})
        except Exception as exc:  # never let one unit kill the deck
            warnings.append(f"unit {unit.get('unit_id', i)} layout={layout} 降级为文本：{exc}")
            storyline.append({"type": "key_takeaway", "data": _build_text_fallback(unit, content, visual, constants)})
    return storyline, warnings, degraded


def render_ppt(
    material: dict[str, Any],
    out_dir: Path,
    fidelity: str = "final",
    file_stem: str = "deliverable",
) -> RenderResult:
    out_dir = Path(out_dir)
    try:
        from presentation_agent.vendor.mck_ppt import constants as c
        from presentation_agent.vendor.mck_ppt.deck_builder import DeckBuilder
    except Exception as exc:  # python-pptx / lxml missing
        html_fallback = _render_html_first_ppt(material, out_dir, fidelity=fidelity, file_stem=file_stem)
        if html_fallback.status == "rendered":
            html_fallback.warnings.insert(0, f"mck_ppt 缺少依赖，已用 HTML-first fallback：{exc}")
            return html_fallback
        detail = f"mck_ppt 缺少 python-pptx + lxml：{exc}"
        if html_fallback.detail:
            detail = f"{detail}\nHTML-first fallback 也失败：{html_fallback.detail}"
        return RenderResult(
            status="skipped_missing_dep",
            fmt="ppt",
            fidelity=fidelity,
            unit_count=len(material.get("material_units") or []),
            warnings=html_fallback.warnings,
            detail=detail,
        )

    storyline, warnings, degraded = material_to_storyline(material, c, fidelity=fidelity)
    if not storyline:
        return RenderResult(status="no_units", fmt="ppt", fidelity=fidelity, warnings=warnings)

    if degraded:
        for d in degraded:
            warnings.append(f"[degraded] unit {d['unit_id']}: {d['reason']}")

    suffix = "draft" if fidelity == "draft" else "final"
    out_path = out_dir / f"{file_stem}_{suffix}.pptx"
    try:
        DeckBuilder.build(storyline, str(out_path), total_slides=len(storyline))
    except Exception as exc:
        html_fallback = _render_html_first_ppt(material, out_dir, fidelity=fidelity, file_stem=file_stem)
        if html_fallback.status == "rendered":
            html_fallback.warnings = warnings + [
                f"mck_ppt 构建失败，已用 HTML-first fallback：{exc}",
            ] + html_fallback.warnings
            return html_fallback
        return RenderResult(
            status="error",
            fmt="ppt",
            fidelity=fidelity,
            warnings=warnings + html_fallback.warnings,
            detail=f"mck_ppt 构建失败：{exc}\nHTML-first fallback：{html_fallback.detail or html_fallback.status}",
        )

    size = out_path.stat().st_size if out_path.exists() else 0
    return RenderResult(
        status="rendered",
        fmt="ppt",
        fidelity=fidelity,
        output_path=str(out_path),
        file_bytes=size,
        unit_count=len(storyline),
        warnings=["mck_ppt shape-native PPT"] + warnings,
        degraded=bool(degraded),
        degraded_units=degraded,
    )
