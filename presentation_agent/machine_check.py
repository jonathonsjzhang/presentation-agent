"""Deterministic machine-checkable rubric evaluation.

Some P0 rubrics are mechanically decidable — enum membership, length/count
thresholds, required-field presence. Handing those to a probabilistic LLM
(Layer 2) is wasteful and unstable. This module lets a rubric *declare* a
machine check via an optional ``machine_check`` block in rubrics.json; the
deterministic gate (Layer 1) parses and executes it with zero hard-coded,
agent-specific logic — fully package driven.

Rubrics WITHOUT a ``machine_check`` block are untouched and still flow to the
LLM reviewer. So this is purely additive: a rubric author opts in by declaring
the structured check next to the natural-language ``check`` text.

Supported check kinds (each rule is one dict in ``rules``):

- ``field_present``   : ``path`` must exist and be non-empty on every matched node.
- ``enum``            : value at ``path`` must be one of ``values``.
- ``str_len``         : string length at ``path`` within [``min``, ``max``].
- ``array_len``       : array length at ``path`` within [``min``, ``max``].
- ``count_max`` / ``count_min`` : alias for array_len bounds on a path.

Node selection: ``each`` selects an array on the artifact (dot path, e.g.
``material_units``); rules then run against every element. Omit ``each`` to run
rules against the artifact root once. ``exempt_when`` skips a node when a field
equals one of the listed values (e.g. cover/closing exempt from action-title).
"""

from __future__ import annotations

from typing import Any, Optional

from presentation_agent.models import Objection


def run_machine_checks(
    artifact: dict[str, Any],
    rubrics: list[dict[str, Any]],
) -> list[Objection]:
    """Evaluate every rubric that declares a ``machine_check`` block.

    Returns one Objection per failed rule occurrence. Rubrics without
    ``machine_check`` are skipped entirely (left for the LLM layer).
    """
    objections: list[Objection] = []
    for rubric in rubrics:
        mc = rubric.get("machine_check")
        if not isinstance(mc, dict):
            continue
        objections.extend(_eval_rubric(artifact, rubric, mc))
    return objections


def _eval_rubric(
    artifact: dict[str, Any],
    rubric: dict[str, Any],
    mc: dict[str, Any],
) -> list[Objection]:
    severity = rubric.get("severity", "P0")
    rubric_id = rubric.get("id", "machine")
    dimension = str(rubric.get("dimension", ""))
    fix = str(rubric.get("fix") or rubric.get("improvement") or "")
    rules = mc.get("rules", [])
    if not isinstance(rules, list):
        return []

    each_path = mc.get("each")
    exempt = mc.get("exempt_when")  # {"path": "...", "values": [...]}
    # When the container is owned/enforced by another rubric (e.g. a P0
    # presence check), set optional_container=true so a missing array is
    # silently skipped here instead of double-reporting.
    optional_container = bool(mc.get("optional_container"))

    nodes: list[tuple[str, Any]]
    if each_path:
        arr = _get(artifact, each_path)
        if not isinstance(arr, list):
            if optional_container:
                return []
            # missing/non-array container is itself a structural failure
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
        nodes = [(f"{each_path}[{i}]", el) for i, el in enumerate(arr)]
    else:
        nodes = [("", artifact)]

    objections: list[Objection] = []
    for loc, node in nodes:
        if exempt and _is_exempt(node, exempt):
            continue
        if not isinstance(node, dict) and each_path:
            continue
        for rule in rules:
            msg = _eval_rule(node, rule)
            if msg:
                where = f"{loc}.{rule.get('path', '')}".strip(".")
                objections.append(
                    _objection(severity, rubric_id, dimension, f"机械校验: {msg}", where, fix)
                )
    return objections


def _eval_rule(node: Any, rule: dict[str, Any]) -> Optional[str]:
    kind = rule.get("kind")
    path = rule.get("path", "")
    value = _get(node, path) if path else node
    label = rule.get("label") or path or "value"

    if kind == "field_present":
        if value is None or value == "" or value == [] or value == {}:
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
        n = len(value)
        lo, hi = rule.get("min"), rule.get("max")
        if lo is not None and n < lo:
            return f"`{label}` 长度 {n} 小于下限 {lo}"
        if hi is not None and n > hi:
            return f"`{label}` 长度 {n} 超过上限 {hi}"
        return None

    if kind in ("array_len", "count_max", "count_min"):
        if not isinstance(value, list):
            return f"`{label}` 应为数组"
        n = len(value)
        lo = rule.get("min")
        hi = rule.get("max")
        if kind == "count_max" and hi is None:
            hi = rule.get("value")
        if kind == "count_min" and lo is None:
            lo = rule.get("value")
        if lo is not None and n < lo:
            return f"`{label}` 元素数 {n} 小于下限 {lo}"
        if hi is not None and n > hi:
            return f"`{label}` 元素数 {n} 超过上限 {hi}"
        return None

    # unknown kind: silently ignore so a future kind in a newer rubric
    # never crashes an older runtime.
    return None


def _is_exempt(node: Any, exempt: dict[str, Any]) -> bool:
    if not isinstance(node, dict):
        return False
    val = _get(node, exempt.get("path", ""))
    return val in exempt.get("values", [])


def _get(obj: Any, path: str) -> Any:
    """Dot-path getter; tolerates missing keys -> None."""
    if not path:
        return obj
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


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
        severity=severity if severity in ("P0", "P1") else "P0",
        dimension=dimension,
        message=message,
        evidence=evidence,
        suggestion=suggestion,
    )
