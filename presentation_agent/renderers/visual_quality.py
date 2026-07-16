"""Renderer-owned visual preflight and post-render quality gates.

Format chooses a visual intent.  This module owns the deterministic boundary:
the intent must compile to a renderer-native primitive, and the generated
assets/pages must be inspectable before a deliverable is published.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any


SUPPORTED_VISUAL_TYPES = {"chart", "table", "matrix", "callout"}
SUPPORTED_CHART_TYPES = {"bar", "line"}


def renderer_readiness_issues(visuals: Any) -> list[str]:
    """Return actionable incompatibilities with the real renderer contract."""

    if not isinstance(visuals, list):
        return ["visuals 必须是数组"]
    issues: list[str] = []
    for index, visual in enumerate(visuals, 1):
        prefix = f"visual {index}"
        if not isinstance(visual, dict):
            issues.append(f"{prefix} 不是对象")
            continue
        visual_type = str(visual.get("type") or "").lower()
        if visual_type not in SUPPORTED_VISUAL_TYPES:
            issues.append(f"{prefix} 使用 renderer 不支持的 type={visual_type or '<empty>'}")
            continue
        data = visual.get("data") if isinstance(visual.get("data"), dict) else {}
        image_path = str(data.get("image_path") or "").strip()
        if image_path:
            path = Path(image_path).expanduser()
            if not path.is_file():
                issues.append(f"{prefix} 引用的 image_path 不存在: {image_path}")
            continue
        if visual_type == "chart":
            issues.extend(_chart_issues(prefix, visual))
        elif visual_type == "table":
            issues.extend(_table_issues(prefix, data))
        elif visual_type == "matrix":
            issues.extend(_matrix_issues(prefix, data))
        elif visual_type == "callout":
            text = str(data.get("text") or data.get("quote") or "").strip()
            if not text:
                issues.append(f"{prefix} 的 callout data 必须提供非空 text/quote")
    return issues


def _chart_issues(prefix: str, visual: dict[str, Any]) -> list[str]:
    from presentation_agent.renderers.formatted_document_v2 import (
        _normalize_chart_data,
        _to_float,
    )

    data = _normalize_chart_data({"data": visual.get("data") or {}})
    chart_type = str(data.get("chart_type") or "bar").lower()
    issues: list[str] = []
    if chart_type not in SUPPORTED_CHART_TYPES:
        issues.append(f"{prefix} 使用 renderer 不支持的 chart_type={chart_type}")
        return issues
    categories = data.get("categories")
    if not isinstance(categories, list) or not categories:
        return [f"{prefix} 的 chart data 必须提供非空 categories"]
    if any(not str(value).strip() for value in categories):
        issues.append(f"{prefix} 的 chart categories 不能包含空标签")
    values = data.get("values")
    series = data.get("series")
    if isinstance(values, list):
        if len(values) != len(categories):
            issues.append(f"{prefix} 的 chart categories 与 values 必须等长")
        elif any(_to_float(value) is None for value in values):
            issues.append(f"{prefix} 的 chart values 必须全部可解析为数值")
        return issues
    if not isinstance(series, list) or not series:
        issues.append(f"{prefix} 的 chart data 必须提供 values 或 series[].values")
        return issues
    for series_index, row in enumerate(series, 1):
        row_values = row.get("values") if isinstance(row, dict) else None
        if not isinstance(row_values, list) or len(row_values) != len(categories):
            issues.append(
                f"{prefix} 的 series {series_index} values 必须与 categories 等长"
            )
            continue
        parsed = [_to_float(value) for value in row_values]
        if chart_type == "bar" and any(value is None for value in parsed):
            issues.append(f"{prefix} 的柱状图 series {series_index} 必须全部为数值")
        elif chart_type == "line" and all(value is None for value in parsed):
            issues.append(f"{prefix} 的折线图 series {series_index} 至少需要一个数值")
    return issues


def _table_issues(prefix: str, data: dict[str, Any]) -> list[str]:
    columns = data.get("columns") or data.get("headers")
    rows = data.get("rows")
    if not isinstance(columns, list) or not columns:
        return [f"{prefix} 的 table data 必须提供非空 columns/headers"]
    issues: list[str] = []
    if any(not str(value).strip() for value in columns):
        issues.append(f"{prefix} 的 table columns/headers 不能包含空标签")
    if not isinstance(rows, list) or not rows:
        issues.append(f"{prefix} 的 table data 必须提供非空 rows")
        return issues
    for row_index, row in enumerate(rows, 1):
        if not isinstance(row, (list, tuple)):
            issues.append(f"{prefix} 的 table row {row_index} 必须是数组")
        elif len(row) != len(columns):
            issues.append(
                f"{prefix} 的 table row {row_index} 必须与 columns/headers 等长"
            )
    return issues


def _matrix_issues(prefix: str, data: dict[str, Any]) -> list[str]:
    labels = data.get("dimensions") or data.get("labels")
    if not isinstance(labels, list) or len(labels) != 4:
        return [f"{prefix} 的 matrix data 必须提供恰好 4 个 dimensions/labels"]
    issues: list[str] = []
    if any(not str(value).strip() for value in labels):
        issues.append(f"{prefix} 的 matrix dimensions/labels 不能包含空标签")
    limitations = data.get("limitations")
    if limitations is not None and (
        not isinstance(limitations, list) or len(limitations) != 4
    ):
        issues.append(f"{prefix} 的 matrix limitations 如提供，必须恰好有 4 项")
    return issues


def audit_render_output(
    material: dict[str, Any],
    render_result: Any,
    out_dir: Path,
    *,
    file_stem: str = "report_formatted",
    require_page_snapshots: bool = True,
) -> dict[str, Any]:
    """Inspect real generated assets and carrier pages after rendering."""

    out_dir = Path(out_dir)
    issues: list[dict[str, Any]] = []
    warnings: list[str] = []
    inspected_assets: list[dict[str, Any]] = []
    inspected_pages: list[dict[str, Any]] = []
    output_path = Path(str(getattr(render_result, "output_path", "") or ""))
    if getattr(render_result, "status", "") != "rendered":
        issues.append(
            _issue(
                "render_not_completed",
                "deliverable",
                "renderer 未返回 rendered 状态，无法进行视觉验收",
                output_path,
            )
        )
    elif not output_path.is_file():
        issues.append(
            _issue(
                "missing_deliverable",
                "deliverable",
                "renderer 声称成功，但 output_path 不存在",
                output_path,
            )
        )

    asset_dir = out_dir / f"{file_stem}_assets"
    for index, visual in enumerate(material.get("visuals") or [], 1):
        if not isinstance(visual, dict):
            continue
        visual_type = str(visual.get("type") or "")
        visual_id = str(visual.get("visual_evidence_id") or f"VIS-{index:02d}")
        data = visual.get("data") if isinstance(visual.get("data"), dict) else {}
        source_image = Path(str(data.get("image_path") or "")).expanduser()
        if visual_type not in {"chart", "matrix"} and not source_image.is_file():
            continue
        image_path = source_image if source_image.is_file() else asset_dir / f"{visual_id}.png"
        row, row_issues = _audit_raster(image_path, scope="visual_asset")
        row.update({"visual_id": visual_id, "visual_type": visual_type})
        inspected_assets.append(row)
        issues.extend(row_issues)

    qa_dir = out_dir / "visual_quality"
    contact_sheet_path: str | None = None
    if output_path.is_file():
        try:
            from presentation_agent.renderers.artifact_preparation import (
                prepare_artifact_pages,
            )

            prepared = prepare_artifact_pages(output_path, qa_dir)
            warnings.extend(prepared.warnings)
            contact_sheet_path = prepared.contact_sheet_path
            for page_path in prepared.visual_paths:
                row, row_issues = _audit_raster(Path(page_path), scope="rendered_page")
                inspected_pages.append(row)
                issues.extend(row_issues)
            if require_page_snapshots and not prepared.visual_paths:
                issues.append(
                    _issue(
                        "page_snapshot_unavailable",
                        "deliverable",
                        "未生成任何真实页面快照，不能以文件存在代替视觉验收",
                        output_path,
                    )
                )
        except Exception as exc:
            warnings.append(f"page preparation failed: {exc}")
            if require_page_snapshots:
                issues.append(
                    _issue(
                        "page_snapshot_unavailable",
                        "deliverable",
                        f"真实页面快照生成失败: {exc}",
                        output_path,
                    )
                )

    ppt_qa: dict[str, Any] | None = None
    if output_path.suffix.lower() == ".pptx" and output_path.is_file():
        try:
            import json

            from presentation_agent.vendor.mck_ppt.qa import PptQA

            report = PptQA(str(output_path)).run()
            ppt_qa = json.loads(report.to_json())
            for item in ppt_qa.get("issues") or []:
                if item.get("severity") != "ERROR":
                    continue
                issues.append(
                    _issue(
                        f"ppt_{item.get('category') or 'layout_error'}",
                        "rendered_page",
                        str(item.get("message") or "PPT layout error"),
                        output_path,
                        metrics={"slide_num": item.get("slide_num")},
                    )
                )
        except Exception as exc:
            warnings.append(f"PPT structural QA unavailable: {exc}")

    return {
        "schema": "visual_quality.v1",
        "passed": not issues,
        "blocking_issue_count": len(issues),
        "issues": issues,
        "warnings": warnings,
        "inspected_assets": inspected_assets,
        "inspected_pages": inspected_pages,
        "contact_sheet_path": contact_sheet_path,
        "ppt_structural_qa": ppt_qa,
    }


def _audit_raster(path: Path, *, scope: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    row: dict[str, Any] = {"path": str(path), "scope": scope, "available": False}
    if not path.is_file():
        return row, [
            _issue(
                "missing_visual_asset" if scope == "visual_asset" else "missing_page_snapshot",
                scope,
                "预期的渲染图像不存在",
                path,
            )
        ]
    try:
        from PIL import Image

        with Image.open(path) as source:
            image = source.convert("L")
            width, height = image.size
            image.thumbnail((320, 320))
            pixels = list(
                image.get_flattened_data()
                if hasattr(image, "get_flattened_data")
                else image.getdata()
            )
    except Exception as exc:
        return row, [_issue("unreadable_raster", scope, f"图像无法读取: {exc}", path)]
    total = max(1, len(pixels))
    metrics = {
        "width": width,
        "height": height,
        "white_ratio": round(sum(value >= 250 for value in pixels) / total, 6),
        "dark_ratio": round(sum(value <= 15 for value in pixels) / total, 6),
        "content_ratio": round(sum(value < 245 for value in pixels) / total, 6),
        "grayscale_stddev": round(statistics.pstdev(pixels), 4) if len(pixels) > 1 else 0.0,
    }
    row.update({"available": True, "metrics": metrics})
    issues: list[dict[str, Any]] = []
    min_width, min_height = ((300, 150) if scope == "visual_asset" else (600, 600))
    if width < min_width or height < min_height:
        issues.append(
            _issue(
                "raster_too_small",
                scope,
                f"渲染图像尺寸过小: {width}x{height}",
                path,
                metrics=metrics,
            )
        )
    if metrics["dark_ratio"] > 0.96:
        issues.append(
            _issue("near_black_raster", scope, "渲染图像接近纯黑", path, metrics=metrics)
        )
    elif metrics["white_ratio"] > 0.998 or metrics["content_ratio"] < 0.002:
        issues.append(
            _issue("near_blank_raster", scope, "渲染图像接近空白", path, metrics=metrics)
        )
    elif metrics["grayscale_stddev"] < 1.5:
        issues.append(
            _issue("near_solid_raster", scope, "渲染图像接近单色", path, metrics=metrics)
        )
    return row, issues


def _issue(
    code: str,
    scope: str,
    message: str,
    path: Path,
    *,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "code": code,
        "severity": "P0",
        "scope": scope,
        "message": message,
        "path": str(path),
    }
    if metrics:
        row["metrics"] = metrics
    return row
