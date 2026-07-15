from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from presentation_agent.capabilities.budget import prompt_budget
from presentation_agent.capabilities.models import CapabilityError
from presentation_agent.capabilities.profile import normalize_report_profile
from presentation_agent.capabilities.registry import CapabilityRegistry
from presentation_agent.capabilities.resolver import resolve_capabilities
from presentation_agent.models import AgentSpec
from presentation_agent.skill_package import SkillPackage, load_skill_package


def compile_skill_package(
    root: Path,
    spec: AgentSpec,
    input_data: dict[str, Any],
    *,
    legacy_fallback: bool = False,
) -> SkillPackage:
    registry = CapabilityRegistry(root)
    core = load_skill_package(root, spec.skill)
    if not registry.enabled_for(spec.id):
        return core
    if not _has_profile_context(input_data):
        return core

    canonical_format = _is_report_v1_format(spec, input_data)
    try:
        profile = normalize_report_profile(input_data, root=root)
        selection = resolve_capabilities(spec.id, profile)
        atomic_keys = (
            ("audience", profile.audience),
            ("report_type", profile.report_type),
            ("format", profile.output_format),
        )
        core_instructions = core.instructions
        instruction_sections = [core_instructions]
        tools: list[str] = []
        context_requirements: list[str] = []
        atomic_specs = []
        property_owners: dict[str, tuple[str, str]] = {}

        for kind, value in atomic_keys:
            atomic_spec, package = registry.atomic_capability(kind, value)
            atomic_specs.append(atomic_spec)
            if atomic_spec.applies_to and spec.id not in atomic_spec.applies_to:
                continue
            matching_rules = [
                rule for rule in package["rules"] if _applies(rule, spec.id)
            ]
            if canonical_format and kind == "format":
                matching_rules = [_canonical_format_rule(profile.delivery_target)]
            lines = [str(rule.get("instruction", "")).strip() for rule in matching_rules]
            lines = [line for line in lines if line]
            # Atomic SKILL.md carries only concise, cross-stage carrier semantics.
            # Renderer implementation details stay in runtime rather than prompts.
            skill_body = str(package.get("instructions", "")).strip()
            if skill_body or lines:
                section = [f"## Active capability: {atomic_spec.id}"]
                if skill_body:
                    section.append(skill_body)
                if lines:
                    section.append("\n".join(f"- {line}" for line in lines))
                instruction_sections.append("\n\n".join(section))
            for rule in matching_rules:
                _check_property_conflict(rule, atomic_spec.id, property_owners)
                context_requirements.extend(
                    str(item) for item in rule.get("context_requirements", [])
                )
            tools.extend(str(tool) for tool in package["tools"])

        selected_ids = set(selection.capability_ids)
        for atomic_spec in atomic_specs:
            conflicts = selected_ids.intersection(atomic_spec.incompatible_with)
            if conflicts:
                raise CapabilityError(
                    f"Capability {atomic_spec.id} conflicts with {sorted(conflicts)}"
                )

        instructions = "\n\n".join(section for section in instruction_sections if section)
        fingerprint = _fingerprint(selection.to_dict(), instructions, core.schemas, tools)
        return SkillPackage(
            agent_id=spec.id,
            path=core.path,
            instructions=instructions,
            schemas=core.schemas,
            selected_capabilities=list(selection.capability_ids),
            tools=list(dict.fromkeys(tools)),
            context_requirements=list(dict.fromkeys(context_requirements)),
            fingerprint=fingerprint,
            budget=prompt_budget(
                instructions=instructions, schemas=core.schemas
            ),
            legacy=False,
        )
    except (CapabilityError, OSError, ValueError, KeyError):
        raise


def _is_report_v1_format(spec: AgentSpec, input_data: dict[str, Any]) -> bool:
    report = input_data.get("report")
    schema = report.get("schema") if isinstance(report, dict) else input_data.get("schema")
    return spec.id == "format" and (
        spec.output_schema == "format_plan.v1"
        or spec.input_schema == "markdown_artifact.v1"
        or
        spec.input_schema == "report.v1" or schema == "report.v1"
    )


def _has_profile_context(input_data: dict[str, Any]) -> bool:
    """Only compose atomic capabilities when the task carries profile data."""
    report = input_data.get("report")
    if isinstance(report, dict) and report.get("schema") == "report.v1":
        return True
    charter = input_data.get("report_charter")
    source = charter if isinstance(charter, dict) else input_data
    return any(
        source.get(key) not in (None, "", [], {})
        for key in ("audience", "report_type", "delivery_target", "output_format")
    )


def _canonical_format_rule(delivery_target: str) -> dict[str, Any]:
    renderers = {
        "document": "docx_renderer",
        "ppt": "ppt_renderer",
        "html": "html_renderer",
    }
    return {
        "id": f"FMT-V03-{delivery_target.upper()}",
        "applies_to": ["format"],
        "phase": ["generation"],
        "level": "P1",
        "property": "delivery_target_contract",
        "instruction": (
            f"本轮目标载体是 delivery_target={delivery_target}；"
            "Format worker 只选择有证据的 visuals[]，不写页面计划、不调用 renderer、"
            "不改 report_markdown。"
            f"默认版式和 {renderers[delivery_target]} 渲染由 runtime 负责。"
        ),
        "context_requirements": [
            "report_markdown",
            "delivery_target",
        ],
    }


def _applies(item: dict[str, Any], agent_id: str) -> bool:
    applies_to = item.get("applies_to", [])
    return not applies_to or agent_id in applies_to


def _check_property_conflict(
    rule: dict[str, Any],
    owner: str,
    property_owners: dict[str, tuple[str, str]],
) -> None:
    if str(rule.get("level", "")).upper() != "P0":
        return
    prop = str(rule.get("property", "")).strip()
    instruction = str(rule.get("instruction", "")).strip()
    if not prop:
        return
    previous = property_owners.get(prop)
    if previous and previous[1] != instruction:
        raise CapabilityError(
            f"Conflicting P0 capability rules for {prop}: {previous[0]} vs {owner}"
        )
    property_owners[prop] = (owner, instruction)


def _fingerprint(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
