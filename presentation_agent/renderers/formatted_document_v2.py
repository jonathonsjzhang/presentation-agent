"""Independent formatted_material.v2(document) -> polished DOCX renderer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from presentation_agent.renderers.base import RenderResult
from presentation_agent.renderers.diagram import render_svg_with_png_fallback
from presentation_agent.renderers.report_docx import (
    _add_bullets,
    _add_data_table,
    _add_heading,
    _add_note_box,
    _add_page_field,
    _set_run_font,
    _style_document,
)

import re

CAPABILITY_ID = "format.document.v2"
PRESET_NAME = "standard_business_brief"


def _normalize_heading(heading: str) -> str:
    """Strip 'N. ' / 'N、' prefix so section_heading can match markdown ## lines."""
    return re.sub(r"^\d+[\.\、\s]+", "", heading).strip()


def _validate(formatted: dict[str, Any], report: dict[str, Any]) -> None:
    if formatted.get("agent_id") != "format" or formatted.get("schema") != "formatted_material.v2":
        raise ValueError("formatted document renderer requires formatted_material.v2")
    if formatted.get("delivery_target") != "document":
        raise ValueError("formatted document renderer only accepts delivery_target=document")
    if report.get("agent_id") != "report" or report.get("schema") != "report.v1":
        raise ValueError("formatted document renderer requires report.v1")
    if not str(report.get("report_markdown") or "").strip():
        raise ValueError("report.v1 requires report_markdown")


def _add_toc(doc: Any, report: dict[str, Any]) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    _add_heading(doc, "目录", 1)
    entries = [
        line[3:].strip()
        for line in str(report.get("report_markdown") or "").splitlines()
        if line.startswith("## ")
    ]
    for index, entry in enumerate(entries):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.left_indent = Pt(0 if index == 0 else 12)
        paragraph.paragraph_format.space_after = Pt(8)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = paragraph.add_run(entry)
        _set_run_font(run, size=11 if index else 12, color="253746", bold=index == 0)


def _add_asset_trace(doc: Any, asset: dict[str, Any]) -> None:
    bits = [
        "Section: " + "、".join(asset.get("source_section_ids") or []),
        "Claim: " + "、".join(asset.get("source_claim_ids") or []) or "Claim: -",
        "Evidence: " + "、".join(asset.get("source_evidence_refs") or []) or "Evidence: -",
    ]
    paragraph = doc.add_paragraph(style="Report Citation")
    run = paragraph.add_run(" | ".join(bits))
    _set_run_font(run, size=8, color="666666", italic=True)
    note = str(asset.get("source_note") or "").strip()
    if note:
        paragraph = doc.add_paragraph(style="Report Citation")
        run = paragraph.add_run(note)
        _set_run_font(run, size=8, color="666666", italic=True)


def _chart_png(asset: dict[str, Any], path: Path) -> Path:
    from PIL import Image, ImageDraw

    from presentation_agent.renderers.diagram import _font

    data = asset.get("data") or {}
    categories = list(data.get("categories") or [])
    series = data.get("series")
    if isinstance(series, list) and series:
        return _line_chart_png(asset, path, categories, series)
    values = list(data.get("values") or [])
    if not categories or len(categories) != len(values):
        raise ValueError(f"{asset.get('asset_id')}: chart requires equally sized categories and values")
    numeric = [float(str(value).replace("%", "").replace(",", "")) for value in values]
    width, height = 1400, 650
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 30), str(asset.get("title") or ""), fill="#0B2545", font=_font(34))
    maximum = max(numeric) if numeric else 1
    left, top, chart_width = 300, 125, 980
    bar_height, gap = 75, 55
    unit = str(data.get("unit") or "")
    for index, (label, value, original) in enumerate(zip(categories, numeric, values)):
        y = top + index * (bar_height + gap)
        draw.text((55, y + 20), str(label), fill="#253746", font=_font(24))
        bar_width = int(chart_width * value / maximum) if maximum else 0
        color = ("#006BA6", "#64748B", "#007A53", "#D46A00")[index % 4]
        draw.rounded_rectangle((left, y, left + bar_width, y + bar_height), radius=8, fill=color)
        value_label = f"{original}{unit}" if unit and not str(original).endswith(unit) else str(original)
        draw.text((left + bar_width + 18, y + 20), value_label, fill="#0B2545", font=_font(25))
    image.save(path, "PNG")
    return path


