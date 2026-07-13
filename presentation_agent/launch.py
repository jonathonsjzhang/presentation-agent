from __future__ import annotations

"""Shared host-launch entry (B-dimension wrapper foundation).

Three hosts — Claude Code (subagent), WorkBuddy (skill), Codex (prompt) — all
need to do the same thing: take a user's spoken request, turn it into a
`raw_brief.v1`, and kick off a report run. The only supported path is the
v0.3 Manager-orchestrated workflow.

Design choices baked in here:
  - Manager path is host-self-execution and does not use a provider.
  - brief normalization is forgiving: accepts a dict, a JSON string, or a path,
    fills sane defaults, and fails loudly only on the few truly-required fields.
  - stepwise by default (human-in-the-loop); hosts pass auto=True for dry runs.
"""

import json
from pathlib import Path
from typing import Any, Optional, Union

from presentation_agent.agent_profiles import load_agent_profile
from presentation_agent.capabilities.profile import normalize_report_profile
from presentation_agent.io import write_json
from presentation_agent.models import now_iso

BriefInput = Union[str, Path, dict]

RAW_BRIEF_SCHEMA = "raw_brief.v1"

# The opening brief gate now asks the user to complete research purpose,
# direction, and evidence confidence. Normalization only needs enough signal to
# start that gate; defaults cover the rest.
_STARTING_CONTEXT_FIELDS = (
    "topic",
    "user_intent",
    "context",
    "decision_goal",
    "expected_action",
    "research_purpose",
    "research_direction",
    "hypothesis",
    "materials",
    "source_units",
    "rows",
    "evidence_index",
    "evidence_catalog",
)

_DEFAULTS: dict[str, Any] = {
    "audience": "总办",
    "report_type": "deep_dive",
    "output_format": "document",
    "project_type": "分析类",
    "delivery_format": "文档",
    "context": "",
    "materials": [],
    "constraints": [],
    "user_intent": "",
    "decision_goal": "",
    "expected_action": "",
    "research_purpose": "",
    "research_direction": "",
}

_PROJECT_TYPE_ALIASES = {
    "分析": "分析类",
    "分析类": "分析类",
    "analysis": "分析类",
    "deep_dive": "分析类",
    "专题汇报": "分析类",
    "专题深度分析": "分析类",
    "梳理": "梳理类",
    "梳理类": "梳理类",
    "整理": "梳理类",
    "整理类": "梳理类",
    "summary": "梳理类",
    "quick_sync": "梳理类",
}

_DELIVERY_ALIASES = {
    "文档": "document",
    "word": "document",
    "docx": "document",
    "document": "document",
    "ppt": "ppt",
    "pptx": "ppt",
    "幻灯片": "ppt",
    "html": "html",
    "网页": "html",
}


class BriefError(ValueError):
    """Raised when the incoming brief cannot be normalized into raw_brief.v1."""


def _coerce_to_dict(brief: BriefInput, root: Path) -> dict[str, Any]:
    """Accept a dict, a JSON string, or a path to a JSON file.

    A bare string is treated as a path first (if it points at an existing file),
    otherwise as inline JSON. This lets host wrappers pass either a temp file
    they wrote or a JSON blob they assembled in-conversation.
    """
    if isinstance(brief, dict):
        return dict(brief)
    if isinstance(brief, Path):
        return json.loads(brief.read_text(encoding="utf-8"))
    if isinstance(brief, str):
        candidate = Path(brief)
        # absolute or root-relative path that exists -> load file
        for p in (candidate, root / candidate):
            if p.exists() and p.is_file():
                return json.loads(p.read_text(encoding="utf-8"))
        # otherwise treat the string as inline JSON
        try:
            data = json.loads(brief)
        except json.JSONDecodeError as exc:
            raise BriefError(
                "brief 既不是已存在的文件路径，也不是合法 JSON：" f"{exc}"
            ) from exc
        if not isinstance(data, dict):
            raise BriefError("brief JSON 顶层必须是对象（dict）")
        return data
    raise BriefError(f"不支持的 brief 类型：{type(brief)!r}")


