from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from presentation_agent.connectors.base import ConnectorContext, SuffixConnector


class CsvConnector(SuffixConnector):
    name = "csv_reader"
    suffixes = (".csv",)

    def load(self, path: Path, context: ConnectorContext) -> dict[str, Any]:
        encodings = ("utf-8-sig", "utf-8", "gb2312", "gbk", "latin-1")
        last_error: Exception | None = None
        for enc in encodings:
            try:
                with path.open("r", encoding=enc, newline="") as f:
                    raw_sample = f.read(4096)
                    # Skip blank lines for Sniffer — survey exports often
                    # have empty rows between header blocks
                    sample = "\n".join(
                        line for line in raw_sample.splitlines() if line.strip()
                    )
                    f.seek(0)
                    try:
                        dialect = (
                            csv.Sniffer().sniff(sample) if sample.strip()
                            else csv.excel
                        )
                    except csv.Error:
                        dialect = csv.excel
                    reader = csv.DictReader(f, dialect=dialect)
                    rows: list[dict[str, str]] = []
                    for row in reader:
                        try:
                            cleaned = {
                                k: v for k, v in row.items() if k is not None
                            }
                            if cleaned:
                                rows.append(cleaned)
                        except (csv.Error, ValueError):
                            # Row with field-count mismatch (survey artifact) — skip
                            continue
                    columns = list(reader.fieldnames or [])
                break
            except (UnicodeDecodeError, UnicodeError) as exc:
                last_error = exc
                continue
        else:
            raise IOError(
                f"无法以任何已知编码读取 {path}: {last_error}"
            )

        return {
            "topic": path.stem,
            "source_path": str(path),
            "source_type": "csv",
            "target_agent": context.agent_id,
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


def rows_to_materials(rows: list[dict[str, str]], columns: list[str]) -> list[dict[str, Any]]:
    if not rows:
        return []

    lower_to_column = {column.lower(): column for column in columns}
    claim_key = first_present(lower_to_column, ("claim", "title", "判断", "结论", "主题"))
    evidence_key = first_present(lower_to_column, ("evidence", "证据", "论据", "source", "来源"))
    so_what_key = first_present(lower_to_column, ("so_what", "sowhat", "含义", "action", "建议"))

    materials: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        claim = clean(row.get(claim_key, "")) if claim_key else ""
        evidence = clean(row.get(evidence_key, "")) if evidence_key else ""
        so_what = clean(row.get(so_what_key, "")) if so_what_key else ""
        if not claim:
            claim = summarize_row(row, index)
        materials.append(
            {
                "claim": claim,
                "key_question": "这条数据说明了什么关键判断？",
                "evidence": [evidence] if evidence else [summarize_row(row, index)],
                "so_what": so_what or "需要结合汇报目标提炼管理层含义。",
                "tag": "mainline",
                "source_row": index,
            }
        )
    return materials


def first_present(columns: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate.lower() in columns:
            return columns[candidate.lower()]
    return None


def clean(value: Any) -> str:
    return str(value or "").strip()


def summarize_row(row: dict[str, str], index: int) -> str:
    parts = [f"{key}={value}" for key, value in row.items() if clean(value)]
    return f"第 {index} 行数据：" + "；".join(parts[:5])
