from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Optional

from presentation_agent.capabilities.budget import estimate_tokens
from presentation_agent.io import flatten_text
from presentation_agent.llm.client import LLMClient
from presentation_agent.llm.schema import validate
from presentation_agent.llm.types import LLMRequest, SchemaValidationError
from presentation_agent.machine_check import run_machine_checks
from presentation_agent.memory import MemoryStore
from presentation_agent.models import AgentSpec, Objection, ReviewReport, StopDecision

# Schema for what the LLM reviewer must return.
_REVIEW_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["objections"],
    "properties": {
        "objections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["rubric_id", "severity", "dimension", "message"],
                "properties": {
                    "rubric_id": {"type": "string"},
                    "severity": {"enum": ["P0", "P1"]},
                    "dimension": {"type": "string"},
                    "message": {"type": "string"},
                    "evidence": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
            },
        }
    },
}


def apply_schema_gate_mode(
    review: ReviewReport,
    mode: str,
) -> ReviewReport:
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
    """Three-layer reviewer for any agent.

    Layer 1 (deterministic P0 hard gate): schema compliance + identity fields,
    driven by the agent's own output schema from the skill package — no
    hard-coded field lists. PLUS any rubric that declares a structured
    ``machine_check`` block (enum / length / count / required) is evaluated here
    deterministically, so mechanically-decidable P0 never depends on an LLM.
    Fast and reliable; owns objective correctness.

    Layer 2 (LLM subjective review, optional): reads rubrics.json in a clean
    context and judges the genuinely subjective criteria a regex can't — hook,
    pacing, memorability, MECE, title-read test, etc. Rubrics already covered by
    a machine check are excluded from the LLM prompt to avoid double-reporting.
    When ``upstream_artifact`` is provided, the L2 prompt also includes an
    "upstream signal check" that detects contradictions, degradation, or missing
    inheritance from the upstream artifact. Skipped gracefully when no LLM is
    injected (e.g. pure offline schema check).

    Layer 3 (memory scan): surfaces historical lessons as P1 reminders.
    """

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm
        self.last_prompt_budget: dict[str, int] = {}

    def review(
        self,
        spec: AgentSpec,
        artifact: dict[str, Any],
        memory: MemoryStore,
        skill_package: Optional[dict[str, Any]] = None,
        upstream_artifact: Optional[dict[str, Any]] = None,
    ) -> ReviewReport:
        objections: list[Objection] = []
        objections.extend(self._schema_gate(spec, artifact, skill_package))
        objections.extend(self._llm_review(spec, artifact, skill_package, upstream_artifact))
        objections.extend(self._memory_scan(artifact, memory, skill_package))
        reviewer = "llm+deterministic" if self.llm is not None else "deterministic"
        return ReviewReport(reviewer=reviewer, objections=objections)

    # -- layer 1: deterministic schema hard gate -------------------------

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
            # The schema is the worker-facing submission contract. Runtime
            # envelope fields are stamped after generation and are validated
            # separately above.
            submission = {
                key: value
                for key, value in artifact.items()
                if key not in {
                    "agent_id",
                    "schema",
                    "delivery_target",
                    "render_result",
                    "render_manifest_path",
                    "artifact_manifest",
                    "evidence_assets",
                    "evidence_asset_enrichment",
                    "body_budget_audit",
                }
            }
            raw_errors = validate(submission, schema)
            deduped = _dedup_validation_errors(raw_errors)
            for index, error in enumerate(deduped, start=1):
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

        # Mechanically-decidable rubrics (enum / length / count / required)
        # declared via machine_check are evaluated deterministically here,
        # not handed to the probabilistic LLM layer.
        rubrics = self._rubrics(skill_package)
        if rubrics:
            objections.extend(run_machine_checks(artifact, rubrics))
        return objections

    @staticmethod
    def _rubrics(skill_package: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
        rubrics = (skill_package or {}).get("rubrics", [])
        return rubrics if isinstance(rubrics, list) else []

    @staticmethod
    def _machine_checked_ids(rubrics: list[dict[str, Any]]) -> set[str]:
        return {
            r.get("id")
            for r in rubrics
            if isinstance(r.get("machine_check"), dict) and r.get("id")
        }

    # -- layer 2: LLM subjective review against rubrics ------------------

    def _llm_review(
        self,
        spec: AgentSpec,
        artifact: dict[str, Any],
        skill_package: Optional[dict[str, Any]],
        upstream_artifact: Optional[dict[str, Any]] = None,
    ) -> list[Objection]:
        if self.llm is None or not skill_package:
            return []
        all_rubrics = self._rubrics(skill_package)
        if not all_rubrics:
            return []
        # Exclude rubrics already covered deterministically in Layer 1 so the
        # LLM doesn't re-report the same mechanical failures.
        machine_ids = self._machine_checked_ids(all_rubrics)
        rubrics = [r for r in all_rubrics if r.get("id") not in machine_ids]
        if not rubrics:
            return []

        system = (
            "你是汇报助手流水线的独立审查 Agent，工作在干净上下文里，只依据 rubrics 判断产物质量，"
            "不参与生成、不揣测作者意图。只报告会真实影响交付的异议，不要按条目凑数。"
            "P0 只用于事实无依据、引用不存在、schema/字段无法交接、Worker 明显越权或最终材料不可用；"
            "结构、表达、节奏、锐度、可读性等改进一般报 P1。"
        )
        # drop the structured machine_check noise from what the LLM reads
        llm_rubrics = [
            {k: v for k, v in r.items() if k != "machine_check"} for r in rubrics
        ]

        # Build the user prompt sections: rubrics + artifact + optional
        # upstream-signal-check + output instruction.
        sections: list[str] = [
            "## 评审 rubrics(逐条对照)",
            self._json_block(llm_rubrics),
            "## 待审查 artifact",
            self._json_block(artifact),
        ]

        if upstream_artifact is not None:
            sections.extend([
                "## 上游信号检查 (upstream signal)",
                self._json_block(self._signal_snapshot(upstream_artifact)),
                "",
                "检查上游 artifact 的关键信号是否在当前 artifact 中被正确地继承或演化：",
                "- **矛盾**：当前 artifact 的结论、预设受众、方向是否与上游的明确信号正面冲突？",
                "- **强度漂移**：当前 artifact 是否无依据升级，或无理由弱化上游判断？",
                "- **上游越界处置**：若上游判断超过证据边界，当前 artifact 是否提交 revision request，而不是静默继承或静默改写？",
                "- **缺失继承**：上游明确提出的约束（受众类型、页数上限、目标 action）是否在当前 artifact "
                "中被忽略？",
                "",
                "如果发现上述任一问题，以 rubric_id=UPSTREAM-SIG-001、dimension=上游信号 报一条 P1 objection。",
                "没有发现任何问题时，无需报这条。",
            ])

        sections.extend([
            "## 输出要求",
            "只输出一个 ```json 代码块，形如 "
            '{"objections": [{"rubric_id","severity","dimension","message","evidence","suggestion"}]}。'
            "没有任何命中时输出 {\"objections\": []}。",
        ])

        user = "\n\n".join(sections)
        self.last_prompt_budget = {
            "system_chars": len(system),
            "system_tokens_estimate": estimate_tokens(system),
            "user_chars": len(user),
            "user_tokens_estimate": estimate_tokens(user),
            "total_chars": len(system) + len(user),
            "total_tokens_estimate": estimate_tokens(system + user),
        }
        request = LLMRequest(
            system=system,
            user=user,
            purpose="review",
            schema=_REVIEW_OUTPUT_SCHEMA,
            schema_name="review_report.v1",
            agent_id=spec.id,
        )
        try:
            response = self.llm.complete(request)
        except SchemaValidationError:
            # A reviewer that itself fails to produce valid output should not
            # crash the loop; treat as "no LLM objections this round".
            return []

        objections: list[Objection] = []
        for index, raw in enumerate(response.data.get("objections", []), start=1):
            severity = raw.get("severity")
            if severity not in ("P0", "P1"):
                continue
            objections.append(
                Objection(
                    id=f"{severity}-{raw.get('rubric_id', f'llm-{index}')}",
                    severity=severity,
                    dimension=str(raw.get("dimension", "")),
                    message=str(raw.get("message", "")),
                    evidence=str(raw.get("evidence", raw.get("rubric_id", ""))),
                    suggestion=str(raw.get("suggestion", "")),
                )
            )
        return objections

    @staticmethod
    def _signal_snapshot(upstream: dict[str, Any]) -> dict[str, Any]:
        """Extract the signal-relevant fields from an upstream artifact.

        Only keeps lightweight fields that downstream agents should inherit or
        consciously deviate from — strips heavy payloads (material_units, pages,
        evidence_bank, etc.) to keep the review prompt lean.
        """
        projected = upstream.get("upstream_signal")
        snapshot = dict(projected) if isinstance(projected, dict) else {}
        pages = upstream.get("pages")
        if not isinstance(pages, list):
            for source in dict(upstream.get("inputs", {})).values():
                if not isinstance(source, dict):
                    continue
                inline = source.get("inline_fields", {})
                candidate = inline.get("pages") if isinstance(inline, dict) else None
                if isinstance(candidate, list):
                    pages = candidate
                    break
        if isinstance(pages, list):
            snapshot["page_evidence_contracts"] = [
                ArtifactReviewer._page_evidence_contract(page)
                for page in pages
                if isinstance(page, dict)
            ]
        evidence_index = ArtifactReviewer._evidence_index(upstream)
        if evidence_index:
            snapshot["evidence_index"] = evidence_index
        readiness = upstream.get("input_readiness")
        if isinstance(readiness, dict):
            snapshot["input_readiness"] = readiness
        if snapshot:
            return snapshot
        heavy = {"material_units", "pages", "evidence_bank", "style_guidance", "raw_text",
                  "reference_patterns", "historical_reference_materials", "input_inventory"}
        return {
            k: v for k, v in upstream.items()
            if k not in heavy and v not in ("", [], {}, None)
        }

    @staticmethod
    def _evidence_index(upstream: dict[str, Any]) -> dict[str, Any]:
        containers: list[dict[str, Any]] = [upstream]
        raw_brief = upstream.get("raw_brief")
        if isinstance(raw_brief, dict):
            containers.append(raw_brief)
        for source in dict(upstream.get("inputs", {})).values():
            if not isinstance(source, dict):
                continue
            inline = source.get("inline_fields")
            if isinstance(inline, dict):
                containers.append(inline)

        result: dict[str, Any] = {}
        for container in containers:
            for field, id_key in (
                ("evidence_items", "evidence_id"),
                ("evidence_bank", "id"),
                ("source_units", "source_unit_id"),
            ):
                value = container.get(field)
                if isinstance(value, dict) and value.get("_projection"):
                    result[field] = value
                    continue
                if not isinstance(value, list):
                    continue
                summaries = []
                for item in value[:200]:
                    if not isinstance(item, dict):
                        continue
                    summaries.append(
                        {
                            id_key: item.get(id_key),
                            "type": item.get("type"),
                            "source_unit_refs": item.get("source_unit_refs", []),
                            "scope": item.get("scope"),
                            "modality": item.get("modality"),
                            "inspection_status": item.get("inspection_status"),
                        }
                    )
                result[field] = {
                    "count": len(value),
                    "items": summaries,
                }
        return result

    @staticmethod
    def _page_evidence_contract(page: dict[str, Any]) -> dict[str, Any]:
        handoff = page.get("format_handoff_notes", {})
        matrix = page.get("comparison_matrix", {})
        qualitative = page.get("qualitative_evidence", [])
        return {
            "page_no": page.get("page_no"),
            "leadline": page.get("leadline"),
            "title": page.get("title") or page.get("leadline"),
            "page_question": page.get("page_question"),
            "points_to_make": page.get("points_to_make", []),
            "evidence_refs": page.get("evidence_refs", []),
            "page_type": page.get("page_type"),
            "page_takeaway": page.get("page_takeaway"),
            "claim_strength": page.get("claim_strength"),
            "must_render_evidence": handoff.get("must_render_evidence", [])
            if isinstance(handoff, dict)
            else [],
            "on_screen_numbers": handoff.get("on_screen_numbers", [])
            if isinstance(handoff, dict)
            else [],
            "must_keep_caveats": handoff.get("must_keep_caveats", [])
            if isinstance(handoff, dict)
            else [],
            "comparison_matrix": {
                "reader_takeaway": matrix.get("reader_takeaway"),
                "source_refs": matrix.get("source_refs", []),
            }
            if isinstance(matrix, dict)
            else {},
            "qualitative_evidence": [
                {
                    "source_ref": row.get("source_ref"),
                    "role": row.get("role"),
                    "attribution": row.get("attribution"),
                }
                for row in qualitative
                if isinstance(row, dict)
            ],
        }

    # -- layer 3: memory scan -------------------------------------------

    def _memory_scan(
        self,
        artifact: dict[str, Any],
        memory: MemoryStore,
        skill_package: Optional[dict[str, Any]] = None,
    ) -> list[Objection]:
        content = dict(artifact)
        content.pop("style_guidance", None)
        text = flatten_text(content)
        objections: list[Objection] = []
        active_capabilities = (skill_package or {}).get(
            "selected_capabilities", []
        )
        for item in memory.scan(text, active_capabilities=active_capabilities):
            objections.append(
                Objection(
                    id=f"P1-memory-{item.id}",
                    severity="P1",
                    dimension=item.dimension,
                    message=f"命中历史 memory: {item.trigger}",
                    evidence=f"{item.id} owner={item.owner}",
                    suggestion=item.suggestion,
                )
            )
        return objections

    @staticmethod
    def _json_block(data: Any) -> str:
        return "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```"


# Lightweight output schema the stop-check LLM must return.
_STOP_CHECK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["can_stop", "confidence"],
    "properties": {
        "can_stop": {"type": "boolean"},
        "confidence": {"enum": ["high", "medium", "low"]},
        "notes": {"type": "string"},
        "flags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short labels for systemic concerns, e.g. 'thin_evidence', 'missing_exec_summary', 'inconsistent_tone'",
        },
    },
}


