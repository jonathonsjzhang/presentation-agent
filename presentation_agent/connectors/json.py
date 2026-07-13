from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from presentation_agent.connectors.base import ConnectorContext, SuffixConnector
from presentation_agent.connectors.csv import rows_to_materials
from presentation_agent.connectors.table_profiler import (
    data_assets_from_profile,
    profile_csv_table,
)


class JsonConnector(SuffixConnector):
    """Read JSON while preserving structure and profiling tabular arrays."""

    name = "json_reader"
    suffixes = (".json",)

    def load(self, path: Path, context: ConnectorContext) -> dict[str, Any]:
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)

        result: dict[str, Any] = {
            "topic": path.stem,
            "source_path": str(path),
            "source_type": "json",
            "target_agent": context.agent_id,
            "json_data": payload,
            "raw_text": json.dumps(payload, ensure_ascii=False, indent=2),
            "source_units": _json_source_units(path, payload),
        }
        rows = _tabular_rows(payload)
        if rows:
            columns = _ordered_columns(rows)
            profile = profile_csv_table(name=path.stem, columns=columns, rows=rows)
            result.update(
                {
                    "data_profile": profile,
                    "data_assets": data_assets_from_profile(profile),
                    "tables": [
                        {
                            "name": path.stem,
                            "columns": columns,
                            "rows": rows,
                            "row_count": len(rows),
                        }
                    ],
                    "materials": rows_to_materials(rows, columns),
                }
            )
        return result


def _tabular_rows(payload: Any) -> list[dict[str, Any]]:
    candidate = payload
    if isinstance(payload, dict):
        candidate = payload.get("rows") or payload.get("data") or payload.get("records")
    if not isinstance(candidate, list) or not candidate:
        return []
    if not all(isinstance(item, dict) for item in candidate):
        return []
    return [dict(item) for item in candidate]


def _ordered_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            name = str(key)
            if name not in columns:
                columns.append(name)
    return columns


def _json_source_units(path: Path, payload: Any) -> list[dict[str, Any]]:
    source_id = path.stem.upper().replace(" ", "-")[:40] or "JSON"
    values: list[tuple[str, Any]]
    rows = _tabular_rows(payload)
    if rows:
        prefix = "/" if isinstance(payload, list) else "/rows/"
        values = [(f"{prefix}{index}", value) for index, value in enumerate(rows)]
    elif isinstance(payload, list):
        values = [(f"/{index}", value) for index, value in enumerate(payload)]
    elif isinstance(payload, dict):
        values = [(f"/{key}", value) for key, value in payload.items()]
    else:
        values = [("/", payload)]
    return [
        {
            "source_unit_id": f"{source_id}-J{index:04d}",
            "source_id": source_id,
            "source_location": pointer,
            "modality": "table" if isinstance(value, (dict, list)) else "text",
            "raw_content": json.dumps(value, ensure_ascii=False, default=str),
            "inspection_status": "inspected",
        }
        for index, (pointer, value) in enumerate(values, start=1)
    ]
