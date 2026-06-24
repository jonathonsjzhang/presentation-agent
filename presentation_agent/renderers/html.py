"""HTML render backend — formatted_material.v1 -> self-contained .html.

Zero third-party dependencies (pure string templating). Produces a McKinsey-
styled single-file deck/report: navy headers, action titles, source footers,
evidence-drawer style supporting content, and a clean print layout.

Works for both `html` format (interactive modules) and as a universal preview
fallback for any format when richer backends are unavailable.
"""

from __future__ import annotations

import html as _html
from pathlib import Path
from typing import Any

from presentation_agent.renderers.base import RenderResult

# McKinsey-ish palette mirrored from the vendored engine constants.
_NAVY = "#051C2C"
_BLUE = "#006BA6"
_GREEN = "#007A53"
_ORANGE = "#D46A00"
_GRAY = "#666666"
_LINE = "#CCCCCC"
_BG = "#F2F2F2"

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Georgia','Songti SC',serif; color:#333; background:#e9ecef; line-height:1.5; }
.deck { max-width: 1100px; margin: 0 auto; padding: 24px; }
.unit { background:#fff; margin: 0 0 28px; padding: 40px 48px 24px; box-shadow: 0 1px 6px rgba(0,0,0,.12); position: relative; min-height: 480px; page-break-after: always; }
.unit .pageno { position:absolute; top:18px; right:24px; font-size:12px; color:#999; }
.action-title { font-size: 24px; color: %(navy)s; font-weight: 700; line-height:1.3; padding-bottom:14px; border-bottom: 2px solid %(navy)s; margin-bottom: 22px; }
.primary { font-size: 17px; color:#222; margin-bottom: 18px; font-family:'Arial','PingFang SC',sans-serif; }
ul.points { list-style:none; margin: 6px 0 18px; }
ul.points li { font-family:'Arial','PingFang SC',sans-serif; font-size: 15px; padding: 9px 0 9px 22px; position:relative; border-bottom:1px solid #eee; }
ul.points li::before { content:''; position:absolute; left:4px; top:16px; width:8px; height:8px; background:%(blue)s; border-radius:2px; }
.cover { background: %(navy)s; color:#fff; min-height:520px; display:flex; flex-direction:column; justify-content:center; padding:64px; }
.cover h1 { font-size: 40px; line-height:1.25; margin-bottom: 18px; }
.cover .sub { font-size: 19px; color:#cdd6dd; font-family:'Arial',sans-serif; }
.cover .meta { margin-top: 40px; font-size:14px; color:#9fb0bb; font-family:'Arial',sans-serif; }
.divider { background:%(bg)s; min-height:420px; display:flex; flex-direction:column; justify-content:center; padding-left:64px; }
.divider .lbl { font-size:64px; color:%(blue)s; font-weight:700; }
.divider h2 { font-size:32px; color:%(navy)s; margin:10px 0; }
.cards { display:flex; gap:16px; margin: 12px 0 18px; }
.card { flex:1; background:%(bg)s; border-top:4px solid %(blue)s; padding:18px; }
.card .n { font-size:28px; color:%(blue)s; font-weight:700; }
.card .t { font-weight:700; margin:6px 0; font-size:16px; }
.card .d { font-size:13px; color:#555; font-family:'Arial',sans-serif; }
table.mck { width:100%%; border-collapse:collapse; margin: 8px 0 18px; font-family:'Arial',sans-serif; font-size:14px; }
table.mck th { background:%(navy)s; color:#fff; text-align:left; padding:10px 12px; }
table.mck td { padding:9px 12px; border-bottom:1px solid %(line)s; }
table.mck tr:nth-child(even) td { background:#fafafa; }
.insight { background:%(bg)s; border-left:4px solid %(green)s; padding:14px 18px; margin: 8px 0 16px; font-family:'Arial',sans-serif; }
.insight .h { color:%(green)s; font-weight:700; margin-bottom:6px; }
.bar-row { display:flex; align-items:center; gap:10px; margin:6px 0; font-family:'Arial',sans-serif; font-size:13px; }
.bar-row .lab { width:120px; }
.bar-row .track { flex:1; background:#eee; height:18px; border-radius:3px; overflow:hidden; }
.bar-row .fill { height:100%%; background:%(blue)s; }
.bar-row .val { width:48px; text-align:right; }
.gap { background:#FFF3E0; border:1px dashed %(orange)s; color:#8a4b00; padding:8px 12px; font-size:13px; margin:8px 0; font-family:'Arial',sans-serif; }
.source { position:absolute; bottom:14px; left:48px; font-size:11px; color:%(gray)s; font-family:'Arial',sans-serif; }
@media print { body{background:#fff;} .unit{box-shadow:none; margin:0;} }
""" % {
    "navy": _NAVY, "blue": _BLUE, "green": _GREEN, "orange": _ORANGE,
    "gray": _GRAY, "line": _LINE, "bg": _BG,
}

# Draft (wireframe) override: grayscale, dashed boxes, visible DRAFT watermark.
# Lets agent4's low-fidelity output be told apart from agent5's final at a glance.
_CSS_DRAFT = """
body.draft { filter: grayscale(1); }
body.draft .unit { border: 2px dashed #999; box-shadow:none; }
body.draft .unit::after { content:'草稿 DRAFT'; position:absolute; top:14px; left:24px;
  font-family:'Arial',sans-serif; font-size:11px; letter-spacing:2px; color:#fff;
  background:#999; padding:2px 8px; border-radius:2px; }
body.draft .action-title { border-bottom-style: dashed; }
body.draft .cover, body.draft .divider { background:#555 !important; }
body.draft .card, body.draft table.mck th, body.draft .bar-row .fill { background:#888 !important; }
body.draft .card { border-top-color:#888 !important; }
"""

_CSS_PPT_EXPORT = """
body.ppt-export { background:#fff; overflow:hidden; }
body.ppt-export .deck { width: 1600px; max-width:none; margin:0; padding:0; }
body.ppt-export .unit {
  width:1600px; height:900px; min-height:900px; margin:0; padding:72px 88px 44px;
  box-shadow:none; page-break-after:always; overflow:hidden;
}
body.ppt-export .cover { min-height:900px; padding:108px; }
body.ppt-export .divider { min-height:900px; padding-left:108px; }
body.ppt-export .action-title { font-size:38px; margin-bottom:34px; padding-bottom:22px; }
body.ppt-export .primary { font-size:25px; margin-bottom:28px; }
body.ppt-export ul.points li { font-size:23px; padding:15px 0 15px 34px; }
body.ppt-export ul.points li::before { top:28px; width:12px; height:12px; }
body.ppt-export .cover h1 { font-size:56px; max-width:1260px; }
body.ppt-export .cover .sub { font-size:30px; }
body.ppt-export .cover .meta { font-size:20px; }
body.ppt-export .cards { gap:24px; }
body.ppt-export .card { padding:26px; }
body.ppt-export .card .n { font-size:42px; }
body.ppt-export .card .t { font-size:24px; }
body.ppt-export .card .d { font-size:19px; }
body.ppt-export table.mck { font-size:21px; }
body.ppt-export table.mck th { padding:15px 18px; }
body.ppt-export table.mck td { padding:14px 18px; }
body.ppt-export .insight { font-size:21px; padding:20px 24px; margin:14px 0 22px; }
body.ppt-export .bar-row { font-size:20px; gap:16px; margin:14px 0; }
body.ppt-export .bar-row .lab { width:180px; }
body.ppt-export .bar-row .track { height:28px; }
body.ppt-export .bar-row .val { width:72px; }
body.ppt-export .gap { font-size:19px; padding:13px 18px; }
body.ppt-export .source { bottom:26px; left:88px; right:88px; font-size:15px; }
"""


def _esc(x: Any) -> str:
    return _html.escape(str(x if x is not None else ""))


def _points(content: dict) -> list[str]:
    pts = content.get("supporting_points") or []
    if isinstance(pts, str):
        pts = [pts]
    return [str(p) for p in pts if str(p).strip()]


def _render_unit(unit: dict, idx: int, total: int) -> str:
    content = unit.get("finalized_content") or {}
    visual = unit.get("visual_object") or {}
    los = unit.get("layout_or_structure") or {}
    layout = (los.get("layout_type") or "").lower()
    headline = unit.get("headline") or content.get("primary_text") or ""
    src = ""
    sd = unit.get("source_display") or {}
    if isinstance(sd, dict):
        src = sd.get("footer", "")

    # cover
    if layout == "cover" or idx == 0:
        return (
            f'<section class="unit cover"><div class="pageno">{idx+1}/{total}</div>'
            f'<h1>{_esc(headline)}</h1>'
            f'<div class="sub">{_esc(content.get("body") or (_points(content)[:1] or [""])[0])}</div>'
            f'<div class="meta">{_esc(content.get("author",""))} &nbsp; {_esc(content.get("date",""))}</div>'
            f"</section>"
        )
    # section divider
    if layout == "section_divider":
        return (
            f'<section class="unit divider"><div class="pageno">{idx+1}/{total}</div>'
            f'<div class="lbl">{_esc(content.get("section_label",""))}</div>'
            f"<h2>{_esc(headline)}</h2>"
            f'<div class="sub">{_esc(content.get("body",""))}</div></section>'
        )
    # closing
    if layout == "closing" or idx == total - 1 and not _points(content):
        return (
            f'<section class="unit cover"><div class="pageno">{idx+1}/{total}</div>'
            f'<h1>{_esc(headline or "谢谢")}</h1>'
            f'<div class="sub">{_esc(content.get("body",""))}</div></section>'
        )

    body_html = [f'<div class="action-title">{_esc(headline)}</div>']
    if content.get("primary_text") and content.get("primary_text") != headline:
        body_html.append(f'<div class="primary">{_esc(content["primary_text"])}</div>')

    # cards layout for four_column / executive_summary
    pts = _points(content)
    if layout in ("four_column", "executive_summary") and pts:
        cards = []
        for i, p in enumerate(pts[:4], 1):
            t, d = (p.split("：", 1) + [""])[:2] if "：" in p else (p[:12], p)
            cards.append(f'<div class="card"><div class="n">{i}</div><div class="t">{_esc(t)}</div><div class="d">{_esc(d)}</div></div>')
        body_html.append('<div class="cards">' + "".join(cards) + "</div>")
    elif pts:
        body_html.append('<ul class="points">' + "".join(f"<li>{_esc(p)}</li>" for p in pts) + "</ul>")

    if content.get("body"):
        body_html.append(f'<div class="primary">{_esc(content["body"])}</div>')

    # table
    for tbl in content.get("tables") or []:
        if isinstance(tbl, dict) and tbl.get("rows"):
            heads = tbl.get("headers") or []
            th = "".join(f"<th>{_esc(h)}</th>" for h in heads)
            trs = "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in tbl["rows"])
            body_html.append(f'<table class="mck"><tr>{th}</tr>{trs}</table>')

    # visual as bar chart (data_fields with pct)
    df = visual.get("data_fields") or []
    if df and visual.get("visual_type"):
        bars = []
        for item in df[:8]:
            if isinstance(item, dict):
                lab, val = item.get("label", ""), float(item.get("pct", item.get("value", 0)) or 0)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                val, lab = float(item[0]), str(item[1])
            else:
                continue
            pct = val * 100 if val <= 1 else val
            bars.append(f'<div class="bar-row"><span class="lab">{_esc(lab)}</span><span class="track"><span class="fill" style="width:{min(pct,100):.0f}%"></span></span><span class="val">{pct:.0f}%</span></div>')
        if bars:
            title = visual.get("title") or visual.get("reader_takeaway") or ""
            if title:
                body_html.append(f'<div class="insight"><div class="h">{_esc(title)}</div></div>')
            body_html.extend(bars)

    # insight from reader_takeaway
    if visual.get("reader_takeaway"):
        body_html.append(f'<div class="insight"><div class="h">启示</div>{_esc(visual["reader_takeaway"])}</div>')

    # gap display
    gd = unit.get("gap_display") or {}
    if isinstance(gd, dict) and gd.get("visible_note"):
        body_html.append(f'<div class="gap">⚠ {_esc(gd["visible_note"])}</div>')

    if src:
        body_html.append(f'<div class="source">{_esc(src)}</div>')

    return f'<section class="unit"><div class="pageno">{idx+1}/{total}</div>' + "".join(body_html) + "</section>"


def build_html_document(material: dict[str, Any], fidelity: str = "final", export_mode: str = "web") -> str:
    """Return a self-contained HTML document for web preview or PPT export."""
    units = material.get("material_units") or []
    topic = material.get("topic", "汇报材料")
    total = len(units)
    sections = "".join(_render_unit(u, i, total) for i, u in enumerate(units))
    is_draft = fidelity == "draft"
    badge = "草稿版" if is_draft else "正式版"
    is_ppt_export = export_mode == "ppt"
    css = _CSS + (_CSS_DRAFT if is_draft else "") + (_CSS_PPT_EXPORT if is_ppt_export else "")
    classes = []
    if is_draft:
        classes.append("draft")
    if is_ppt_export:
        classes.append("ppt-export")
    body_class = f" class='{' '.join(classes)}'" if classes else ""
    return (
        f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_esc(topic)} · {badge}</title><style>{css}</style></head>"
        f"<body{body_class}><div class='deck'>{sections}</div></body></html>"
    )


def render_html(material: dict[str, Any], out_dir: Path, fidelity: str = "final", file_stem: str = "deliverable") -> RenderResult:
    out_dir = Path(out_dir)
    units = material.get("material_units") or []
    if not units:
        return RenderResult(status="no_units", fmt="html", fidelity=fidelity)

    total = len(units)
    doc = build_html_document(material, fidelity=fidelity)
    suffix = "draft" if fidelity == "draft" else "final"
    out_path = out_dir / f"{file_stem}_{suffix}.html"
    out_path.write_text(doc, encoding="utf-8")
    size = out_path.stat().st_size
    return RenderResult(
        status="rendered", fmt="html", fidelity=fidelity,
        output_path=str(out_path), file_bytes=size, unit_count=total,
    )