class StopChecker:
    """Clean-context stop gate: hard constraints + independent LLM sanity check.

    Layer 1 (deterministic): P0 objection count > 0 → block; schema mismatch → block.
    Layer 2 (LLM sanity): a lightweight, independent LLM context checks whether the
    artifact is genuinely converged or whether there are systemic issues the
    dedicated reviewer (L2 per-rubric LLM) might have missed.

    When ``llm`` is None the checker gracefully degrades to mechanical-only mode.
    The LLM here MUST be a separate client instance from both the maker and the
    reviewer, so the stop gate truly has independent reasoning.
    """

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm

    def check(
        self,
        spec: AgentSpec,
        artifact: dict[str, Any],
        review: ReviewReport,
    ) -> StopDecision:
        # -- layer 1: deterministic hard gates --------------------------------
        if review.p0:
            return StopDecision(can_stop=False, reason=f"blocked by {len(review.p0)} P0 objection(s)")
        if artifact.get("schema") != spec.output_schema:
            return StopDecision(can_stop=False, reason="output schema mismatch")

        # -- layer 2: independent LLM sanity check ----------------------------
        assessment: Optional[dict[str, Any]] = None
        if self.llm is not None:
            try:
                assessment = self._llm_sanity_check(spec, artifact, review)
            except Exception:
                # A broken stop-check LLM must not crash the loop — treat as
                # "LLM unavailable, fall through to mechanical pass".
                assessment = None

        if assessment is None:
            return StopDecision(
                can_stop=True,
                reason="all hard constraints passed; waiting for human review",
            )

        llm_stop = not assessment.get("can_stop", True)
        confidence = assessment.get("confidence", "medium")
        notes = assessment.get("notes", "")
        flags = assessment.get("flags", [])

        if llm_stop:
            flag_detail = f" flags={flags}" if flags else ""
            return StopDecision(
                can_stop=False,
                reason=f"independent stop-check disagrees (confidence={confidence}): {notes}{flag_detail}",
                llm_assessment=assessment,
            )

        return StopDecision(
            can_stop=True,
            reason=f"all hard constraints + independent check passed (confidence={confidence})",
            llm_assessment=assessment,
        )

    def _llm_sanity_check(
        self,
        spec: AgentSpec,
        artifact: dict[str, Any],
        review: ReviewReport,
    ) -> dict[str, Any]:
        """Send the artifact + review summary to the LLM for a lightweight sanity pass.

        The prompt is deliberately short — this is not a second full review; it
        only asks "is there anything the per-rubric reviewer obviously missed?"
        """
        # Strip bulk fields to keep the prompt light.
        safe = dict(artifact)
        safe.pop("style_guidance", None)
        safe.pop("material_units", None)  # too large, use count hint instead
        units = artifact.get("material_units")
        if isinstance(units, list):
            safe["_material_unit_count"] = len(units)

        review_summary = {
            "p0_count": len(review.p0),
            "p1_count": len(review.p1),
            "p1_samples": [obj.message for obj in review.p1[:3]],
        }

        system = (
            "You are an independent quality gate for a strategy presentation pipeline. "
            "The agent that produced this artifact and a dedicated per-rubric reviewer "
            "have both already run. Your job is NOT to re-review every rubric — it is "
            "to scan for SYSTEMIC concerns that a rubric-by-rubric reviewer might miss:\n"
            "- Does the argument actually ANSWER the prompt/objective?\n"
            "- Is the evidence thin, circular, or self-referential?\n"
            "- Are there missing structural elements (no exec summary, no action items)?\n"
            "- Is the tone or framing inconsistent with the audience/objective?\n"
            "- Could a reader plausibly misunderstand the central claim?\n\n"
            "Be strict: if you see ANY of these systemic issues, set can_stop=false. "
            "Only set can_stop=true when you are genuinely confident the artifact is "
            "ready for human review. Confidence should reflect your certainty level."
        )

        user = (
            f"Agent: {spec.name} (stage {spec.stage})\n"
            f"Output schema: {spec.output_schema}\n\n"
            f"--- ARTIFACT SUMMARY ---\n"
            f"{json.dumps(safe, ensure_ascii=False, indent=2, default=str)[:3000]}\n\n"
            f"--- REVIEW SUMMARY ---\n"
            f"{json.dumps(review_summary, ensure_ascii=False, indent=2)}\n\n"
            f"Based on the above, can this artifact stop for human review? "
            f"Return your assessment as JSON."
        )

        request = LLMRequest(
            system=system,
            user=user,
            purpose="stop_check",
            schema=_STOP_CHECK_SCHEMA,
            schema_name="stop_check",
            agent_id=spec.id,
        )
        response = self.llm.complete(request)
        return response.data


