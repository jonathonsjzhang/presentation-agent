from __future__ import annotations

from typing import Any

from presentation_agent.models import AgentSpec, Objection
from presentation_agent.skills.base import SkillContext


class StorylineDesignSkill:
    """Legacy-compatible Storyline fallback.

    Production routing uses ``GenericSkill`` so the compiled Storyline package
    can reason about hierarchy and ordering. This class remains as a safe
    fallback for direct imports; it deliberately avoids choosing a fixed story
    arc or turning the last page into a recommendation.
    """

    id = "storyline_design"

    def generation_dimensions(self) -> list[str]:
        return ["Leadline", "Wording", "结构", "证据"]

    def run(
        self,
        spec: AgentSpec,
        input_data: dict[str, Any],
        context: SkillContext,
    ) -> dict[str, Any]:
        executive_summary = input_data.get("executive_summary") or {}
        materials = input_data.get("materials") or input_data.get("key_arguments") or []
        objective = (
            input_data.get("objective")
            or input_data.get("expected_action")
            or executive_summary.get("expected_action")
            or executive_summary.get("decision_request")
            or "形成对核心问题的判断"
        )
        governing_question = (
            input_data.get("core_question")
            or executive_summary.get("decision_request")
            or f"围绕“{input_data.get('topic', '本议题')}”需要形成什么判断？"
        )
        core_answer = (
            executive_summary.get("core_conclusion")
            or input_data.get("core_thesis")
        )
        if not core_answer:
            core_answer = (
                self._claim(materials[0], "待形成核心判断")
                if materials
                else "待形成核心判断"
            )

        pages: list[dict[str, Any]] = []
        supporting_messages: list[dict[str, Any]] = []
        unit_type = self._unit_type(input_data.get("output_format", "ppt"))
        for index, material in enumerate(materials, start=1):
            claim = self._claim(material, f"第 {index} 个核心判断")
            evidence_refs = self._strings(material.get("evidence_refs", []))
            points = self._points(material, claim)
            page_question = str(material.get("key_question", "")).strip()
            if not page_question:
                page_question = f"为什么可以得出“{claim}”？"
            source_refs = self._strings(
                material.get("source_argument_refs", material.get("argument_refs", []))
            )

            pages.append(
                {
                    "page_no": index,
                    "unit_type": unit_type,
                    "leadline": claim,
                    "title": claim,
                    "page_question": page_question,
                    "points_to_make": points,
                    "role_in_story": str(material.get("role_in_story", "")).strip()
                    or "support_core_answer",
                    "source_argument_refs": source_refs,
                    "evidence_refs": evidence_refs,
                    "transition_from_previous": str(
                        material.get("transition_from_previous", "")
                    ).strip()
                    or ("建立核心判断" if index == 1 else "承接上一判断并继续推进"),
                    "transition_to_next": str(
                        material.get("transition_to_next", "")
                    ).strip()
                    or ("收束到当前可支持的判断" if index == len(materials) else "引出下一层判断"),
                    "tag": str(material.get("tag", "mainline")),
                }
            )
            supporting_messages.append(
                {
                    "message": claim,
                    "relationship_to_core": str(
                        material.get("relationship_to_core", "")
                    ).strip()
                    or "支撑或限定 core answer",
                    "source_argument_refs": source_refs,
                    "page_nos": [index],
                }
            )

        if not pages:
            pages = [
                {
                    "page_no": 1,
                    "unit_type": unit_type,
                    "leadline": str(core_answer),
                    "title": str(core_answer),
                    "page_question": str(governing_question),
                    "points_to_make": ["明确当前材料能够支持的核心判断"],
                    "role_in_story": "establish_core_answer",
                    "source_argument_refs": [],
                    "evidence_refs": [],
                    "transition_from_previous": "开场提出 governing question",
                    "transition_to_next": "收束到当前可支持的判断",
                    "tag": "mainline",
                }
            ]
            supporting_messages = [
                {
                    "message": str(core_answer),
                    "relationship_to_core": "直接表达 core answer",
                    "source_argument_refs": [],
                    "page_nos": [1],
                }
            ]

        titles = [page["leadline"] for page in pages if page.get("tag") == "mainline"]
        title_checks = {
            dimension: {
                "passes": False,
                "issue_pages": [],
                "note": "Fallback 仅保证结构完整，需由独立 reviewer 做语义检查。",
            }
            for dimension in (
                "completeness",
                "progression",
                "adjacency",
                "necessity",
                "atomicity",
                "supportability",
                "decision_maturity",
            )
        }
        return {
            "agent_id": spec.id,
            "schema": spec.output_schema,
            "topic": input_data.get("topic", ""),
            "audience": input_data.get("audience", ""),
            "report_type": input_data.get("report_type", ""),
            "output_format": input_data.get("output_format", ""),
            "objective": str(objective),
            "message_pyramid": {
                "governing_question": str(governing_question),
                "core_answer": str(core_answer),
                "supporting_messages": supporting_messages,
            },
            "ordering_rationale": str(
                input_data.get("ordering_rationale")
                or "沿用上游论点顺序；生产运行应由 compiled LLM skill 根据真实论证依赖重排。"
            ),
            "closing_intent": str(
                input_data.get("closing_intent")
                or "收束到当前论据能够支持的判断，不自动补行动建议。"
            ),
            "title_read_test": {
                "title_chain": titles,
                "passes": False,
                "checks": title_checks,
                "revision_notes": ["需要独立 reviewer 完成结构化 title-read test。"],
            },
            "memory_points": input_data.get("memory_points", []),
            "style_guidance": context.get("style_guidance", []),
            "pages": pages,
            "appendix_plan": input_data.get("appendix_plan", []),
            "upstream_revision_requests": [],
            "open_questions": input_data.get("open_questions", []),
        }

    def revise(
        self,
        spec: AgentSpec,
        input_data: dict[str, Any],
        previous_artifact: dict[str, Any],
        objections: list[Objection],
        context: SkillContext,
    ) -> dict[str, Any]:
        # A deterministic fallback cannot safely repair semantic storyline
        # objections. Rebuild a schema-complete artifact without inventing a
        # fixed arc; the production GenericSkill handles genuine revisions.
        return self.run(spec, input_data, context)

    @staticmethod
    def _unit_type(output_format: str) -> str:
        return {
            "ppt": "page",
            "document": "section",
            "html": "module",
        }.get(str(output_format), "page")

    @staticmethod
    def _claim(material: dict[str, Any], fallback: str) -> str:
        claim = str(material.get("claim", "")).strip() if isinstance(material, dict) else ""
        return claim.rstrip("。.!！?？") or fallback

    @staticmethod
    def _strings(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return []

    def _points(self, material: dict[str, Any], claim: str) -> list[str]:
        explicit = self._strings(material.get("points_to_make", []))
        if explicit:
            return explicit
        candidates = [
            material.get("logic_chain"),
            material.get("why_it_matters"),
            material.get("so_what"),
        ]
        points = [str(item).strip() for item in candidates if str(item or "").strip()]
        return list(dict.fromkeys(points)) or [f"解释并支撑：{claim}"]
