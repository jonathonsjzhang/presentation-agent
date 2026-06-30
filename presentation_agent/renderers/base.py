"""Render dispatcher + shared result type.

`render_material(material, out_dir, fidelity)` picks a backend by the material's
`format` field (ppt / html / document) and produces a real deliverable file.

fidelity:
- "draft"  -> agent4 wireframe-level output (low-fidelity but real file)
- "final"  -> agent5 production output (McKinsey-grade)

Every backend returns a RenderResult. Missing optional deps never crash the
pipeline; they surface as status="skipped_missing_dep" with a clear reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class RenderResult:
    """Outcome of a single render attempt."""

    status: str  # "rendered" | "skipped_missing_dep" | "error" | "no_units"
    fmt: str  # "ppt" | "html" | "document"
    fidelity: str  # "draft" | "final"
    output_path: Optional[str] = None
    file_bytes: int = 0
    unit_count: int = 0
    warnings: list[str] = field(default_factory=list)
    detail: str = ""
    degraded: bool = False
    degraded_units: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "status": self.status,
            "format": self.fmt,
            "fidelity": self.fidelity,
            "output_path": self.output_path,
            "file_bytes": self.file_bytes,
            "unit_count": self.unit_count,
            "warnings": self.warnings,
            "detail": self.detail,
        }
        if self.degraded:
            d["degraded"] = True
            d["degraded_units"] = self.degraded_units
        return d

    def present_line(self) -> str:
        """One-line human summary for present_to_user."""
        if self.status == "rendered":
            kb = self.file_bytes / 1024 if self.file_bytes else 0
            line = f"已导出 {self.fidelity} 版 {self.fmt.upper()}：{self.output_path}（{self.unit_count} 单元，{kb:.0f}KB）"
            if self.degraded:
                line += f" ⚠️ {len(self.degraded_units)} 个单元 layout 降级"
            return line
        if self.status == "skipped_missing_dep":
            return f"⚠️ {self.fmt.upper()} 渲染跳过（缺少依赖）：{self.detail}"
        if self.status == "no_units":
            return f"⚠️ {self.fmt.upper()} 无可渲染单元"
        return f"⚠️ {self.fmt.upper()} 渲染失败：{self.detail}"


# Map the schema's `format` value to a backend key.
_FORMAT_ALIASES = {
    "ppt": "ppt",
    "pptx": "ppt",
    "html": "html",
    "document": "document",
    "doc": "document",
    "docx": "document",
}

_FORMAT_CAPABILITIES = {
    "ppt": "format.ppt",
    "html": "format.html",
    "document": "format.document",
}


def resolve_output_format(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw not in _FORMAT_ALIASES:
        raise ValueError(f"unsupported output format: {raw!r}")
    return _FORMAT_ALIASES[raw]


def render_material(
    material: dict[str, Any],
    out_dir: Path,
    fidelity: str = "final",
    file_stem: str = "deliverable",
    expected_format: Optional[str] = None,
    selected_capabilities: Optional[list[str]] = None,
) -> RenderResult:
    """Render a formatted_material.v1-shaped dict into a real file.

    `material` accepts both the agent5 `formatted_material.v1` (uses
    `material_units`) and the agent4 draft shape (also uses `material_units`
    but with lower-fidelity content). The `format` field selects the backend.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_fmt = material.get("format") or material.get("output_format")
    try:
        backend = resolve_output_format(expected_format or raw_fmt)
    except ValueError as exc:
        return RenderResult(
            status="error",
            fmt=str(expected_format or raw_fmt or "unknown"),
            fidelity=fidelity,
            detail=str(exc),
        )
    if expected_format:
        try:
            artifact_format = resolve_output_format(raw_fmt)
        except ValueError as exc:
            return RenderResult(
                status="error", fmt=backend, fidelity=fidelity, detail=str(exc)
            )
        if artifact_format != backend:
            return RenderResult(
                status="error",
                fmt=backend,
                fidelity=fidelity,
                detail=f"format mismatch: compiled={backend}, artifact={artifact_format}",
            )
    expected_capability = _FORMAT_CAPABILITIES[backend]
    if selected_capabilities and expected_capability not in selected_capabilities:
        return RenderResult(
            status="error",
            fmt=backend,
            fidelity=fidelity,
            detail=f"renderer requires {expected_capability}; selected={selected_capabilities}",
        )

    units = material.get("material_units") or []
    if not units:
        return RenderResult(status="no_units", fmt=backend, fidelity=fidelity)

    if backend == "ppt":
        from presentation_agent.renderers.ppt import render_ppt

        return render_ppt(material, out_dir, fidelity=fidelity, file_stem=file_stem)
    if backend == "html":
        from presentation_agent.renderers.html import render_html

        return render_html(material, out_dir, fidelity=fidelity, file_stem=file_stem)
    if backend == "document":
        from presentation_agent.renderers.docx import render_docx

        return render_docx(material, out_dir, fidelity=fidelity, file_stem=file_stem)

    return RenderResult(
        status="error", fmt=backend, fidelity=fidelity, detail=f"unknown format {raw_fmt}"
    )
