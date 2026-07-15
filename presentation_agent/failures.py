from __future__ import annotations

import hashlib
import re
from typing import Any


def classify_failure(
    message: str,
    *,
    stage: str,
    source: str = "runtime",
) -> dict[str, Any]:
    """Convert runtime text into a small, stable repair contract."""

    text = str(message or "unknown runtime failure").strip()
    lowered = text.lower()
    code = "contract_validation"
    responsible_stage = stage
    repair_scope = "same_stage"

    if "unsupported_file_type" in lowered or "path_not_found" in lowered:
        code = "missing_source_data"
        responsible_stage = "evidence_harvester"
        repair_scope = "evidence"
    elif "renderer 不支持" in text or "unsupported" in lowered and "chart" in lowered:
        code = "unsupported_visual_type"
        responsible_stage = "format"
    elif any(token in text for token in ("图表数据", "chart data", "table data", "matrix data", "视觉预检")):
        code = "invalid_data_shape"
        responsible_stage = "format"
    elif any(token in lowered for token in ("heading", "placement", "section_heading")):
        code = "missing_placement"
        responsible_stage = "format"
    elif any(token in lowered for token in ("libreoffice", "soffice", "python-docx", "pdfplumber", "chromium", "environment")):
        code = "environment_failure"
        responsible_stage = "runtime"
        repair_scope = "environment"
    elif any(token in lowered for token in ("degraded", "render", "output_path", "deliverable")):
        code = "render_failure"
        responsible_stage = "format"
    elif "evidence" in lowered and any(token in lowered for token in ("missing", "unknown", "not found")):
        code = "missing_analysis_asset"
        responsible_stage = "analysis"
        repair_scope = "upstream_stage"

    stable_detail = re.sub(r"\b\d+\b", "#", lowered)
    stable_detail = re.sub(r"[/\\][^\s;,。；]+", "<path>", stable_detail)
    stable_detail = re.sub(r"\s+", " ", stable_detail).strip()[:240]
    signature_basis = f"{stage}|{code}|{stable_detail}"
    signature = hashlib.sha256(signature_basis.encode("utf-8")).hexdigest()[:16]
    return {
        "schema": "runtime_failure.v1",
        "error_code": code,
        "stage": stage,
        "responsible_stage": responsible_stage,
        "repair_scope": repair_scope,
        "source": source,
        "message": text,
        "stable_detail": stable_detail,
        "signature": signature,
    }
