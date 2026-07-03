"""Independent formatted_material.v2(document) -> polished DOCX renderer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from presentation_agent.renderers.base import RenderResult
from presentation_agent.renderers.diagram import render_svg_with_png_fallback
from presentation_agent.renderers.report_docx import (
    CONTENT_WIDTH_DXA,
    _add_bullets,
    _add_citation,
    _add_data_table,
    _add_heading,
    _add_note_box,
    _add_page_field,
    _render_appendices,
    _render_method_and_risks,
    _render_narrative_block,
    _render_recommendations,
    _set_run_font,
    _style_document,
)

CAPABILITY_ID = "format.document.v2"
PRESET_NAME = "standard_business_brief"


def _validate(formatted: dict[str, Any], report: dict[str, Any]) -> None:
    if formatted.get("agent_id") != "format" or formatted.get("schema") != "formatted_material.v2":
        raise ValueError("formatted document renderer requires formatted_material.v2")
    if formatted.get("delivery_target") != "document":
        raise ValueError("formatted document renderer only accepts delivery_target=document")
    if report.get("agent_id") != "report" or report.get("schema") != "report.v1":
        raise ValueError("formatted document renderer requires report.v1")
    section_ids = {item.get("section_id") for item in report.get("sections") or []}
    claim_ids = {item.get("claim_id") for item in report.get("claims") or []}
    for asset in formatted.get("visual_assets") or []:
        if not set(asset.get("source_section_ids") or []) <= section_ids:
            raise ValueError(f"{asset.get('asset_id')}: unknown source section mapping")
        if not set(asset.get("source_claim_ids") or []) <= claim_ids:
            raise ValueError(f"{asset.get('asset_id')}: unknown source claim mapping")
    protected = set((report.get("format_handoff") or {}).get("protected_caveats") or [])
    preserved = {
        item.get("source_caveat")
        for item in formatted.get("caveat_preservation") or []
        if item.get("status") in {"preserved", "reworded_equivalent"}
    }
    if not protected <= preserved:
        raise ValueError("formatted_material.v2 does not preserve every protected report caveat")


def _add_toc(doc: Any, report: dict[str, Any]) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    _add_heading(doc, "目录", 1)
    entries = ["执行摘要"]
    entries.extend(
        f"{index}. {section.get('heading', '')}"
        for index, section in enumerate(report.get("sections") or [], 1)
    )
    entries.extend(["方法与边界", "风险与反方观点", "建议", "附录"])
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
    else:
        asset_dir.mkdir(parents=True, exist_ok=True)
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
    _add_asset_trace(doc, asset)
    for caveat in asset.get("caveats") or []:
        _add_note_box(doc, "图表边界", str(caveat), caveat=True)


def _assets_by_section(formatted: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    ordered_ids = formatted.get("render_plan", {}).get("asset_order") or []
    lookup = {item.get("asset_id"): item for item in formatted.get("visual_assets") or []}
    assets = [lookup[item] for item in ordered_ids if item in lookup]
    assets.extend(item for item in formatted.get("visual_assets") or [] if item not in assets)
    result: dict[str, list[dict[str, Any]]] = {}
    for asset in assets:
        for section_id in asset.get("source_section_ids") or []:
            result.setdefault(section_id, []).append(asset)
    return result


def _protected_caveats_for_section(report: dict[str, Any], report_section: dict[str, Any]) -> list[str]:
    protected = set((report.get("format_handoff") or {}).get("protected_caveats") or [])
    section_claims = set(report_section.get("claim_ids") or [])
    caveats: list[str] = []
    for claim in report.get("claims") or []:
        if claim.get("claim_id") not in section_claims:
            continue
        for caveat in claim.get("caveats") or []:
            if caveat in protected and caveat not in caveats:
                caveats.append(caveat)
    return caveats


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
        metadata = report["report_metadata"]
        section = doc.sections[0]
        header = section.header.paragraphs[0]
        header_run = header.add_run(str(metadata.get("title") or formatted.get("topic") or "分析报告"))
        _set_run_font(header_run, size=8, color="666666")
        _add_page_field(section.footer.paragraphs[0])

        # Editorial cover: intentionally uses only report metadata.
        cover = doc.add_paragraph()
        cover.paragraph_format.space_before = Pt(120)
        cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cover.add_run(str(metadata.get("title") or formatted.get("topic") or "分析报告"))
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

        summary = report.get("executive_summary") or {}
        _add_heading(doc, "执行摘要", 1)
        paragraph = doc.add_paragraph(str(summary.get("context") or ""))
        _add_note_box(doc, "核心答案", str(summary.get("core_answer") or ""))
        _add_heading(doc, "关键发现", 2)
        _add_bullets(doc, summary.get("key_findings") or [])
        _add_heading(doc, "业务含义", 2)
        _add_bullets(doc, summary.get("implications") or [])
        _add_note_box(doc, "需要确认", str(summary.get("expected_action") or ""))

        section_assets = _assets_by_section(formatted)
        for index, report_section in enumerate(report.get("sections") or [], 1):
            _add_heading(doc, f"{index}. {report_section.get('heading', '')}", 1)
            _add_note_box(doc, "本节判断", str(report_section.get("section_thesis") or ""))
            for block in report_section.get("narrative_blocks") or []:
                _render_narrative_block(doc, report, block)
            for table in report_section.get("tables") or []:
                _add_data_table(
                    doc,
                    str(table.get("title") or table.get("table_id") or "表格"),
                    [str(value) for value in table.get("columns") or []],
                    table.get("rows") or [],
                    table.get("source_refs") or [],
                    table.get("notes") or [],
                )
            for asset in section_assets.get(report_section.get("section_id"), []):
                _render_visual_asset(doc, asset, out_dir / f"{file_stem}_assets")
            for caveat in _protected_caveats_for_section(report, report_section):
                _add_note_box(doc, "关键边界", caveat, caveat=True)
            _add_note_box(doc, "本节结论", str(report_section.get("section_conclusion") or ""))
            transition = str(report_section.get("transition") or "")
            if transition:
                paragraph = doc.add_paragraph(style="Report Citation")
                run = paragraph.add_run("承接：" + transition)
                _set_run_font(run, size=8.5, color="666666", italic=True)

        _render_method_and_risks(doc, report)
        _render_recommendations(doc, report.get("recommendations") or [])
        _render_appendices(doc, report)
        _normalize_east_asia_font(doc)
        output_path = out_dir / f"{file_stem}.docx"
        doc.save(output_path)
        return RenderResult(
            status="rendered",
            fmt="document",
            fidelity="formatted",
            output_path=str(output_path),
            file_bytes=output_path.stat().st_size,
            unit_count=len(formatted.get("delivery_units") or []),
            detail=f"preset={PRESET_NAME}; visual_assets={len(formatted.get('visual_assets') or [])}",
        )
    except Exception as exc:
        return RenderResult(
            status="error",
            fmt="document",
            fidelity="formatted",
            unit_count=len(formatted.get("delivery_units") or []),
            detail=str(exc),
        )
