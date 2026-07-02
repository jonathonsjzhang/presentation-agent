"""Generic deterministic rubric checks declared by skill packages."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from presentation_agent.models import Objection


def run_machine_checks(
    artifact: dict[str, Any],
    rubrics: list[dict[str, Any]],
) -> list[Objection]:
    objections: list[Objection] = []
    for rubric in rubrics:
        machine_check = rubric.get("machine_check")
        if isinstance(machine_check, dict):
            objections.extend(_eval_rubric(artifact, rubric, machine_check))
    return objections


def _eval_rubric(
    artifact: dict[str, Any],
    rubric: dict[str, Any],
    machine_check: dict[str, Any],
) -> list[Objection]:
    severity = rubric.get("severity", "P0")
    rubric_id = rubric.get("id", "machine")
    dimension = str(rubric.get("dimension", ""))
    fix = str(rubric.get("fix") or rubric.get("improvement") or "")
    rules = machine_check.get("rules", [])
    if not isinstance(rules, list):
        return []

    each_path = machine_check.get("each")
    exempt = machine_check.get("exempt_when")
    optional_container = bool(machine_check.get("optional_container"))

    nodes: list[tuple[str, Any]]
    if each_path:
        array = _get(artifact, each_path)
        if not isinstance(array, list):
            if optional_container:
                return []
            return [
                _objection(
                    severity,
                    rubric_id,
                    dimension,
                    f"机械校验: 期望数组字段 `{each_path}` 不存在或类型错误",
                    each_path,
                    fix,
                )
            ]
        nodes = [(f"{each_path}[{index}]", item) for index, item in enumerate(array)]
    else:
        nodes = [("", artifact)]

    objections: list[Objection] = []
    for location, node in nodes:
        if exempt and _is_exempt(node, exempt):
            continue
        if not isinstance(node, dict) and each_path:
            continue
        for rule in rules:
            message = _eval_rule(node, rule, artifact)
            if not message:
                continue
            where = f"{location}.{rule.get('path', '')}".strip(".")
            objections.append(
                _objection(
                    severity,
                    rubric_id,
                    dimension,
                    f"机械校验: {message}",
                    where,
                    fix,
                )
            )
    return objections


def _eval_rule(
    node: Any,
    rule: dict[str, Any],
    artifact: dict[str, Any],
) -> Optional[str]:
    kind = rule.get("kind")
    path = str(rule.get("path", ""))
    value = _get(node, path) if path else node
    label = rule.get("label") or path or "value"

    if kind == "field_present":
        if value in (None, "", [], {}):
            return f"`{label}` 必填且不可为空"
        return None

    if kind == "enum":
        allowed = rule.get("values", [])
        if value is None:
            return f"`{label}` 缺失，应取自枚举 {allowed}"
        if value not in allowed:
            return f"`{label}` = {value!r} 不在允许枚举 {allowed} 内"
        return None

    if kind == "str_len":
        if not isinstance(value, str):
            return f"`{label}` 应为字符串"
        length = len(value)
        lower, upper = rule.get("min"), rule.get("max")
        if lower is not None and length < lower:
            return f"`{label}` 长度 {length} 小于下限 {lower}"
        if upper is not None and length > upper:
            return f"`{label}` 长度 {length} 超过上限 {upper}"
        return None

    if kind in ("array_len", "count_max", "count_min"):
        if not isinstance(value, list):
            return f"`{label}` 应为数组"
        length = len(value)
        lower = rule.get("min")
        upper = rule.get("max")
        if kind == "count_max" and upper is None:
            upper = rule.get("value")
        if kind == "count_min" and lower is None:
            lower = rule.get("value")
        if lower is not None and length < lower:
            return f"`{label}` 元素数 {length} 小于下限 {lower}"
        if upper is not None and length > upper:
            return f"`{label}` 元素数 {length} 超过上限 {upper}"
        return None

    if kind == "forbidden_pattern":
        paths = rule.get("paths")
        if not isinstance(paths, list):
            paths = [path] if path else [""]
        text = "\n".join(_flatten_text(_get(node, item)) for item in paths)
        for pattern in rule.get("patterns", []):
            try:
                match = re.search(str(pattern), text, flags=re.IGNORECASE)
            except re.error:
                continue
            if match:
                return f"`{label}` 命中禁止表达 {match.group(0)!r}"
        return None

    if kind == "cross_ref_exists":
        refs = value if isinstance(value, list) else [value]
        target = _get(artifact, str(rule.get("target_path", "")))
        target_key = str(rule.get("target_key", "id"))
        if isinstance(target, list):
            valid = {
                item.get(target_key)
                for item in target
                if isinstance(item, dict) and item.get(target_key) is not None
            }
        elif isinstance(target, dict):
            valid = set(target)
        else:
            return f"`{label}` 的目标集合不存在"
        missing = [ref for ref in refs if ref not in valid]
        if missing:
            return f"`{label}` 包含不存在的引用 {missing[:5]}"
        return None

    if kind == "conditional_required":
        when_value = _get(node, str(rule.get("when_path", "")))
        if "when_not" in rule:
            active = when_value != rule.get("when_not")
        elif "when_equals" in rule:
            active = when_value == rule.get("when_equals")
        else:
            active = bool(when_value)
        if active and _get(node, path) in (None, "", [], {}):
            return f"`{label}` 在条件满足时必填"
        return None

    if kind == "set_coverage":
        source = _get(artifact, str(rule.get("source_path", "")))
        target = _get(artifact, str(rule.get("target_path", "")))
        source_key = str(rule.get("source_key", "id"))
        if not isinstance(source, list) or not isinstance(target, dict):
            return f"`{label}` coverage 输入结构错误"
        source_ids = {
            item.get(source_key)
            for item in source
            if isinstance(item, dict) and item.get(source_key) is not None
        }
        missing = sorted(str(item) for item in source_ids - set(target))
        if missing:
            return f"`{label}` 未覆盖 {missing[:5]}"
        return None

    if kind == "enum_max_level":
        ordered = list(rule.get("values", []))
        max_value = rule.get("max")
        if value not in ordered or max_value not in ordered:
            return f"`{label}` = {value!r} 不在有序枚举 {ordered}"
        if ordered.index(value) > ordered.index(max_value):
            return f"`{label}` = {value!r} 超过允许上限 {max_value!r}"
        return None

    if kind == "disposition_claim_coverage":
        dispositions = _get(
            artifact, str(rule.get("disposition_path", ""))
        )
        claims = _get(artifact, str(rule.get("claims_path", "")))
        if not isinstance(dispositions, dict) or not isinstance(claims, list):
            return f"`{label}` disposition/claim 输入结构错误"
        claim_ids = {
            item.get("id")
            for item in claims
            if isinstance(item, dict) and item.get("id")
        }
        for evidence_id, disposition in dispositions.items():
            if not isinstance(disposition, dict):
                return f"`{label}` 中 {evidence_id} 不是对象"
            if disposition.get("status") not in ("selected", "counterpoint"):
                continue
            refs = disposition.get("claim_refs")
            if not isinstance(refs, list) or not refs:
                return f"`{label}` 中 {evidence_id} 未绑定 claim"
            missing = [ref for ref in refs if ref not in claim_ids]
            if missing:
                return (
                    f"`{label}` 中 {evidence_id} 引用不存在的 claim "
                    f"{missing[:5]}"
                )
        return None

    return None


def _is_exempt(node: Any, exempt: dict[str, Any]) -> bool:
    if not isinstance(node, dict):
        return False
    value = _get(node, exempt.get("path", ""))
    return value in exempt.get("values", [])


def _get(obj: Any, path: str) -> Any:
    if not path:
        return obj
    current = obj
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _objection(
    severity: str,
    rubric_id: str,
    dimension: str,
    message: str,
    evidence: str,
    suggestion: str,
) -> Objection:
    return Objection(
        id=f"{severity}-{rubric_id}",
        severity=severity if severity in ("P0", "P1") else "P1",
        dimension=dimension,
        message=message,
        evidence=evidence,
        suggestion=suggestion,
    )
