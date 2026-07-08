from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from presentation_agent.connectors.registry import load_with_connector
from presentation_agent.io import write_json
from presentation_agent.models import AgentSpec


PATH_KEYS = ("path", "source_path", "file_path", "filepath", "artifact_path")
SUPPORTED_SUFFIXES = {
    ".csv",
    ".doc",
    ".docx",
    ".jpg",
    ".jpeg",
    ".pdf",
    ".png",
    ".xlsx",
}
TABLE_SOURCE_TYPES = {"csv", "xlsx"}
INLINE_SOURCE_UNIT_LIMIT = 80
INLINE_SOURCE_UNIT_HEAD = 40
INLINE_SOURCE_UNIT_TAIL = 10


def resolve_raw_materials(
    raw_materials: list[Any],
    *,
    spec: AgentSpec,
    base_dirs: Iterable[Path],
    artifact_dir: Path | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    """Resolve path-bearing material entries into connector source units.

    Manager briefs often carry JSON material entries such as
    ``{"path": "./data.xlsx", "description": "..."}``.  The Evidence worker
    needs the parsed file contents, not just the path and description.  This
    resolver is intentionally deterministic: it expands nested file/directory
    paths before the LLM Evidence Harvester runs.
    """

    resolved: list[Any] = []
    summary = {
        "total_input_materials": len(raw_materials),
        "parsed_files": 0,
        "parsed_directories": 0,
        "inline_materials": 0,
        "unresolved_materials": 0,
        "unresolved": [],
    }
    artifact_dir = artifact_dir.resolve() if artifact_dir else None
    if artifact_dir:
        artifact_dir.mkdir(parents=True, exist_ok=True)

    bases = _unique_dirs(base_dirs)
    for index, material in enumerate(raw_materials, start=1):
        path_value = _material_path(material)
        if not path_value:
            resolved.append(material)
            summary["inline_materials"] += 1
            continue

        path = _resolve_path(path_value, bases)
        if path is None:
            resolved.append(_unresolved_material(material, path_value, "path_not_found"))
            summary["unresolved_materials"] += 1
            summary["unresolved"].append({"path": path_value, "reason": "path_not_found"})
            continue

        if path.is_dir():
            directory_records = _resolve_directory(
                path,
                material,
                spec=spec,
                artifact_dir=artifact_dir,
                sequence_prefix=f"{index}",
            )
            resolved.extend(directory_records["materials"])
            summary["parsed_directories"] += 1
            summary["parsed_files"] += directory_records["parsed_files"]
            summary["unresolved_materials"] += directory_records["unresolved_materials"]
            summary["unresolved"].extend(directory_records["unresolved"])
            continue

        parsed = _load_material_file(
            path,
            material,
            spec=spec,
            artifact_dir=artifact_dir,
            sequence=f"{index}",
        )
        resolved.append(parsed)
        if parsed.get("parse_status") == "parsed":
            summary["parsed_files"] += 1
        else:
            summary["unresolved_materials"] += 1
            summary["unresolved"].append(
                {
                    "path": str(path),
                    "reason": parsed.get("parse_error") or parsed.get("parse_status"),
                }
            )

    evidence_index = attach_evidence_records(resolved)
    summary["evidence_count"] = len(evidence_index)
    summary["complete"] = summary["unresolved_materials"] == 0
    return resolved, summary


def evidence_index_from_materials(materials: list[Any]) -> list[dict[str, Any]]:
    return [
        material["evidence_record"]
        for material in materials
        if isinstance(material, dict) and isinstance(material.get("evidence_record"), dict)
    ]


def attach_evidence_records(materials: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, material in enumerate(
        [item for item in materials if isinstance(item, dict)], start=1
    ):
        evidence_id = f"E{index}"
        material["evidence_id"] = evidence_id
        material["evidence_record"] = _evidence_record(evidence_id, material)
        records.append(material["evidence_record"])
    return records


def _resolve_directory(
    path: Path,
    original: Any,
    *,
    spec: AgentSpec,
    artifact_dir: Path | None,
    sequence_prefix: str,
) -> dict[str, Any]:
    materials: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    parsed_files = 0
    unresolved_materials = 0
    files = [
        item
        for item in sorted(path.rglob("*"))
        if item.is_file()
        and not any(part.startswith(".") for part in item.relative_to(path).parts)
        and item.suffix.lower() in SUPPORTED_SUFFIXES
    ]
    for file_index, file_path in enumerate(files, start=1):
        parsed = _load_material_file(
            file_path,
            original,
            spec=spec,
            artifact_dir=artifact_dir,
            sequence=f"{sequence_prefix}-{file_index}",
            directory_root=path,
        )
        materials.append(parsed)
        if parsed.get("parse_status") == "parsed":
            parsed_files += 1
        else:
            unresolved_materials += 1
            unresolved.append(
                {
                    "path": str(file_path),
                    "reason": parsed.get("parse_error") or parsed.get("parse_status", "error"),
                }
            )
    if not files:
        unresolved_materials += 1
        unresolved.append({"path": str(path), "reason": "no_supported_files"})
        materials.append(_unresolved_material(original, str(path), "no_supported_files"))
    return {
        "materials": materials,
        "parsed_files": parsed_files,
        "unresolved_materials": unresolved_materials,
        "unresolved": unresolved,
    }


def _load_material_file(
    path: Path,
    original: Any,
    *,
    spec: AgentSpec,
    artifact_dir: Path | None,
    sequence: str,
    directory_root: Path | None = None,
) -> dict[str, Any]:
    base = dict(original) if isinstance(original, dict) else {"material": original}
    try:
        loaded = load_with_connector(path, spec)
    except Exception as exc:  # pragma: no cover - exact connector failures vary by file
        return _unresolved_material(base, str(path), f"connector_error: {exc}")

    material_id = str(
        base.get("material_id")
        or base.get("name")
        or base.get("id")
        or path.stem
    )
    if directory_root is not None:
        material_id = f"{material_id}/{path.relative_to(directory_root)}"

    source_type = loaded.get("source_type") or path.suffix.lower().lstrip(".")
    parsed_artifact_path = ""
    if artifact_dir:
        artifact_path = artifact_dir / f"{_safe_name(sequence + '-' + path.stem)}.json"
        write_json(artifact_path, loaded)
        parsed_artifact_path = str(artifact_path)

    source_units = loaded.get("source_units", [])
    source_units_inline, omitted_units = _source_units_for_prompt(source_units, source_type)
    source_unit_summary = dict(loaded.get("source_unit_summary", {}))
    if isinstance(source_units, list):
        source_unit_summary.setdefault("total", len(source_units))
        source_unit_summary["inlined"] = len(source_units_inline)
        if omitted_units:
            source_unit_summary["omitted_from_prompt"] = omitted_units

    parsed = {
        **base,
        "material_id": material_id,
        "source_path": str(path),
        "source_name": path.name,
        "source_type": source_type,
        "parse_status": "parsed",
        "description_hint": base.get("description") or base.get("notes") or "",
        "source_units": source_units_inline,
        "source_unit_summary": source_unit_summary,
    }
    if parsed_artifact_path:
        parsed["parsed_artifact_path"] = parsed_artifact_path
        parsed["raw_access"] = {
            "parsed_artifact_path": parsed_artifact_path,
            "fields": _raw_access_fields(loaded),
        }
    if omitted_units:
        parsed["source_units_omitted"] = omitted_units
        parsed["source_units_access"] = {
            "parsed_artifact_path": parsed_artifact_path,
            "field": "source_units",
        }
    for key in (
        "converted_docx_path",
        "conversion_note",
        "data_assets",
        "data_profile",
        "images",
        "images_note",
        "materials",
        "paragraphs",
        "raw_text",
        "sheets",
        "tables",
        "topic",
    ):
        if key in loaded:
            if source_type in TABLE_SOURCE_TYPES and key in {"sheets", "tables"}:
                parsed.setdefault("table_data_access", {
                    "parsed_artifact_path": parsed_artifact_path,
                    "fields": [key],
                })
                continue
            if source_type in TABLE_SOURCE_TYPES and key == "materials":
                continue
            parsed[key] = loaded[key]
    return parsed


def _material_path(material: Any) -> str:
    if isinstance(material, (str, Path)):
        return str(material)
    if not isinstance(material, dict):
        return ""
    for key in PATH_KEYS:
        value = material.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _resolve_path(raw_path: str, base_dirs: list[Path]) -> Path | None:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve() if candidate.exists() else None
    for base in base_dirs:
        full = (base / candidate).resolve()
        if full.exists():
            return full
    return None


def _unique_dirs(base_dirs: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for raw in base_dirs:
        if raw is None:
            continue
        path = Path(raw).expanduser()
        if path.is_file():
            path = path.parent
        try:
            resolved = path.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def _unresolved_material(original: Any, path: str, reason: str) -> dict[str, Any]:
    base = dict(original) if isinstance(original, dict) else {"material": original}
    return {
        **base,
        "path": path,
        "parse_status": "unresolved",
        "parse_error": reason,
        "source_units": [],
        "source_unit_summary": {"total": 0, "unresolved": 1},
    }


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")[:120] or "material"


def _source_units_for_prompt(
    source_units: Any,
    source_type: str,
) -> tuple[list[Any], int]:
    if not isinstance(source_units, list):
        return [], 0
    if source_type not in TABLE_SOURCE_TYPES or len(source_units) <= INLINE_SOURCE_UNIT_LIMIT:
        return source_units, 0
    inline = source_units[:INLINE_SOURCE_UNIT_HEAD] + source_units[-INLINE_SOURCE_UNIT_TAIL:]
    return inline, len(source_units) - len(inline)


def _raw_access_fields(loaded: dict[str, Any]) -> list[str]:
    fields = []
    for key in (
        "source_units",
        "tables",
        "sheets",
        "paragraphs",
        "raw_text",
        "images",
        "data_profile",
        "data_assets",
        "materials",
    ):
        if key in loaded:
            fields.append(key)
    return fields


def _evidence_record(evidence_id: str, material: dict[str, Any]) -> dict[str, Any]:
    record = {
        "id": evidence_id,
        "material_id": str(
            material.get("material_id")
            or material.get("id")
            or material.get("source_name")
            or evidence_id
        ),
        "source_name": str(material.get("source_name") or material.get("path") or ""),
        "source_type": str(material.get("source_type") or ""),
        "parse_status": str(material.get("parse_status") or "inline"),
        "summary": _material_summary(material),
        "key_findings": _material_key_findings(material),
        "hypothesis_relevant_points": _hypothesis_points(material),
        "data_assets": material.get("data_assets", []),
        "source_refs": {
            "source_path": material.get("source_path") or material.get("path") or "",
            "parsed_artifact_path": material.get("parsed_artifact_path", ""),
            "source_unit_count": (material.get("source_unit_summary") or {}).get("total", 0),
            "source_units_inlined": (material.get("source_unit_summary") or {}).get(
                "inlined",
                len(material.get("source_units") or []),
            ),
        },
        "downstream_use": _downstream_use(material),
    }
    if material.get("parse_error"):
        record["limitations"] = [str(material["parse_error"])]
    return record


def _material_summary(material: dict[str, Any]) -> str:
    if material.get("parse_status") == "unresolved":
        return f"材料无法读取：{material.get('parse_error', 'unknown_error')}。"
    profile = material.get("data_profile")
    if isinstance(profile, dict) and profile.get("summary"):
        return str(profile["summary"])
    source_type = material.get("source_type")
    unit_summary = material.get("source_unit_summary") or {}
    total = unit_summary.get("total", len(material.get("source_units") or []))
    if source_type in {"doc", "docx", "pdf"}:
        image_count = len(material.get("images") or [])
        topic = str(material.get("topic") or material.get("source_name") or "")
        image_text = f"，含 {image_count} 张图片/页面图" if image_count else ""
        return f"{topic[:80]}：已解析 {total} 个文本/图片 source units{image_text}。"
    if source_type == "image":
        images = material.get("images") or []
        if images and isinstance(images[0], dict):
            first = images[0]
            return (
                f"图片材料 {material.get('source_name', '')}："
                f"{first.get('width_px')}x{first.get('height_px')}，需视觉读取。"
            )
    hint = material.get("description_hint") or material.get("description")
    if hint:
        return str(hint)
    return f"已解析 {total} 个 source units。"


def _material_key_findings(material: dict[str, Any]) -> list[str]:
    profile = material.get("data_profile")
    if isinstance(profile, dict):
        findings = profile.get("key_findings")
        if isinstance(findings, list):
            return [str(item) for item in findings[:8]]
    findings = []
    for item in material.get("materials") or []:
        if isinstance(item, dict) and item.get("claim"):
            findings.append(str(item["claim"]))
        if len(findings) >= 5:
            break
    if findings:
        return findings
    hint = material.get("description_hint") or material.get("description")
    return [str(hint)] if hint else []


def _hypothesis_points(material: dict[str, Any]) -> list[str]:
    points = _material_key_findings(material)
    assets = material.get("data_assets") or []
    for asset in assets[:5]:
        if not isinstance(asset, dict):
            continue
        if asset.get("chart_ready"):
            points.append(
                f"{asset.get('label', asset.get('asset_id', 'table'))} 可回查原始数据生成趋势/对比图。"
            )
    if material.get("source_units_omitted"):
        points.append(
            f"完整 source_units 已保存在 sidecar，当前输入仅内联 {len(material.get('source_units') or [])} 条预览。"
        )
    return points[:10]


def _downstream_use(material: dict[str, Any]) -> list[str]:
    uses = ["evidence_lookup"]
    if material.get("data_assets"):
        uses.extend(["quant_analysis", "chart_generation"])
    if material.get("images"):
        uses.append("visual_inspection")
    if material.get("paragraphs") or material.get("raw_text"):
        uses.append("quote_extraction")
    return list(dict.fromkeys(uses))
