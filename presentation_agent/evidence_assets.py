from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Iterable

from presentation_agent.io import read_json


MAX_CHART_POINTS = 60
MAX_SERIES = 6


def build_evidence_assets(
    evidence_index: list[dict[str, Any]],
    *,
    max_points: int = MAX_CHART_POINTS,
) -> list[dict[str, Any]]:
    """Build compact, downstream-usable assets from Evidence E-cards.

    The Evidence index is the human/LLM-facing catalog.  This helper follows
    each E-card's sidecar reference and creates small chart-ready previews that
    Format can use without inlining the full raw workbook into its prompt.
    """

    assets: list[dict[str, Any]] = []
    for record in evidence_index:
        if not isinstance(record, dict):
            continue
        source_refs = record.get("source_refs") or {}
        sidecar_path = str(source_refs.get("parsed_artifact_path") or "")
        sidecar = read_json(Path(sidecar_path), default={}) if sidecar_path else {}
        for data_asset in record.get("data_assets") or []:
            if not isinstance(data_asset, dict):
                continue
            asset_id = str(data_asset.get("asset_id") or "")
            evidence_id = str(record.get("id") or "")
            chart_data = (
                _chart_data_from_sidecar(sidecar, data_asset, max_points=max_points)
                if data_asset.get("chart_ready")
                else {}
            )
            assets.append(
                {
                    "evidence_id": evidence_id,
                    "asset_id": asset_id,
                    "ref": _asset_ref(evidence_id, asset_id),
                    "label": data_asset.get("label") or record.get("source_name") or asset_id,
                    "source_name": record.get("source_name", ""),
                    "source_type": record.get("source_type", ""),
                    "summary": record.get("summary", ""),
                    "key_findings": record.get("key_findings", []),
                    "chart_ready": bool(chart_data),
                    "suggested_uses": data_asset.get("suggested_uses", []),
                    "source_refs": {
                        **source_refs,
                        "evidence_id": evidence_id,
                        "data_asset_id": asset_id,
                    },
                    "data_asset": data_asset,
                    "chart_data": chart_data,
                }
            )
    return assets


def evidence_runtime_fields(*payloads: Any) -> dict[str, Any]:
    """Collect evidence index/assets from input payloads for runtime carryover."""

    evidence_index = _first_non_empty("evidence_index", payloads)
    material_resolution = _first_non_empty("material_resolution", payloads)
    evidence_assets = _first_non_empty("evidence_assets", payloads)

    catalog = _first_non_empty("evidence_catalog", payloads)
    if isinstance(catalog, dict):
        evidence_index = evidence_index or catalog.get("evidence_index")
        material_resolution = material_resolution or catalog.get("material_resolution")
        evidence_assets = evidence_assets or catalog.get("evidence_assets")

    if evidence_index and not evidence_assets:
        evidence_assets = build_evidence_assets(_as_dict_list(evidence_index))

    fields: dict[str, Any] = {}
    if evidence_index:
        fields["evidence_index"] = evidence_index
    if evidence_assets:
        fields["evidence_assets"] = evidence_assets
    if material_resolution:
        fields["material_resolution"] = material_resolution
    return fields


def enrich_format_visuals_with_evidence_assets(
    formatted: dict[str, Any],
    input_data: dict[str, Any],
) -> dict[str, Any]:
    fields = evidence_runtime_fields(input_data)
    assets = _as_dict_list(fields.get("evidence_assets"))
    if not assets:
        return formatted

    formatted.setdefault("evidence_assets", assets)
    enriched: list[dict[str, Any]] = []
    for visual in formatted.get("visuals") or []:
        if not isinstance(visual, dict):
            continue
        if visual.get("type") != "chart" or _has_chart_data(visual.get("data")):
            continue
        asset = _match_chart_asset(visual, assets)
        chart_data = asset.get("chart_data") if asset else None
        if not isinstance(chart_data, dict) or not chart_data:
            continue
        visual["data"] = chart_data
        refs = [str(item) for item in visual.get("source_refs") or [] if str(item)]
        for ref in (asset.get("evidence_id"), asset.get("ref")):
            if ref and str(ref) not in refs:
                refs.append(str(ref))
        visual["source_refs"] = refs
        enriched.append(
            {
                "visual_title": visual.get("title", ""),
                "evidence_id": asset.get("evidence_id", ""),
                "asset_id": asset.get("asset_id", ""),
                "ref": asset.get("ref", ""),
            }
        )
    if enriched:
        formatted["evidence_asset_enrichment"] = enriched
    return formatted


