from __future__ import annotations

from typing import Any


QUANTITATIVE_TYPES = {"time_series", "comparison", "distribution", "relationship"}


def audit_required_visual_evidence(
    formatted: dict[str, Any], report: dict[str, Any] | None
) -> dict[str, Any]:
    """Check that every required visual argument survives into a renderable visual."""

    report = report or {}
    placements = [
        item
        for item in report.get("visual_evidence_placements") or []
        if isinstance(item, dict)
    ]
    required = [item for item in placements if item.get("required") is True]
    visuals = {
        str(item.get("visual_evidence_id")): item
        for item in formatted.get("visuals") or []
        if isinstance(item, dict) and item.get("visual_evidence_id")
    }
    markdown = str(report.get("report_markdown") or "")
    issues: list[dict[str, Any]] = []

    for placement in required:
        evidence_id = str(placement.get("id") or "")
        marker = str(placement.get("marker") or f"[可视化论据：{evidence_id}]")
        if marker not in markdown:
            issues.append(
                _issue(evidence_id, "正文中缺少可视化论据的位置标记", "report")
            )
        visual = visuals.get(evidence_id)
        if visual is None:
            issues.append(
                _issue(evidence_id, "Format 没有生成对应的图表或表格", "format")
            )
            continue
        if str(visual.get("section_heading") or "") != str(
            placement.get("section_heading") or ""
        ):
            issues.append(
                _issue(evidence_id, "Format 生成的位置与 Report 指定位置不一致", "format")
            )
        if str(placement.get("data_type") or "") in QUANTITATIVE_TYPES and not _data_ready(visual):
            target = "evidence_harvester" if placement.get("data_asset_refs") else "analysis"
            issues.append(
                _issue(evidence_id, "缺少可绘制的完整数据，不能只用文字或空图代替", target)
            )

    return {
        "passed": not issues,
        "required_count": len(required),
        "resolved_count": len(required)
        - len({item["visual_evidence_id"] for item in issues}),
        "issues": issues,
    }


def revision_requests_from_audit(audit: dict[str, Any]) -> list[dict[str, Any]]:
    requests = []
    for issue in audit.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        requests.append(
            {
                "request_id": f"visual-{issue.get('visual_evidence_id', 'unknown')}",
                "target_agent": issue.get("target_agent", "analysis"),
                "blocking_level": "blocking",
                "reason": issue.get("reason", "可视化论据不完整"),
                "visual_evidence_refs": [issue.get("visual_evidence_id", "")],
                "requested_action": "补齐数据或交接信息后重新生成，不允许静默省略。",
            }
        )
    return requests


def _data_ready(visual: dict[str, Any]) -> bool:
    data = visual.get("data")
    if not isinstance(data, dict) or not data:
        return False
    visual_type = str(visual.get("type") or "")
    if visual_type == "chart":
        categories = data.get("categories")
        if not isinstance(categories, list) or not categories:
            return False
        series = data.get("series")
        if isinstance(series, list) and series:
            return all(
                isinstance(item, dict)
                and isinstance(item.get("values"), list)
                and len(item["values"]) == len(categories)
                for item in series
            )
        values = data.get("values")
        return isinstance(values, list) and len(values) == len(categories)
    if visual_type == "table":
        return bool(data.get("columns") or data.get("headers")) and bool(data.get("rows"))
    return True


def _issue(evidence_id: str, reason: str, target_agent: str) -> dict[str, str]:
    return {
        "visual_evidence_id": evidence_id,
        "reason": reason,
        "target_agent": target_agent,
    }
