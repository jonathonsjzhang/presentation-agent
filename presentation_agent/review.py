from __future__ import annotations

import re
from typing import Any, Optional

from presentation_agent.io import flatten_text
from presentation_agent.llm.schema import validate
from presentation_agent.memory import MemoryStore
from presentation_agent.models import AgentSpec, Objection, ReviewReport, StopDecision


def apply_schema_gate_mode(review: ReviewReport, mode: str) -> ReviewReport:
    """Downgrade schema-only P0s in loop-first development mode."""

    if mode != "advisory":
        return review
    adjusted: list[Objection] = []
    for objection in review.objections:
        is_schema = (
            "schema" in objection.id.lower()
            or objection.dimension in ("接口", "schema_contract")
        )
        if objection.severity == "P0" and is_schema:
            adjusted.append(
                Objection(
                    id=objection.id.replace("P0", "P1", 1),
                    severity="P1",
                    dimension=objection.dimension,
                    message=f"[advisory schema] {objection.message}",
                    evidence=objection.evidence,
                    suggestion=objection.suggestion,
                )
            )
        else:
            adjusted.append(objection)
    return ReviewReport(
        reviewer=f"{review.reviewer}+schema_{mode}",
        objections=adjusted,
    )


class ArtifactReviewer:
    """Compatibility name for the runtime's deterministic artifact validator.

    The production chain has no independent rubric-based Reviewer agent. This
    class checks artifact identity, output schema, the selected carrier, and
    scoped memory reminders. It never makes a subjective quality judgment.
    """

    def review(
        self,
        spec: AgentSpec,
        artifact: dict[str, Any],
        memory: MemoryStore,
        skill_package: Optional[dict[str, Any]] = None,
        upstream_artifact: Optional[dict[str, Any]] = None,
    ) -> ReviewReport:
        del upstream_artifact  # kept only for compatibility with legacy callers
        objections = self._schema_gate(spec, artifact, skill_package)
        objections.extend(self._memory_scan(artifact, memory, skill_package))
        return ReviewReport(reviewer="runtime_validation", objections=objections)

    def _schema_gate(
        self,
        spec: AgentSpec,
        artifact: dict[str, Any],
        skill_package: Optional[dict[str, Any]],
    ) -> list[Objection]:
        objections: list[Objection] = []
        if artifact.get("schema") != spec.output_schema:
            objections.append(
                Objection(
                    id="P0-schema",
                    severity="P0",
                    dimension="接口",
                    message=f"artifact schema 必须为 {spec.output_schema}",
                    evidence="schema",
                    suggestion="按本环节 output_schema 重写 artifact",
                )
            )

        selected = (skill_package or {}).get("selected_capabilities", [])
        selected_formats = [
            item.removeprefix("format.")
            for item in selected
            if isinstance(item, str) and item.startswith("format.")
        ]
        artifact_format = artifact.get("format") or artifact.get("output_format")
        if len(selected_formats) == 1 and artifact_format:
            aliases = {"pptx": "ppt", "doc": "document", "docx": "document"}
            normalized = aliases.get(
                str(artifact_format).lower(), str(artifact_format).lower()
            )
            if normalized != selected_formats[0]:
                objections.append(
                    Objection(
                        id="P0-format-capability-mismatch",
                        severity="P0",
                        dimension="格式契约",
                        message=(
                            f"artifact format={normalized} 与 compiled "
                            f"format.{selected_formats[0]} 冲突"
                        ),
                        evidence="selected_capabilities",
                        suggestion="按本轮唯一激活的 format capability 重写产物",
                    )
                )

        schema = (skill_package or {}).get("schemas", {}).get(spec.output_schema)
        if schema:
            submission = {
                key: value
                for key, value in artifact.items()
                if key not in {
                    "agent_id",
                    "schema",
                    "delivery_target",
                    "render_result",
                    "render_manifest_path",
                    "visual_quality_manifest_path",
                    "artifact_manifest",
                    "evidence_index",
                    "evidence_assets",
                    "evidence_asset_enrichment",
                    "material_resolution",
                    "body_budget_audit",
                }
            }
            raw_errors = validate(submission, schema)
            for index, error in enumerate(
                _dedup_validation_errors(raw_errors), start=1
            ):
                objections.append(
                    Objection(
                        id=f"P0-schema-{index}",
                        severity="P0",
                        dimension="接口",
                        message=f"schema 不合规: {error}",
                        evidence="schema",
                        suggestion="补齐/修正字段以符合 output schema",
                    )
                )
        return objections

    @staticmethod
    def _memory_scan(
        artifact: dict[str, Any],
        memory: MemoryStore,
        skill_package: Optional[dict[str, Any]] = None,
    ) -> list[Objection]:
        content = dict(artifact)
        content.pop("style_guidance", None)
        text = flatten_text(content)
        active_capabilities = (skill_package or {}).get(
            "selected_capabilities", []
        )
        return [
            Objection(
                id=f"P1-memory-{item.id}",
                severity="P1",
                dimension=item.dimension,
                message=f"命中历史 memory: {item.trigger}",
                evidence=f"{item.id} owner={item.owner}",
                suggestion=item.suggestion,
            )
            for item in memory.scan(
                text, active_capabilities=active_capabilities
            )
        ]


class StopChecker:
    """Allow progress once deterministic validation has no blocking P0."""

    @staticmethod
    def check(
        spec: AgentSpec,
        artifact: dict[str, Any],
        review: ReviewReport,
    ) -> StopDecision:
        if review.p0:
            return StopDecision(
                can_stop=False,
                reason=f"blocked by {len(review.p0)} deterministic error(s)",
            )
        if artifact.get("schema") != spec.output_schema:
            return StopDecision(can_stop=False, reason="output schema mismatch")
        return StopDecision(
            can_stop=True,
            reason="deterministic validation passed; ready for the next gate",
        )


_ARRAY_INDEX_PAT = re.compile(r"\[\d+\]")


def _dedup_validation_errors(errors: list[str]) -> list[str]:
    """Collapse repeated array-item errors into one actionable message."""

    if len(errors) <= 1:
        return errors

    groups: dict[tuple[str, str], list[str]] = {}
    for error in errors:
        parts = error.split(": ", 1)
        path = parts[0] if len(parts) > 1 else error
        message = parts[1] if len(parts) > 1 else ""
        key = (_ARRAY_INDEX_PAT.sub("[*]", path), message)
        groups.setdefault(key, []).append(error)

    result: list[str] = []
    for (path, message), items in groups.items():
        if len(items) == 1:
            result.append(items[0])
            continue
        first_instance = _ARRAY_INDEX_PAT.search(items[0])
        example = first_instance.group(0) if first_instance else ""
        result.append(
            f"{path}: {message} (共 {len(items)} 处, 例: {example})"
        )
    return result
