from __future__ import annotations

"""Shared host-launch entry (B-dimension wrapper foundation).

Three hosts — Claude Code (subagent), WorkBuddy (skill), Codex (prompt) — all
need to do the same thing: take a user's spoken request, turn it into a
`raw_brief.v1`, and kick off a report run. As of v0.2 the default path is
Manager-orchestrated; set ``use_manager=False`` for legacy direct Pipeline.

Design choices baked in here:
  - default provider is "cli" (decision 1A) when using legacy Pipeline; Manager
    path is host-self-execution and does not use a provider.
  - brief normalization is forgiving: accepts a dict, a JSON string, or a path,
    fills sane defaults, and fails loudly only on the few truly-required fields.
  - stepwise by default (human-in-the-loop); hosts pass auto=True for dry runs.
"""

import json
from pathlib import Path
from typing import Any, Optional, Union

from presentation_agent.agent_profiles import LEGACY_CONTRACT_PROFILE, load_agent_profile
from presentation_agent.capabilities.profile import normalize_report_profile
from presentation_agent.io import write_json
from presentation_agent.models import now_iso

BriefInput = Union[str, Path, dict]

RAW_BRIEF_SCHEMA = "raw_brief.v1"

# Only these must be present (possibly via defaults below) for the pipeline to
# have something meaningful to chew on. Everything else is optional context.
_REQUIRED_FIELDS = ("topic", "audience", "decision_goal")

_DEFAULTS: dict[str, Any] = {
    "report_type": "deep_dive",
    "output_format": "ppt",
    "context": "",
    "materials": [],
    "constraints": [],
    "user_intent": "",
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
    contract_profile: str = LEGACY_CONTRACT_PROFILE,
) -> dict[str, Any]:
    """Turn any accepted brief form into a valid raw_brief.v1 dict.

    Fills defaults, stamps the schema tag, and validates the few required
    fields. Materials are lightly normalized so a host can pass a plain list of
    claim strings and still get a usable structure.
    """
    selected_profile = load_agent_profile(root, contract_profile).contract_profile
    data = _coerce_to_dict(brief, root)

    normalized: dict[str, Any] = {**_DEFAULTS, **data}
    normalized["schema"] = RAW_BRIEF_SCHEMA

    missing = [f for f in _REQUIRED_FIELDS if not str(normalized.get(f, "")).strip()]
    if missing:
        raise BriefError(
            "brief 缺少必填字段：" + ", ".join(missing) + "。"
            "（topic=汇报主题、audience=汇报对象、decision_goal=希望支撑的决策）"
        )

    normalized["materials"] = _normalize_materials(normalized.get("materials"))
    normalized["constraints"] = _as_str_list(normalized.get("constraints"))
    if selected_profile == "v0_3":
        targets = normalized.get("delivery_targets") or ["document"]
        if isinstance(targets, str):
            targets = [targets]
        allowed = {"document", "ppt", "html"}
        requested_targets = [
            str(item) for item in targets if str(item) in allowed
        ]
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
    normalized["report_profile_version"] = profile.version
    return normalized


def _normalize_materials(materials: Any) -> list[dict[str, Any]]:
    if not materials:
        return []
    out: list[dict[str, Any]] = []
    for item in materials:
        if isinstance(item, str):
            out.append({"claim": item, "evidence": [], "so_what": ""})
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
    contract_profile: str = "v0_3",
) -> dict[str, Any]:
    """Normalize a brief, persist it, and kick off a report run.

    This is THE function every host wrapper calls. Returns run metadata so the
    host can show the user what was run and where the artifacts landed.

    **Manager path** (``use_manager=True``, default since v0.2):
        Initializes a ManagerOrchestrator run, writes the brief, and returns
        the first instruction (Manager planning).  The host then drives the
        run step-by-step via the ``report next → submit → approve/feedback``
        protocol — no provider needed (host self-execution).

    **Legacy Pipeline** (``use_manager=False``):
        Runs the direct six-Worker Pipeline via LoopRunner.  Requires a
        ``provider`` (defaults to ``"cli"`` when omitted).  Kept for
        compatibility and headless debugging.

    When ``init_only=True`` (legacy only), only writes the brief and creates
    stage 1's run_dir without running any agent.
    """
    root_path = Path(root).resolve()
    selected_profile = load_agent_profile(
        root_path, contract_profile
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
            raise BriefError("init_only 仅支持 Legacy Pipeline 路径")
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

    # ---- Legacy Pipeline (deprecated since v0.2) ----------------------------
    used_provider = provider or "cli"

    if init_only:
        from presentation_agent.step import PipelineStepper

        stepper = PipelineStepper(root_path, out_root)
        stage1 = stepper.init_pipeline(brief_path)
        return {
            "brief_path": str(brief_path),
            "output_dir": str(out_root),
            "stage_1_dir": stage1["stage_dir"],
        }

    from presentation_agent.pipeline import Pipeline

    pipeline = Pipeline(root_path, provider_override=used_provider)
    summary = pipeline.run(brief_path, run_dir=out_root, auto=auto)

    return {
        "brief_path": str(brief_path),
        "provider": used_provider,
        **summary,
    }
