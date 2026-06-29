from __future__ import annotations

"""Shared host-launch entry (B-dimension wrapper foundation).

Three hosts — Claude Code (subagent), WorkBuddy (skill), Codex (prompt) — all
need to do the same thing: take a user's spoken request, turn it into a
`raw_brief.v1`, and kick off the legacy direct six-Worker Pipeline. Rather than
re-implement that plumbing in each host wrapper (which would drift), every
wrapper calls this one entry point. New interactive report runs use
`ManagerOrchestrator`; this wrapper remains for direct pipeline compatibility.

Design choices baked in here:
  - default provider is "cli" (decision 1A): the harness borrows whichever
    coding-agent CLI the host configured in configs/llm.json, so "谁发起用谁的
    模型" holds without the wrapper passing tokens.
  - brief normalization is forgiving: accepts a dict, a JSON string, or a path,
    fills sane defaults, and fails loudly only on the few truly-required fields.
  - stepwise by default (human-in-the-loop); hosts pass auto=True for dry runs.
"""

import json
from pathlib import Path
from typing import Any, Optional, Union

from presentation_agent.io import write_json
from presentation_agent.models import now_iso
from presentation_agent.pipeline import Pipeline

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


def normalize_brief(brief: BriefInput, root: Path) -> dict[str, Any]:
    """Turn any accepted brief form into a valid raw_brief.v1 dict.

    Fills defaults, stamps the schema tag, and validates the few required
    fields. Materials are lightly normalized so a host can pass a plain list of
    claim strings and still get a usable structure.
    """
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
    return normalized


def _normalize_materials(materials: Any) -> list[dict[str, Any]]:
    if not materials:
        return []
    out: list[dict[str, Any]] = []
    for item in materials:
        if isinstance(item, str):
            out.append({"claim": item, "evidence": [], "so_what": ""})
        elif isinstance(item, dict):
            out.append(
                {
                    "claim": str(item.get("claim", "")).strip(),
                    "evidence": _as_str_list(item.get("evidence")),
                    "so_what": str(item.get("so_what", "")).strip(),
                }
            )
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
    provider: Optional[str] = "cli",
    auto: bool = False,
    out: Optional[Union[str, Path]] = None,
    init_only: bool = False,
) -> dict[str, Any]:
    """Normalize a brief, persist it, and run the report pipeline.

    This is THE function every host wrapper calls. Returns the pipeline summary
    plus the path to the normalized brief so the host can show the user what was
    actually run and where the artifacts landed.

    provider defaults to "cli" per decision 1A; pass "mock" for offline dry runs
    or any provider key defined in configs/llm.json.

    When init_only=True, only writes the brief and creates stage 1's run_dir
    without running any agent. The host is expected to drive the pipeline
    step-by-step via `cli step` commands.
    """
    root_path = Path(root).resolve()
    normalized = normalize_brief(brief, root_path)

    run_id = f"report-{now_iso().replace(':', '').replace('+', 'Z')}"
    out_root = Path(out).resolve() if out else (root_path / "artifacts" / run_id)
    out_root.mkdir(parents=True, exist_ok=True)

    brief_path = out_root / "raw_brief.json"
    write_json(brief_path, normalized)

    if init_only:
        from presentation_agent.step import PipelineStepper

        stepper = PipelineStepper(root_path, out_root)
        stage1 = stepper.init_pipeline(brief_path)
        return {
            "brief_path": str(brief_path),
            "output_dir": str(out_root),
            "stage_1_dir": stage1["stage_dir"],
        }

    pipeline = Pipeline(root_path, provider_override=provider)
    summary = pipeline.run(brief_path, run_dir=out_root, auto=auto)

    return {
        "brief_path": str(brief_path),
        "provider": provider or "(config default)",
        **summary,
    }