def normalize_brief(
    brief: BriefInput,
    root: Path,
    contract_profile: Optional[str] = None,
) -> dict[str, Any]:
    """Turn any accepted brief form into a valid raw_brief.v1 dict.

    Fills defaults, stamps the schema tag, and validates the few required
    fields. Materials are lightly normalized so a host can pass a plain list of
    claim strings and still get a usable structure.
    """
    selected_profile = load_agent_profile(root, contract_profile).contract_profile
    data = _coerce_to_dict(brief, root)

    if not _has_starting_context(data):
        raise BriefError(
            "brief 缺少可用于启动汇报的需求信息：请提供 topic、user_intent、"
            "context、decision_goal、materials 或原始材料。"
        )

    normalized: dict[str, Any] = {**_DEFAULTS, **data}
    normalized["schema"] = RAW_BRIEF_SCHEMA

    normalized["materials"] = _normalize_materials(normalized.get("materials"))
    normalized["constraints"] = _as_str_list(normalized.get("constraints"))
    normalized["research_purpose"] = _first_text(normalized, "research_purpose")
    normalized["research_direction"] = _first_text(
        normalized,
        "research_direction",
        "hypothesis",
        "hypo",
    )
    if not str(normalized.get("decision_goal", "")).strip():
        normalized["decision_goal"] = normalized["research_purpose"]
    if not str(normalized.get("expected_action", "")).strip():
        normalized["expected_action"] = normalized["research_direction"]

    project_type = _normalize_project_type(
        data.get("project_type") or data.get("project_kind")
    )
    report_type_as_project_type = _normalize_project_type(data.get("report_type"))
    normalized["project_type"] = (
        project_type or report_type_as_project_type or str(normalized["project_type"])
    )
    if project_type and "report_type" not in data:
        normalized["report_type"] = _report_type_for_project_type(project_type)
    elif report_type_as_project_type:
        normalized["report_type"] = _report_type_for_project_type(
            report_type_as_project_type
        )

    requested_targets = _requested_delivery_targets(data, normalized)
    normalized["requested_delivery_targets"] = requested_targets
    normalized["delivery_format"] = _display_delivery_targets(requested_targets)
    if not str(normalized.get("report_length", "")).strip():
        normalized["report_length"] = _default_report_length(requested_targets)

    if selected_profile == "v0_3":
        allowed = {"document", "ppt", "html"}
        requested_targets = [
            item for item in requested_targets if item in allowed
        ] or ["document"]
        normalized["requested_delivery_targets"] = requested_targets
        normalized["requested_followup_targets"] = [
            item for item in requested_targets if item != "document"
        ]
        normalized["delivery_targets"] = ["document"]
        normalized["output_format"] = "document"
    profile = normalize_report_profile(
        normalized,
        root=root,
        allow_freeform_audience=True,
    )
    normalized["audience"] = profile.audience
    normalized["report_type"] = profile.report_type
    normalized["output_format"] = profile.output_format
    normalized["report_profile_version"] = selected_profile
    return normalized


def _has_starting_context(data: dict[str, Any]) -> bool:
    for field in _STARTING_CONTEXT_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, (list, tuple, set, dict)) and value:
            return True
    return False


