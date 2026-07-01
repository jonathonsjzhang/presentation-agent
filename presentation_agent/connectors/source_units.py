from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def attach_source_units(result: dict[str, Any], path: Path) -> dict[str, Any]:
    """Attach stable, modality-aware source units to connector output."""
    if isinstance(result.get("source_units"), list):
        return result

    source_id = _source_id(path)
    units: list[dict[str, Any]] = []

    paragraphs = result.get("paragraphs")
    if isinstance(paragraphs, list):
        location_prefix = "page" if result.get("source_type") == "pdf" else "paragraph"
        for index, raw in enumerate(paragraphs, start=1):
            text = str(raw or "").strip()
            if not text:
                continue
            unit = {
                "source_unit_id": f"{source_id}-T{index:04d}",
                "source_id": source_id,
                "source_location": f"{location_prefix} {index}",
                "modality": "text",
                "raw_content": text,
                "inspection_status": "inspected",
            }
            attribution = _attribution(text)
            if attribution:
                unit["attribution"] = attribution
            units.append(unit)

    sheets = result.get("sheets")
    if isinstance(sheets, list):
        for sheet_index, sheet in enumerate(sheets, start=1):
            if not isinstance(sheet, dict):
                continue
            name = str(sheet.get("name") or f"sheet-{sheet_index}")
            rows = sheet.get("rows", [])
            for row_index, row in enumerate(rows, start=1):
                units.append(
                    _table_unit(
                        source_id,
                        len(units) + 1,
                        f"sheet {name} row {row_index}",
                        row,
                    )
                )

    tables = result.get("tables")
    if isinstance(tables, list):
        for table_index, table in enumerate(tables, start=1):
            if not isinstance(table, dict):
                continue
            name = str(table.get("name") or f"table-{table_index}")
            rows = table.get("rows", [])
            for row_index, row in enumerate(rows, start=1):
                units.append(
                    _table_unit(
                        source_id,
                        len(units) + 1,
                        f"table {name} row {row_index}",
                        row,
                    )
                )

    images = result.get("images")
    if isinstance(images, list):
        for image_index, image in enumerate(images, start=1):
            if not isinstance(image, dict):
                continue
            location = (
                f"page {image.get('page_number')}"
                if image.get("page_number")
                else f"image {image_index}"
            )
            units.append(
                {
                    "source_unit_id": f"{source_id}-I{image_index:04d}",
                    "source_id": source_id,
                    "source_location": location,
                    "modality": "image",
                    "raw_content": str(
                        image.get("extracted_path")
                        or image.get("filename")
                        or ""
                    ),
                    "inspection_status": "unresolved",
                }
            )

    if not units:
        materials = result.get("materials")
        if isinstance(materials, list):
            for index, material in enumerate(materials, start=1):
                units.append(
                    {
                        "source_unit_id": f"{source_id}-M{index:04d}",
                        "source_id": source_id,
                        "source_location": f"material {index}",
                        "modality": "text",
                        "raw_content": json.dumps(
                            material, ensure_ascii=False, default=str
                        ),
                        "inspection_status": "inspected",
                    }
                )

    result["source_units"] = units
    result["source_unit_summary"] = {
        "total": len(units),
        "text": sum(unit["modality"] == "text" for unit in units),
        "table": sum(unit["modality"] == "table" for unit in units),
        "image": sum(unit["modality"] == "image" for unit in units),
        "unresolved": sum(
            unit["inspection_status"] == "unresolved" for unit in units
        ),
    }
    return result


def _table_unit(
    source_id: str, sequence: int, location: str, row: Any
) -> dict[str, Any]:
    return {
        "source_unit_id": f"{source_id}-R{sequence:04d}",
        "source_id": source_id,
        "source_location": location,
        "modality": "table",
        "raw_content": json.dumps(row, ensure_ascii=False, default=str),
        "inspection_status": "inspected",
    }


def _source_id(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "-", path.stem).strip("-").upper()
    return (stem or "SOURCE")[:40]


def _attribution(text: str) -> dict[str, str]:
    match = re.match(r"^(男|女)\s*(\d{1,3})岁(?:[，,\s]+(.{1,30}))?", text)
    if not match:
        return {}
    return {
        "speaker": f"{match.group(1)} {match.group(2)}岁",
        "profile": str(match.group(3) or "").strip(),
    }