# ---------------------------------------------------------------------------
# schema validation error deduplication
# ---------------------------------------------------------------------------

_ARRAY_INDEX_PAT = re.compile(r"\[\d+\]")


def _dedup_validation_errors(errors: list[str]) -> list[str]:
    """Collapse array-level repetition so a single missing field doesn't
    produce one objection per array item.

    ``$.material_units[0].foo: …`` and ``$.material_units[1].foo: …``
    become ``$.material_units[*].foo: …  (×N)``.
    """
    if len(errors) <= 1:
        return errors

    # Group by (normalized path, error message)
    groups: dict[tuple[str, str], list[str]] = {}
    for err in errors:
        # Extract path (before ": ") and message (after ": ")
        parts = err.split(": ", 1)
        path = parts[0] if len(parts) > 1 else err
        msg = parts[1] if len(parts) > 1 else ""
        norm_path = _ARRAY_INDEX_PAT.sub("[*]", path)
        key = (norm_path, msg)
        groups.setdefault(key, []).append(err)

    result: list[str] = []
    for (norm_path, msg), items in groups.items():
        if len(items) == 1:
            result.append(items[0])
        else:
            first_instance = _ARRAY_INDEX_PAT.search(items[0])
            example_idx = first_instance.group(0) if first_instance else ""
            result.append(
                f"{norm_path}: {msg} "
                f"(共 {len(items)} 处, 例: {example_idx})"
            )
    return result