def _line_chart_png(
    asset: dict[str, Any],
    path: Path,
    categories: list[Any],
    series: list[Any],
) -> Path:
    from PIL import Image, ImageDraw

    from presentation_agent.renderers.diagram import _font

    if not categories:
        raise ValueError(f"{asset.get('asset_id')}: line chart requires categories")
    normalized_series = []
    for row in series:
        if not isinstance(row, dict):
            continue
        values = [_to_float(value) for value in row.get("values") or []]
        if len(values) != len(categories):
            continue
        if any(value is not None for value in values):
            normalized_series.append(
                {"name": str(row.get("name") or ""), "values": values}
            )
    if not normalized_series:
        raise ValueError(f"{asset.get('asset_id')}: line chart requires numeric series")

    width, height = 1400, 650
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 30), str(asset.get("title") or ""), fill="#0B2545", font=_font(34))

    left, top, right, bottom = 105, 130, 1320, 535
    draw.line((left, bottom, right, bottom), fill="#94A3B8", width=2)
    draw.line((left, top, left, bottom), fill="#94A3B8", width=2)

    numeric = [
        value
        for row in normalized_series
        for value in row["values"]
        if value is not None
    ]
    minimum = min(numeric)
    maximum = max(numeric)
    if minimum == maximum:
        minimum -= 1
        maximum += 1
    span = maximum - minimum
    colors = ("#006BA6", "#007A53", "#D46A00", "#7C3AED", "#64748B", "#B91C1C")

    def xy(index: int, value: float) -> tuple[float, float]:
        x = left + (right - left) * index / max(1, len(categories) - 1)
        y = bottom - (bottom - top) * (value - minimum) / span
        return x, y

    for tick in range(5):
        value = minimum + span * tick / 4
        y = bottom - (bottom - top) * tick / 4
        draw.line((left, y, right, y), fill="#E2E8F0", width=1)
        draw.text((35, y - 12), _format_tick(value), fill="#64748B", font=_font(18))

    for series_index, row in enumerate(normalized_series):
        color = colors[series_index % len(colors)]
        previous: tuple[float, float] | None = None
        for index, value in enumerate(row["values"]):
            if value is None:
                previous = None
                continue
            point = xy(index, value)
            if previous is not None:
                draw.line((previous[0], previous[1], point[0], point[1]), fill=color, width=4)
            draw.ellipse((point[0] - 4, point[1] - 4, point[0] + 4, point[1] + 4), fill=color)
            previous = point
        legend_x = 125 + series_index * 205
        draw.rectangle((legend_x, 88, legend_x + 26, 104), fill=color)
        draw.text((legend_x + 34, 82), row["name"], fill="#253746", font=_font(20))

    label_step = max(1, len(categories) // 6)
    for index, label in enumerate(categories):
        if index not in (0, len(categories) - 1) and index % label_step:
            continue
        x = left + (right - left) * index / max(1, len(categories) - 1)
        draw.text((x - 45, bottom + 18), str(label)[:10], fill="#64748B", font=_font(16))

    note = str((asset.get("data") or {}).get("sampling_note") or "")
    if note:
        draw.text((55, 590), note, fill="#64748B", font=_font(18))
    image.save(path, "PNG")
    return path


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(str(value).replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _format_tick(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _matrix_png(asset: dict[str, Any], path: Path) -> Path:
    from PIL import Image, ImageDraw
    from presentation_agent.renderers.diagram import _font, _labels

    data = asset.get("data") or {}
    labels = _labels(data)
    image = Image.new("RGB", (1200, 720), "white")
    draw = ImageDraw.Draw(image)
    draw.text((45, 25), str(asset.get("title") or ""), fill="#0B2545", font=_font(32))
    draw.rectangle((170, 130, 1090, 630), outline="#64748B", width=3)
    draw.line((630, 130, 630, 630), fill="#CBD5E1", width=3)
    draw.line((170, 380, 1090, 380), fill="#CBD5E1", width=3)
    positions = ((220, 175), (680, 175), (220, 425), (680, 425))
    for label, position in zip(labels, positions):
        draw.text(position, label, fill="#253746", font=_font(23))
    for key, xy in (("x_label", (500, 660)), ("y_label", (25, 355))):
        if data.get(key):
            draw.text(xy, str(data[key]), fill="#64748B", font=_font(20))
    image.save(path, "PNG")
    return path


def _render_visual_asset(doc: Any, asset: dict[str, Any], asset_dir: Path) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches

    asset_type = str(asset.get("asset_type") or "")
    title = str(asset.get("title") or asset.get("asset_id") or "视觉资产")
    if asset_type == "table":
        data = asset.get("data") or {}
        columns = [str(value) for value in data.get("columns") or data.get("headers") or []]
        rows = data.get("rows") or []
        if not columns:
            raise ValueError(f"{asset.get('asset_id')}: table requires columns/headers")
        _add_data_table(doc, title, columns, rows, asset.get("source_evidence_refs") or [], asset.get("caveats") or [])
    elif asset_type == "callout":
        _add_note_box(doc, title, str(asset.get("reader_takeaway") or ""))
    elif asset_type == "chart" and not _chart_data_ready(asset):
        _add_note_box(
            doc,
            title,
            str(asset.get("reader_takeaway") or "图表数据尚未提供，暂以要点呈现。"),
        )
    else:
        asset_dir.mkdir(parents=True, exist_ok=True)
        try:
            if asset_type == "chart":
                png_path = _chart_png(asset, asset_dir / f"{asset['asset_id']}.png")
            elif asset_type == "matrix":
                _, png_path = render_svg_with_png_fallback(asset, asset_dir)
                _matrix_png(asset, png_path)
            else:
                _, png_path = render_svg_with_png_fallback(asset, asset_dir)
            paragraph = doc.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = paragraph.add_run()
            run.add_picture(str(png_path), width=Inches(6.35))
            caption = doc.add_paragraph()
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = caption.add_run(f"{title} — {asset.get('reader_takeaway', '')}")
            _set_run_font(run, size=9.5, color="1F4D78", bold=True)
        except Exception:
            _add_note_box(
                doc,
                title,
                str(asset.get("reader_takeaway") or f"「{title}」渲染失败，数据格式不兼容，暂以文本呈现。"),
            )
    _add_asset_trace(doc, asset)
    for caveat in asset.get("caveats") or []:
        _add_note_box(doc, "图表边界", str(caveat), caveat=True)


def _chart_data_ready(asset: dict[str, Any]) -> bool:
    data = asset.get("data")
    if not isinstance(data, dict):
        return False
    categories = data.get("categories")
    series = data.get("series")
    if isinstance(categories, list) and categories and isinstance(series, list) and series:
        return True
    values = data.get("values")
    return (
        isinstance(categories, list)
        and isinstance(values, list)
        and bool(categories)
        and len(categories) == len(values)
    )


def _assets_by_section(formatted: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if "visuals" in formatted:
        result: dict[str, list[dict[str, Any]]] = {}
        for index, visual in enumerate(formatted.get("visuals") or [], 1):
            if not isinstance(visual, dict):
                continue
            prepared = {
                "asset_id": f"VIS-{index:02d}",
                "asset_type": visual.get("type"),
                "title": visual.get("title"),
                "data": visual.get("data", {}),
                "source_evidence_refs": visual.get("source_refs", []),
                "source_section_ids": [visual.get("section_heading")],
                "source_claim_ids": [],
            }
            key = _normalize_heading(str(visual.get("section_heading") or ""))
            result.setdefault(key, []).append(prepared)
        return result
    ordered_ids = formatted.get("render_plan", {}).get("asset_order") or []
    lookup = {item.get("asset_id"): item for item in formatted.get("visual_assets") or []}
    assets = [lookup[item] for item in ordered_ids if item in lookup]
    assets.extend(item for item in formatted.get("visual_assets") or [] if item not in assets)
    result: dict[str, list[dict[str, Any]]] = {}
    for asset in assets:
        for section_id in asset.get("source_section_ids") or []:
            result.setdefault(section_id, []).append(asset)
    return result


def _protected_caveats_for_section(
    formatted: dict[str, Any],
    report_section: dict[str, Any],
) -> list[str]:
    section_id = str(report_section.get("section_id") or "")
    unit_ids = {
        str(unit.get("unit_id"))
        for unit in formatted.get("delivery_units") or []
        if isinstance(unit, dict)
        and section_id in set(map(str, unit.get("source_section_ids") or []))
    }
    caveats: list[str] = []
    for row in formatted.get("caveat_preservation") or []:
        if not isinstance(row, dict):
            continue
        destinations = set(map(str, row.get("destination_unit_ids") or []))
        caveat = str(row.get("source_caveat") or "")
        if caveat and destinations & unit_ids and caveat not in caveats:
            caveats.append(caveat)
    return caveats


def _markdown_sections(markdown: str) -> list[tuple[str, list[str]]]:
    """Split canonical Markdown into H2 sections while preserving body lines."""

    sections: list[tuple[str, list[str]]] = []
    heading = ""
    body: list[str] = []
    for raw in markdown.splitlines():
        if raw.startswith("# ") and not raw.startswith("## "):
            continue
        if raw.startswith("## "):
            if heading or any(line.strip() for line in body):
                sections.append((heading, body))
            heading = raw[3:].strip()
            body = []
        else:
            body.append(raw)
    if heading or any(line.strip() for line in body):
        sections.append((heading, body))
    return sections


def _render_markdown_body(doc: Any, lines: list[str]) -> None:
    """Render a conservative Markdown subset without rewriting its wording."""

    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        if not line:
            index += 1
            continue
        if line.startswith("### "):
            _add_heading(doc, line[4:].strip(), 2)
            index += 1
            continue
        if line.startswith("> "):
            _add_note_box(doc, "边界说明", line[2:].strip(), caveat=True)
            index += 1
            continue
        if line.startswith(("- ", "* ")):
            items: list[str] = []
            while index < len(lines) and lines[index].startswith(("- ", "* ")):
                items.append(lines[index][2:].strip())
                index += 1
            _add_bullets(doc, items)
            continue
        if line.startswith("|") and index + 1 < len(lines) and lines[index + 1].startswith("|"):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].startswith("|"):
                table_lines.append(lines[index])
                index += 1
            rows = [
                [cell.strip() for cell in row.strip().strip("|").split("|")]
                for row in table_lines
            ]
            if len(rows) >= 2:
                columns = rows[0]
                data_rows = rows[2:] if set("".join(rows[1])) <= {"-", ":", " "} else rows[1:]
                _add_data_table(doc, "", columns, data_rows)
            continue
        paragraph_lines = [line]
        index += 1
        while (
            index < len(lines)
            and lines[index].strip()
            and not lines[index].startswith(("### ", "> ", "- ", "* ", "|"))
        ):
            paragraph_lines.append(lines[index].strip())
            index += 1
        paragraph = doc.add_paragraph()
        run = paragraph.add_run(" ".join(paragraph_lines))
        _set_run_font(run, color="253746")


def _set_update_fields(doc: Any) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    settings = doc.settings._element
    update = settings.find(qn("w:updateFields"))
    if update is None:
        update = OxmlElement("w:updateFields")
        settings.append(update)
    update.set(qn("w:val"), "true")


def _normalize_east_asia_font(doc: Any) -> None:
    """Avoid unstable CJK substitution in Word/LibreOffice on macOS."""
    from docx.oxml.ns import qn

    for style in doc.styles:
        if getattr(style, "_element", None) is not None and style._element.rPr is not None:
            style._element.rPr.get_or_add_rFonts().set(qn("w:eastAsia"), "PingFang SC")
    for paragraph in list(doc.paragraphs):
        for run in paragraph.runs:
            run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "PingFang SC")
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run._element.get_or_add_rPr().get_or_add_rFonts().set(
                            qn("w:eastAsia"), "PingFang SC"
                        )


def render_formatted_document_v2(
    formatted: dict[str, Any],
    report: dict[str, Any],
    out_dir: Path,
    *,
    file_stem: str = "report_formatted",
) -> RenderResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        _validate(formatted, report)
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt
    except Exception as exc:
        return RenderResult(status="error", fmt="document", fidelity="formatted", detail=str(exc))

    try:
        doc = Document()
        _style_document(doc)
        _set_update_fields(doc)
        metadata = report.get("report_metadata") or {}
        markdown = str(report.get("report_markdown") or "")
        markdown_title = next(
            (
                line[2:].strip()
                for line in markdown.splitlines()
                if line.startswith("# ") and not line.startswith("## ")
            ),
            "分析报告",
        )
        title = str(metadata.get("title") or markdown_title)
        section = doc.sections[0]
        header = section.header.paragraphs[0]
        header_run = header.add_run(title)
        _set_run_font(header_run, size=8, color="666666")
        _add_page_field(section.footer.paragraphs[0])

        # Editorial cover: intentionally uses only report metadata.
        cover = doc.add_paragraph()
        cover.paragraph_format.space_before = Pt(120)
        cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cover.add_run(title)
        _set_run_font(run, size=30, color="0B2545", bold=True)
        subtitle = doc.add_paragraph()
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        subtitle.paragraph_format.space_before = Pt(12)
        run = subtitle.add_run(
            f"{metadata.get('report_type', '')} | {metadata.get('audience', '')} | 版本 {metadata.get('version', '')}"
        )
        _set_run_font(run, size=11, color="666666")
        doc.add_page_break()
        _add_toc(doc, report)
        doc.add_page_break()

        section_assets = _assets_by_section(formatted)
        # Build heading → section_id map from report.v1 sections so both
        # Path A (visuals keyed by section_heading) and Path B (visual_assets
        # keyed by source_section_ids) resolve correctly.
        section_id_map: dict[str, str] = {}
        for sec in report.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            h = str(sec.get("heading") or "")
            if sid and h:
                section_id_map[_normalize_heading(h)] = sid
        markdown_sections = _markdown_sections(markdown)
        render_warnings: list[str] = []
        for heading, body in markdown_sections:
            _add_heading(doc, heading, 1)
            _render_markdown_body(doc, body)
            norm = _normalize_heading(heading)
            sid = section_id_map.get(norm, "")
            # Path A: visuals keyed by normalized heading
            # Path B: visual_assets keyed by section_id
            for asset in (section_assets.get(norm) or []) + (section_assets.get(sid) or []):
                try:
                    _render_visual_asset(doc, asset, out_dir / f"{file_stem}_assets")
                except Exception as exc:
                    render_warnings.append(
                        f"{asset.get('asset_id', '?')} ({asset.get('asset_type', '?')}): {exc}"
                    )
        _normalize_east_asia_font(doc)
        output_path = out_dir / f"{file_stem}.docx"
        doc.save(output_path)
        return RenderResult(
            status="rendered",
            fmt="document",
            fidelity="formatted",
            output_path=str(output_path),
            file_bytes=output_path.stat().st_size,
            unit_count=len(markdown_sections),
            warnings=render_warnings,
            detail=f"preset={PRESET_NAME}; visuals={len(formatted.get('visuals') or [])}"
            + (f"; failed={len(render_warnings)}" if render_warnings else ""),
        )
    except Exception as exc:
        return RenderResult(
            status="error",
            fmt="document",
            fidelity="formatted",
            unit_count=len(_markdown_sections(str(report.get("report_markdown") or ""))),
            detail=str(exc),
        )
