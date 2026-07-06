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
        rubrics = list(core.rubrics)
        tools: list[str] = []
        context_requirements: list[str] = []
        atomic_specs = []
        seen_rubric_ids = {
            row.get("id") for row in rubrics if isinstance(row, dict) and row.get("id")
        }
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
            # 原子 SKILL.md 正文 = 载体独有的核心准则与 gotcha（生成期须内化）。
            # 与 rules 注入相互独立：canonical_format 只替换 rules（契约字段），
            # 不影响 SKILL.md 准则的注入，从而实现 B1 共存。
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
            applicable_rubrics = [
                rubric for rubric in package["rubrics"] if _applies(rubric, spec.id)
            ]
            if not applicable_rubrics:
                applicable_rubrics = [
                    _rubric_from_rule(rule, atomic_spec.id)
                    for rule in matching_rules
                    if "review" in rule.get("phase", [])
                ]
            for rubric in applicable_rubrics:
                rubric_id = rubric.get("id")
                if rubric_id and rubric_id in seen_rubric_ids:
                    raise CapabilityError(f"Duplicate rubric id: {rubric_id}")
                if rubric_id:
                    seen_rubric_ids.add(rubric_id)
                rubrics.append(rubric)
            tools.extend(str(tool) for tool in package["tools"])

        selected_ids = set(selection.capability_ids)
        for atomic_spec in atomic_specs:
            conflicts = selected_ids.intersection(atomic_spec.incompatible_with)
            if conflicts:
                raise CapabilityError(
                    f"Capability {atomic_spec.id} conflicts with {sorted(conflicts)}"
                )

        instructions = "\n\n".join(section for section in instruction_sections if section)
        fingerprint = _fingerprint(
            selection.to_dict(), instructions, rubrics, core.schemas, tools
        )
        return SkillPackage(
            agent_id=spec.id,
            path=core.path,
            instructions=instructions,
            rubrics=rubrics,
            schemas=core.schemas,
            selected_capabilities=list(selection.capability_ids),
            tools=list(dict.fromkeys(tools)),
            context_requirements=list(dict.fromkeys(context_requirements)),
            fingerprint=fingerprint,
            budget=prompt_budget(
                instructions=instructions, rubrics=rubrics, schemas=core.schemas
            ),
            legacy=False,
        )
    except (CapabilityError, OSError, ValueError, KeyError):
        raise


def _is_report_v1_format(spec: AgentSpec, input_data: dict[str, Any]) -> bool:
    report = input_data.get("report")
    schema = report.get("schema") if isinstance(report, dict) else input_data.get("schema")
    return spec.id == "format" and (
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
    unit_types = {
        "document": "document_section",
        "ppt": "slide",
        "html": "html_module",
    }
    renderers = {
        "document": "docx_renderer",
        "ppt": "ppt_renderer",
        "html": "html_renderer",
    }
    return {
        "id": f"FMT-V03-{delivery_target.upper()}",
        "applies_to": ["format"],
        "phase": ["generation", "review"],
        "level": "P0",
        "property": "delivery_target_contract",
        "instruction": (
            f"只转译为 delivery_target={delivery_target}；"
            f"目标载体使用 {unit_types[delivery_target]} 结构和 "
            f"{renderers[delivery_target]}。"
            "Worker 只选择有证据的 visuals，不调用 renderer；"
            "runtime 负责默认版式、分页与渲染状态，"
            "report_markdown 始终是内容真相源。"
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


def _rubric_from_rule(rule: dict[str, Any], owner: str) -> dict[str, Any]:
    return {
        "id": f"{rule.get('id', owner)}-REVIEW",
        "severity": str(rule.get("level", "P1")).upper(),
        "dimension": str(rule.get("property", owner)),
        "criterion": str(rule.get("instruction", "")),
        "check": str(
            rule.get(
                "check",
                "检查产物是否遵循当前 capability 的场景要求，只有真实违反时才报异议。",
            )
        ),
        "fix": str(rule.get("fix", "按当前 capability 要求调整相关产物。")),
        "owner": owner,
    }


def _fingerprint(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