def _chart_data_from_sidecar(
    sidecar: dict[str, Any],
    asset: dict[str, Any],
    *,
    max_points: int,
) -> dict[str, Any]:
    if not isinstance(sidecar, dict) or not sidecar:
        return {}
    orientation = str(asset.get("orientation") or "long")
    table = _table_for_asset(sidecar, asset)
    if not table:
        return {}
    if orientation == "wide":
        return _wide_chart_data(table, asset, max_points=max_points)
    return _long_chart_data(table, asset, max_points=max_points)


def _table_for_asset(sidecar: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    label = str(asset.get("label") or "")
    for table in sidecar.get("tables") or []:
        if not isinstance(table, dict):
            continue
        if not label or str(table.get("name") or "") == label:
            return {
                "name": table.get("name", ""),
                "columns": list(table.get("columns") or []),
                "rows": list(table.get("rows") or []),
                "row_format": "dict",
            }
    sheets = [sheet for sheet in sidecar.get("sheets") or [] if isinstance(sheet, dict)]
    if not sheets:
        return {}
    selected = next((sheet for sheet in sheets if str(sheet.get("name") or "") == label), sheets[0])
    rows = list(selected.get("rows") or [])
    header_index = _header_index(rows)
    if header_index is None:
        return {}
    columns = [str(item).strip() or f"列{i + 1}" for i, item in enumerate(rows[header_index])]
    return {
        "name": selected.get("name", ""),
        "columns": columns,
        "rows": rows[header_index + 1 :],
        "row_format": "list",
    }


def _wide_chart_data(
    table: dict[str, Any],
    asset: dict[str, Any],
    *,
    max_points: int,
) -> dict[str, Any]:
    columns = [str(item) for item in table.get("columns") or []]
    rows = list(table.get("rows") or [])
    if not columns or not rows:
        return {}
    label_column = str(asset.get("series_label_column") or columns[0])
    label_index = columns.index(label_column) if label_column in columns else 0
    date_indices = [
        index for index, column in enumerate(columns)
        if index != label_index and _looks_like_date_header(column)
    ]
    if len(date_indices) < 2:
        return {}
    categories = [columns[index] for index in date_indices]
    series = []
    for row in rows[:MAX_SERIES]:
        if isinstance(row, dict):
            label = str(row.get(label_column) or "")
            values = [_parse_number(row.get(columns[index], "")) for index in date_indices]
        else:
            row_values = list(row)
            label = str(row_values[label_index] if label_index < len(row_values) else "")
            values = [
                _parse_number(row_values[index] if index < len(row_values) else "")
                for index in date_indices
            ]
        if label and any(value is not None for value in values):
            series.append({"name": label, "values": values})
    if not series:
        return {}
    categories, series = _sample_chart(categories, series, max_points)
    return {
        "chart_type": "line",
        "orientation": "wide",
        "categories": categories,
        "series": series,
        "unit": asset.get("unit", ""),
        "source_table": table.get("name", ""),
        "sampling_note": _sampling_note(table, categories, asset),
    }


def _long_chart_data(
    table: dict[str, Any],
    asset: dict[str, Any],
    *,
    max_points: int,
) -> dict[str, Any]:
    columns = [str(item) for item in table.get("columns") or []]
    date_column = str(asset.get("date_column") or "")
    value_columns = [str(item) for item in asset.get("value_columns") or []]
    if not date_column or date_column not in columns or not value_columns:
        return {}
    rows = _dict_rows(table)
    categories: list[str] = []
    raw_series = {column: [] for column in value_columns[:MAX_SERIES] if column in columns}
    for row in rows:
        label = str(row.get(date_column) or "").strip()
        if not label:
            continue
        categories.append(label)
        for column in raw_series:
            raw_series[column].append(_parse_number(row.get(column, "")))
    series = [
        {"name": column, "values": values}
        for column, values in raw_series.items()
        if any(value is not None for value in values)
    ]
    if not categories or not series:
        return {}
    categories, series = _sample_chart(categories, series, max_points)
    data = {
        "chart_type": "line",
        "orientation": "long",
        "categories": categories,
        "series": series,
        "unit": asset.get("unit", ""),
        "source_table": table.get("name", ""),
        "sampling_note": _sampling_note(table, categories, asset),
    }
    if len(series) == 1:
        data["values"] = series[0]["values"]
    return data


def _dict_rows(table: dict[str, Any]) -> list[dict[str, Any]]:
    columns = [str(item) for item in table.get("columns") or []]
    rows = list(table.get("rows") or [])
    if table.get("row_format") == "dict":
        return [row for row in rows if isinstance(row, dict)]
    result = []
    unique_columns = _unique_columns(columns)
    for row in rows:
        if not isinstance(row, list):
            continue
        result.append(
            {
                unique_columns[index]: row[index] if index < len(row) else ""
                for index in range(len(unique_columns))
            }
        )
    return result


def _sample_chart(
    categories: list[str],
    series: list[dict[str, Any]],
    max_points: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    if len(categories) <= max_points:
        return categories, series
    if max_points < 2:
        max_points = 2
    indices = sorted(
        {
            round(index * (len(categories) - 1) / (max_points - 1))
            for index in range(max_points)
        }
    )
    sampled_categories = [categories[index] for index in indices]
    sampled_series = [
        {
            **row,
            "values": [
                (row.get("values") or [])[index]
                if index < len(row.get("values") or [])
                else None
                for index in indices
            ],
        }
        for row in series
    ]
    return sampled_categories, sampled_series


def _sampling_note(table: dict[str, Any], categories: list[str], asset: dict[str, Any]) -> str:
    total = int(asset.get("date_columns_count") or table.get("row_count") or len(categories))
    if total > len(categories):
        return f"图表预览从 {total} 个点等距抽样为 {len(categories)} 个点；完整数据见 parsed_artifact_path。"
    return ""


def _match_chart_asset(
    visual: dict[str, Any],
    assets: list[dict[str, Any]],
) -> dict[str, Any]:
    refs = {str(item) for item in visual.get("source_refs") or []}
    chart_assets = [asset for asset in assets if asset.get("chart_ready")]
    for asset in chart_assets:
        keys = {
            str(asset.get("evidence_id") or ""),
            str(asset.get("asset_id") or ""),
            str(asset.get("ref") or ""),
        }
        if refs & {key for key in keys if key}:
            return asset
    title = str(visual.get("title") or "")
    for asset in chart_assets:
        label = str(asset.get("label") or "")
        if label and (label in title or title in label):
            return asset
    return chart_assets[0] if chart_assets else {}


def _has_chart_data(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    categories = data.get("categories")
    if not isinstance(categories, list) or not categories:
        return False
    series = data.get("series")
    if isinstance(series, list) and series:
        return True
    values = data.get("values")
    return isinstance(values, list) and bool(values)


def _first_non_empty(key: str, payloads: Iterable[Any]) -> Any:
    for payload in payloads:
        found = _find_key(payload, key)
        if found not in (None, "", [], {}):
            return found
    return None


def _find_key(value: Any, key: str, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if isinstance(value, dict):
        if value.get(key) not in (None, "", [], {}):
            return value[key]
        for nested_key in ("evidence_catalog", "analysis", "storyline", "report", "inputs", "inline_fields"):
            nested = value.get(nested_key)
            found = _find_key(nested, key, depth + 1)
            if found not in (None, "", [], {}):
                return found
        for nested in value.values():
            if isinstance(nested, dict):
                found = _find_key(nested, key, depth + 1)
                if found not in (None, "", [], {}):
                    return found
    elif isinstance(value, list):
        for item in value[:20]:
            found = _find_key(item, key, depth + 1)
            if found not in (None, "", [], {}):
                return found
    return None


def _header_index(rows: list[Any]) -> int | None:
    for index, row in enumerate(rows):
        if isinstance(row, list) and any(str(value).strip() for value in row):
            return index
    return None


def _unique_columns(columns: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    result = []
    for index, raw in enumerate(columns):
        name = str(raw or f"列{index + 1}")
        count = counts.get(name, 0) + 1
        counts[name] = count
        result.append(name if count == 1 else f"{name}#{count}")
    return result


def _parse_number(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "").replace("，", "")
    multiplier = 0.01 if text.endswith("%") else 1.0
    text = text.rstrip("%")
    text = re.sub(r"^[^\d.+-]+", "", text)
    text = re.sub(r"[^\d.+-]+$", "", text)
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return None
    try:
        number = float(text) * multiplier
    except ValueError:
        return None
    if negative:
        number = -number
    if math.isfinite(number):
        return round(number, 4)
    return None


def _looks_like_date_header(value: str) -> bool:
    text = str(value or "").strip()
    return bool(
        re.fullmatch(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", text)
        or re.fullmatch(r"\d{4}[-/.年]\d{1,2}月?", text)
    )


def _asset_ref(evidence_id: str, asset_id: str) -> str:
    if evidence_id and asset_id:
        return f"{evidence_id}:{asset_id}"
    return evidence_id or asset_id


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
