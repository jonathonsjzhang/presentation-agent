from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any


MAX_COLUMNS_PROFILED = 80
MAX_EXAMPLES = 3
MAX_FINDINGS = 12


def profile_csv_table(
    *,
    name: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a neutral, compact profile for a CSV-like table."""

    table = _profile_table(
        name=name,
        columns=columns,
        rows=[[row.get(column, "") for column in columns] for row in rows],
    )
    return _profile_from_tables([table])


def profile_xlsx_sheets(sheets: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a neutral, compact profile for workbook sheets."""

    tables = []
    for sheet in sheets:
        rows = sheet.get("rows", [])
        if not isinstance(rows, list):
            continue
        header_index = _header_index(rows)
        if header_index is None:
            tables.append(
                {
                    "asset_id": _asset_id(sheet.get("name") or "sheet", len(tables) + 1),
                    "name": str(sheet.get("name") or f"sheet-{len(tables) + 1}"),
                    "row_count": 0,
                    "column_count": 0,
                    "columns": [],
                    "summary": "未识别到非空表头或有效数据行。",
                    "key_findings": [],
                    "time_series_candidates": [],
                }
            )
            continue
        columns = [str(item).strip() or f"列{i + 1}" for i, item in enumerate(rows[header_index])]
        data_rows = rows[header_index + 1 :]
        sequence = len(tables) + 1
        tables.append(
            _profile_table(
                name=str(sheet.get("name") or f"sheet-{sequence}"),
                columns=columns,
                rows=data_rows,
                sequence=sequence,
            )
        )
    return _profile_from_tables(tables)


def data_assets_from_profile(profile: dict[str, Any]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for table in profile.get("tables", []):
        if not isinstance(table, dict):
            continue
        asset = {
            "asset_id": table.get("asset_id", ""),
            "kind": "table",
            "label": table.get("name", ""),
            "row_count": table.get("row_count", 0),
            "column_count": table.get("column_count", 0),
            "suggested_uses": ["table_lookup"],
            "chart_ready": False,
        }
        candidates = table.get("time_series_candidates") or []
        if candidates:
            first = candidates[0]
            asset["chart_ready"] = True
            asset["suggested_uses"] = ["trend_chart", "metric_comparison", "table_lookup"]
            asset["orientation"] = first.get("orientation", "long")
            if first.get("orientation") == "wide":
                asset["series_label_column"] = first.get("series_label_column", "")
                asset["date_columns_count"] = first.get("date_columns_count", 0)
                asset["date_range"] = first.get("date_range", {})
                asset["value_columns"] = []
            else:
                asset["date_column"] = first.get("date_column", "")
                asset["value_columns"] = first.get("value_columns", [])
        assets.append(asset)
    return assets


def _profile_from_tables(tables: list[dict[str, Any]]) -> dict[str, Any]:
    key_findings: list[str] = []
    for table in tables:
        key_findings.extend(table.get("key_findings", []))
    key_findings = key_findings[:MAX_FINDINGS]
    return {
        "summary": _profile_summary(tables),
        "tables": tables,
        "key_findings": key_findings,
        "data_assets": data_assets_from_profile({"tables": tables}),
    }


def _profile_table(
    *,
    name: str,
    columns: list[str],
    rows: list[list[Any]],
    sequence: int = 1,
) -> dict[str, Any]:
    row_count = len(rows)
    column_count = len(columns)
    column_profiles = [
        _profile_column(column, [row[index] if index < len(row) else "" for row in rows])
        for index, column in enumerate(columns[:MAX_COLUMNS_PROFILED])
    ]
    wide_candidate, wide_findings = _wide_time_series(name, columns, rows)
    time_candidates = wide_candidate or _time_series_candidates(column_profiles)
    findings = wide_findings or _numeric_findings(name, column_profiles)
    table = {
        "asset_id": _asset_id(name, sequence),
        "name": name,
        "row_count": row_count,
        "column_count": column_count,
        "profiled_column_count": len(column_profiles),
        "columns": column_profiles,
        "summary": _table_summary(name, row_count, column_count, findings, time_candidates),
        "key_findings": findings,
        "time_series_candidates": time_candidates,
    }
    if column_count > MAX_COLUMNS_PROFILED:
        table["profile_note"] = f"列数较多，仅 profile 前 {MAX_COLUMNS_PROFILED} 列。"
    return table


def _profile_column(name: str, values: list[Any]) -> dict[str, Any]:
    cleaned = [_clean(value) for value in values]
    non_empty = [value for value in cleaned if value != ""]
    numeric_values = [_parse_number(value) for value in non_empty]
    numeric_values = [value for value in numeric_values if value is not None]
    date_like = sum(1 for value in non_empty if _looks_like_date(value))
    inferred = _infer_type(non_empty, numeric_values, date_like)
    profile: dict[str, Any] = {
        "name": name,
        "inferred_type": inferred,
        "non_empty_count": len(non_empty),
        "empty_count": len(values) - len(non_empty),
        "examples": _examples(non_empty),
    }
    if numeric_values:
        first = _first_number(non_empty)
        last = _last_number(non_empty)
        profile.update(
            {
                "min": _round(min(numeric_values)),
                "max": _round(max(numeric_values)),
                "first": _round(first),
                "last": _round(last),
            }
        )
        if first is not None and last is not None:
            delta = last - first
            profile["delta"] = _round(delta)
            if first:
                profile["growth_pct"] = _round(delta / abs(first))
    else:
        profile["distinct_count"] = len(set(non_empty[:1000]))
    return profile


def _numeric_findings(name: str, columns: list[dict[str, Any]]) -> list[str]:
    findings = []
    for column in columns:
        if column.get("inferred_type") != "numeric":
            continue
        first = column.get("first")
        last = column.get("last")
        if first is None or last is None:
            continue
        delta = column.get("delta")
        growth = column.get("growth_pct")
        if delta in (None, 0) and growth in (None, 0):
            continue
        growth_text = f"，变化 {growth:.1%}" if isinstance(growth, (int, float)) else ""
        findings.append(
            f"{name}：{column.get('name')} 从 {_fmt_number(first)} 到 {_fmt_number(last)}"
            f"（差值 {_fmt_number(delta)}{growth_text}）。"
        )
        if len(findings) >= MAX_FINDINGS:
            break
    return findings


def _time_series_candidates(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    date_columns = [
        column
        for column in columns
        if column.get("inferred_type") == "date"
        or any(token in str(column.get("name", "")).lower() for token in ("date", "day", "month", "week", "日期", "时间", "月份", "周"))
    ]
    numeric_columns = [
        str(column.get("name"))
        for column in columns
        if column.get("inferred_type") == "numeric"
    ]
    if not date_columns or not numeric_columns:
        return []
    return [
        {
            "orientation": "long",
            "date_column": str(date_columns[0].get("name")),
            "value_columns": numeric_columns[:20],
            "recommended_visual": "line_chart",
            "reason": "包含日期/时间列和多个数值列，可用于趋势或竞品对比折线图。",
        }
    ]


def _wide_time_series(
    name: str,
    columns: list[str],
    rows: list[list[Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    if len(columns) < 4 or not rows:
        return [], []
    date_indices = [
        index
        for index, column in enumerate(columns)
        if index > 0 and _looks_like_date_header(str(column))
    ]
    if len(date_indices) < 3:
        return [], []
    label_index = 0
    first_date = date_indices[0]
    last_date = date_indices[-1]
    findings: list[str] = []
    for row in rows:
        if label_index >= len(row):
            continue
        label = _clean(row[label_index])
        if not label:
            continue
        first = _parse_number(_clean(row[first_date] if first_date < len(row) else ""))
        last = _parse_number(_clean(row[last_date] if last_date < len(row) else ""))
        if first is None or last is None:
            continue
        delta = last - first
        growth = delta / abs(first) if first else None
        growth_text = f"，变化 {growth:.1%}" if growth is not None else ""
        findings.append(
            f"{name}：{label} 从 {columns[first_date]} 的 {_fmt_number(first)} "
            f"到 {columns[last_date]} 的 {_fmt_number(last)}"
            f"（差值 {_fmt_number(delta)}{growth_text}）。"
        )
        if len(findings) >= MAX_FINDINGS:
            break
    return [
        {
            "orientation": "wide",
            "series_label_column": str(columns[label_index]),
            "date_columns_count": len(date_indices),
            "date_range": {
                "start": str(columns[first_date]),
                "end": str(columns[last_date]),
            },
            "recommended_visual": "line_chart",
            "reason": "列头为连续日期、每行是一个序列，可转成长表后绘制多序列折线图。",
        }
    ], findings


def _profile_summary(tables: list[dict[str, Any]]) -> str:
    if not tables:
        return "未识别到可 profile 的表格。"
    total_rows = sum(int(table.get("row_count", 0)) for table in tables)
    total_columns = sum(int(table.get("column_count", 0)) for table in tables)
    chart_ready = sum(1 for table in tables if table.get("time_series_candidates"))
    return (
        f"共识别 {len(tables)} 个表/工作表，合计 {total_rows} 行、{total_columns} 列；"
        f"其中 {chart_ready} 个具备时间序列/趋势图候选。"
    )


def _table_summary(
    name: str,
    row_count: int,
    column_count: int,
    findings: list[str],
    time_candidates: list[dict[str, Any]],
) -> str:
    chart_text = "；可作为趋势图数据源" if time_candidates else ""
    finding_text = f"；关键数值变化：{findings[0]}" if findings else ""
    return f"{name}：{row_count} 行、{column_count} 列{chart_text}{finding_text}"


def _header_index(rows: list[Any]) -> int | None:
    for index, row in enumerate(rows):
        if isinstance(row, list) and any(_clean(value) for value in row):
            return index
    return None


def _infer_type(
    non_empty: list[str],
    numeric_values: list[float],
    date_like_count: int,
) -> str:
    if not non_empty:
        return "empty"
    if date_like_count >= max(1, math.ceil(len(non_empty) * 0.6)):
        return "date"
    if len(numeric_values) >= max(1, math.ceil(len(non_empty) * 0.8)):
        return "numeric"
    return "text"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _parse_number(value: str) -> float | None:
    text = _clean(value)
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
    return -number if negative else number


def _looks_like_date(value: str) -> bool:
    text = _clean(value)
    if not text:
        return False
    if re.fullmatch(r"\d{4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?", text):
        return True
    if re.fullmatch(r"\d{1,2}[-/]\d{1,2}", text):
        return True
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    return False


def _looks_like_date_header(value: str) -> bool:
    text = _clean(value)
    if re.fullmatch(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", text):
        return True
    if re.fullmatch(r"\d{4}[-/.年]\d{1,2}月?", text):
        return True
    return False


def _first_number(values: list[str]) -> float | None:
    for value in values:
        parsed = _parse_number(value)
        if parsed is not None:
            return parsed
    return None


def _last_number(values: list[str]) -> float | None:
    for value in reversed(values):
        parsed = _parse_number(value)
        if parsed is not None:
            return parsed
    return None


def _examples(values: list[str]) -> list[str]:
    examples: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        examples.append(value)
        if len(examples) >= MAX_EXAMPLES:
            break
    return examples


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    if abs(value) >= 100:
        return round(value, 2)
    return round(value, 4)


def _fmt_number(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return str(value)
    if abs(value) >= 100:
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _asset_id(name: str, sequence: int) -> str:
    stem = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", str(name)).strip("-")
    return f"T{sequence}-{stem[:36] or 'table'}"