def _first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_project_type(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    return _PROJECT_TYPE_ALIASES.get(text) or _PROJECT_TYPE_ALIASES.get(lowered, "")


def _report_type_for_project_type(project_type: str) -> str:
    return "quick_sync" if project_type == "梳理类" else "deep_dive"


def _requested_delivery_targets(
    data: dict[str, Any], normalized: dict[str, Any]
) -> list[str]:
    raw_targets = data.get("delivery_targets")
    if raw_targets is None:
        raw = (
            data.get("delivery_format")
            or data.get("output_format")
            or data.get("material_format")
            or normalized.get("output_format")
        )
        raw_targets = [raw]
    elif isinstance(raw_targets, str):
        raw_targets = [raw_targets]
    targets = [
        target
        for target in (_canonical_delivery_target(item) for item in raw_targets)
        if target
    ]
    return targets or ["document"]


def _canonical_delivery_target(value: Any) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    return _DELIVERY_ALIASES.get(text) or _DELIVERY_ALIASES.get(lowered, lowered)


def _display_delivery_targets(targets: list[str]) -> str:
    labels = {"document": "文档", "ppt": "PPT", "html": "HTML"}
    return " / ".join(labels.get(item, item) for item in targets)


def _default_report_length(targets: list[str]) -> str:
    return "10页PPT" if "ppt" in targets else "3页"


def _normalize_materials(materials: Any) -> list[dict[str, Any]]:
    if not materials:
        return []
    out: list[dict[str, Any]] = []
    for item in materials:
        if isinstance(item, str):
            text = item.strip()
            candidate = Path(text).expanduser()
            looks_like_path = (
                candidate.exists()
                or text.startswith(("/", "./", "../", "~/", "\\"))
                or text.endswith(("/", "\\"))
                or (len(text) > 2 and text[1] == ":" and text[2] in ("/", "\\"))
                or candidate.suffix.lower()
                in {
                    ".csv", ".doc", ".docx", ".jpg", ".jpeg", ".json",
                    ".md", ".pdf", ".png", ".txt", ".xlsx",
                }
            )
            if looks_like_path:
                out.append({"path": text})
            else:
                out.append({"claim": text, "evidence": [], "so_what": ""})
        elif isinstance(item, dict):
            normalized_item = dict(item)
            if "claim" in item:
                normalized_item["claim"] = str(item.get("claim", "")).strip()
            if "evidence" in item:
                normalized_item["evidence"] = _as_str_list(item.get("evidence"))
            if "so_what" in item:
                normalized_item["so_what"] = str(item.get("so_what", "")).strip()
            out.append(normalized_item)
    return out


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def launch_report(
    brief: BriefInput,
    root: Union[str, Path] = ".",
    *,
    use_manager: bool = True,
    provider: Optional[str] = None,
    auto: bool = False,
    out: Optional[Union[str, Path]] = None,
    spawn_adapter: Optional[str] = None,
    init_only: bool = False,
    contract_profile: Optional[str] = None,
) -> dict[str, Any]:
    """Normalize a brief, persist it, and kick off a report run.

    This is THE function every host wrapper calls. Returns run metadata so the
    host can show the user what was run and where the artifacts landed.

    **Manager path** (``use_manager=True``):
        Initializes a ManagerOrchestrator run, writes the brief, and returns
        the first instruction (Manager planning).  The host then drives the
        run step-by-step via the ``report next → submit → approve/feedback``
        protocol — no provider needed (host self-execution).

    ``use_manager=False`` is rejected. ``init_only`` remains in the public
    signature for callers migrating to the Manager protocol.
    """
    root_path = Path(root).resolve()
    if not use_manager:
        raise BriefError(
            "Direct Pipeline 已移除；请使用默认 Manager 路径"
        )
    if not spawn_adapter:
        raise BriefError(
            "Manager 路径要求宿主显式选择 spawn_adapter（workbuddy/codex/claude）；"
            "仅当宿主无法派生 sub-agent 时才显式使用 inline"
        )
    profile_request = contract_profile
    selected_profile = load_agent_profile(
        root_path, profile_request
    ).contract_profile
    normalized = normalize_brief(brief, root_path, selected_profile)

    run_id = f"report-{now_iso().replace(':', '').replace('+', 'Z')}"
    out_root = Path(out).resolve() if out else (root_path / "artifacts" / run_id)
    out_root.mkdir(parents=True, exist_ok=True)

    brief_path = out_root / "raw_brief.json"
    write_json(brief_path, normalized)

    # ---- Manager path (default) ---------------------------------------------
    if use_manager:
        if init_only:
            raise BriefError("init_only 已随 Direct Pipeline 一并移除")
        from presentation_agent.manager import ManagerOrchestrator

        orchestrator = ManagerOrchestrator(
            root_path,
            out_root,
            spawn_adapter=spawn_adapter,
            contract_profile=selected_profile,
        )
        instruction = orchestrator.initialize_run(brief_path)
        return {
            "run_id": orchestrator.run_dir.name,
            "run_dir": str(out_root),
            "brief_path": str(brief_path),
            "mode": "manager_controlled",
            "contract_profile": orchestrator.contract_profile,
            "spawn_adapter": orchestrator.workers.spawn_adapter.kind,
            "instruction": instruction,
        }

    raise BriefError("Manager 路径未能启动")
