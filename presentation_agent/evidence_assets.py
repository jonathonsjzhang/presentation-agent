from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Iterable

from presentation_agent.io import read_json


MAX_CHART_POINTS = 60
MAX_SERIES = 6
MAX_TABLE_ROWS = 12
MAX_TABLE_COLUMNS = 8
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


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
            table_data = _table_data_from_sidecar(sidecar, data_asset)
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
                    "table_data": table_data,
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
    evidence_index = _as_dict_list(fields.get("evidence_index"))
    assets = _as_dict_list(fields.get("evidence_assets"))
    if evidence_index:
        # Older catalogs may carry evidence_assets created before table
        # projections were introduced. Rebuild from the immutable sidecar refs
        # and merge the deterministic projections into the carried metadata.
        assets = _merge_asset_projections(assets, build_evidence_assets(evidence_index))
    if not assets and not evidence_index:
        return formatted

    if assets:
        formatted["evidence_assets"] = assets
    enriched: list[dict[str, Any]] = []
    for visual in formatted.get("visuals") or []:
        if not isinstance(visual, dict):
            continue
        visual_type = str(visual.get("type") or "")
        data = visual.get("data")
        if visual_type == "chart" and (
            _has_chart_data(data) or _has_source_image(data)
        ):
            continue
        if visual_type == "table" and _has_table_data(data):
            continue

        asset = _match_evidence_asset(visual, assets)
        chart_data = asset.get("chart_data") if asset else None
        table_data = asset.get("table_data") if asset else None
        enrichment_kind = ""
        if visual_type == "chart" and isinstance(chart_data, dict) and chart_data:
            visual["data"] = chart_data
            enrichment_kind = "chart_data"
        elif visual_type in {"chart", "table"} and _has_table_data(table_data):
            # A referenced workbook table is still valid renderable evidence
            # when its layout is too irregular for deterministic chart
            # inference. Preserve the data as a bounded table instead of
            # inventing a chart or returning an empty visual.
            visual["type"] = "table"
            visual["data"] = table_data
            visual["runtime_projection"] = {
                "from": visual_type,
                "to": "table",
                "reason": (
                    "referenced evidence table is not safely chart-ready"
                    if visual_type == "chart"
                    else "bounded referenced evidence table for deterministic rendering"
                ),
            }
            enrichment_kind = "table_fallback"
        else:
            image_path = _match_source_image(visual, evidence_index)
            if image_path:
                visual["data"] = {"image_path": image_path}
                enrichment_kind = "source_image"

        if not enrichment_kind:
            continue
        refs = [str(item) for item in visual.get("source_refs") or [] if str(item)]
        for ref in (
            asset.get("evidence_id") if asset else "",
            asset.get("ref") if asset else "",
        ):
            if ref and str(ref) not in refs:
                refs.append(str(ref))
        visual["source_refs"] = refs
        enriched.append(
            {
                "visual_title": visual.get("title", ""),
                "kind": enrichment_kind,
                "evidence_id": asset.get("evidence_id", "") if asset else "",
                "asset_id": asset.get("asset_id", "") if asset else "",
                "ref": asset.get("ref", "") if asset else "",
            }
        )
    if enriched:
        formatted["evidence_asset_enrichment"] = enriched
    return formatted


def _merge_asset_projections(
    carried: list[dict[str, Any]], rebuilt: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rebuilt_by_ref = {
        str(item.get("ref") or ""): item
        for item in rebuilt
        if isinstance(item, dict) and item.get("ref")
    }
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in carried:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "")
        fresh = rebuilt_by_ref.get(ref, {})
        merged.append({**item, **{k: v for k, v in fresh.items() if v not in (None, "", [], {})}})
        if ref:
            seen.add(ref)
    merged.extend(item for item in rebuilt if str(item.get("ref") or "") not in seen)
    return merged


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


def _table_data_from_sidecar(
    sidecar: dict[str, Any], asset: dict[str, Any]
) -> dict[str, Any]:
    table = _table_for_asset(sidecar, asset)
    columns = [str(item) for item in table.get("columns") or []]
    if not columns:
        return {}
    rows = list(table.get("rows") or [])
    row_lists: list[list[Any]] = []
    if table.get("row_format") == "dict":
        row_lists = [
            [row.get(column, "") for column in columns]
            for row in rows
            if isinstance(row, dict)
        ]
    else:
        row_lists = [list(row) for row in rows if isinstance(row, list)]

    useful_indices = [
        index
        for index, column in enumerate(columns)
        if str(column).strip()
        or any(index < len(row) and str(row[index]).strip() for row in row_lists)
    ][:MAX_TABLE_COLUMNS]
    if not useful_indices:
        return {}
    selected_columns = _unique_columns(
        [columns[index] or f"列{index + 1}" for index in useful_indices]
    )
    selected_rows = []
    for row in row_lists:
        values = [row[index] if index < len(row) else "" for index in useful_indices]
        if not any(str(value).strip() for value in values):
            continue
        selected_rows.append(values)
        if len(selected_rows) >= MAX_TABLE_ROWS:
            break
    if not selected_rows:
        return {}
    return {
        "columns": selected_columns,
        "rows": selected_rows,
        "source_table": table.get("name", ""),
        "projection_note": (
            f"runtime bounded projection: first {len(selected_rows)} rows × "
            f"{len(selected_columns)} non-empty columns"
        ),
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


def _match_evidence_asset(
    visual: dict[str, Any],
    assets: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_refs = [str(item) for item in visual.get("source_refs") or [] if str(item)]
    # A compound ref identifies one exact table. Respect the worker's source
    # order when more than one supporting table is present.
    for ref in ordered_refs:
        if ":" not in ref:
            continue
        for asset in assets:
            if ref in {
                str(asset.get("ref") or ""),
                str(asset.get("asset_id") or ""),
            }:
                return asset
    refs = {
        alias
        for item in ordered_refs
        for alias in _ref_aliases(str(item))
    }
    for asset in assets:
        keys = {
            alias
            for value in (
                asset.get("evidence_id"),
                asset.get("asset_id"),
                asset.get("ref"),
            )
            for alias in _ref_aliases(str(value or ""))
        }
        if refs & {key for key in keys if key}:
            return asset
    title = str(visual.get("title") or "")
    for asset in assets:
        label = str(asset.get("label") or "")
        if label and (label in title or title in label):
            return asset
    return {}


def _match_source_image(
    visual: dict[str, Any], evidence_index: list[dict[str, Any]]
) -> str:
    refs = {
        alias
        for item in visual.get("source_refs") or []
        for alias in _ref_aliases(str(item))
    }
    for record in evidence_index:
        evidence_id = str(record.get("id") or "")
        if not refs.intersection(_ref_aliases(evidence_id)):
            continue
        source_refs = record.get("source_refs") or {}
        source_path = Path(str(source_refs.get("source_path") or ""))
        if source_path.suffix.lower() in IMAGE_SUFFIXES and source_path.is_file():
            return str(source_path)
    return ""


def _ref_aliases(value: str) -> set[str]:
    value = value.strip()
    if not value:
        return set()
    aliases = {value}
    if value.startswith("EV-"):
        aliases.add(value[3:])
    return aliases


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


def _has_table_data(data: Any) -> bool:
    return (
        isinstance(data, dict)
        and bool(data.get("columns") or data.get("headers"))
        and bool(data.get("rows"))
    )


def _has_source_image(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    path = Path(str(data.get("image_path") or ""))
    return path.suffix.lower() in IMAGE_SUFFIXES and path.is_file()


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
