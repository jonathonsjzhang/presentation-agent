from __future__ import annotations

from typing import Any

from presentation_agent.models import AgentSpec, Objection
from presentation_agent.skills.base import SkillContext


class StorylineDesignSkill:
    id = "storyline_design"

    def generation_dimensions(self) -> list[str]:
        return ["Leadline", "Wording", "结构", "证据"]

    def run(self, spec: AgentSpec, input_data: dict[str, Any], context: SkillContext) -> dict[str, Any]:
        executive_summary = input_data.get("executive_summary") or {}
        key_arguments = input_data.get("key_arguments") or []
        materials = input_data.get("materials") or key_arguments or []
        objective = (
            input_data.get("objective")
            or input_data.get("expected_action")
            or executive_summary.get("expected_action")
            or executive_summary.get("decision_request")
            or "本次汇报目标"
        )
        if not materials:
            materials = [
                {
                    "claim": input_data.get("topic", "待分析主题"),
                    "evidence": [],
                    "evidence_refs": [],
                    "so_what": str(objective),
                }
            ]

        pages = []
        for index, material in enumerate(materials, start=1):
            claim = str(material.get("claim", "")).strip() or f"第 {index} 个核心判断"
            evidence = material.get("evidence", [])
            if isinstance(evidence, str):
                evidence_list = [evidence] if evidence.strip() else []
            else:
                evidence_list = [str(item) for item in evidence if str(item).strip()]
            so_what = str(material.get("so_what", "")).strip() or "TODO: 提炼 so what"
            evidence_refs = [str(item) for item in material.get("evidence_refs", []) if str(item).strip()]
            expected_materials = [
                {
                    "material": item,
                    "evidence_ref": evidence_refs[i] if i < len(evidence_refs) else "",
                    "purpose": f"支撑本页判断：{claim}",
                    "status": "available" if evidence_refs or "需要补充" not in item else "needs_evidence",
                }
                for i, item in enumerate(evidence_list)
            ]
            if not expected_materials and evidence_refs:
                expected_materials = [
                    {
                        "material": f"引用证据 {ref}",
                        "evidence_ref": ref,
                        "purpose": f"支撑本页判断：{claim}",
                        "status": "available",
                    }
                    for ref in evidence_refs
                ]
            pages.append(
                {
                    "page_no": index,
                    "unit_type": "page" if input_data.get("output_format", "ppt") == "ppt" else "module",
                    "title": self._title_from_claim(claim),
                    "key_question": str(material.get("key_question", "")).strip()
                    or f"这个判断如何支撑 {objective}?",
                    "role_in_story": str(material.get("role_in_story", "")).strip() or self._role_for_index(index, len(materials)),
                    "evidence_refs": evidence_refs,
                    "evidence": evidence_list,
                    "expected_evidence_materials": expected_materials,
                    "so_what": so_what,
                    "transition": str(material.get("transition", "")).strip() or "下一页继续验证该判断对最终 action 的含义。",
                    "tag": material.get("tag", "mainline"),
                }
            )

        titles = [page["title"] for page in pages if page.get("tag") == "mainline"]
        core_conclusion = (
            executive_summary.get("core_conclusion")
            or input_data.get("core_thesis")
            or (titles[0] if titles else input_data.get("topic", ""))
        )
        return {
            "agent_id": spec.id,
            "schema": spec.output_schema,
            "topic": input_data.get("topic", ""),
            "audience": input_data.get("audience", ""),
            "report_type": input_data.get("report_type", ""),
            "output_format": input_data.get("output_format", ""),
            "objective": objective,
            "selected_story_angle": input_data.get("selected_story_angle", "executive_summary_to_action"),
            "story_angle_options": input_data.get("recommended_story_angles", []),
            "story_arc": f"围绕“{core_conclusion}”展开，先交代关键判断，再用核心论据逐步证明，最后回到“{objective}”。",
            "title_read_test": " -> ".join(titles),
            "memory_points": input_data.get("memory_points", []),
            "style_guidance": context.get("style_guidance", []),
            "pages": pages,
            "appendix_plan": input_data.get("appendix_plan", []),
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
        artifact = dict(previous_artifact)
        pages = [dict(page) for page in artifact.get("pages", [])]
        for objection in objections:
            if "page" in objection.evidence:
                self._fix_pages(pages)
            if "schema" in objection.evidence:
                artifact["schema"] = spec.output_schema
        if not pages:
            artifact = self.run(spec, input_data, context)
        else:
            self._fix_pages(pages)
            artifact["pages"] = pages
        return artifact

    def _fix_pages(self, pages: list[dict[str, Any]]) -> None:
        for index, page in enumerate(pages, start=1):
            page.setdefault("page_no", index)
            page.setdefault("unit_type", "page")
            page.setdefault("title", f"第 {index} 页需要形成明确结论")
            page.setdefault("key_question", "这页要回答什么关键问题?")
            page.setdefault("role_in_story", self._role_for_index(index, len(pages)))
            page.setdefault("evidence_refs", [])
            page.setdefault("evidence", ["TODO: 补充来源和数据"])
            page.setdefault(
                "expected_evidence_materials",
                [{"material": "TODO: 补充来源和数据", "purpose": "支撑本页判断", "status": "needs_evidence"}],
            )
            page.setdefault("so_what", "TODO: 补充管理层含义")
            page.setdefault("transition", "下一页继续推进故事线。")
            page.setdefault("tag", "mainline")
            if not page["evidence"]:
                page["evidence"] = ["TODO: 补充来源和数据"]
            if not page["expected_evidence_materials"]:
                page["expected_evidence_materials"] = [
                    {"material": item, "purpose": "支撑本页判断", "status": "available"} for item in page["evidence"]
                ]

    def _title_from_claim(self, claim: str) -> str:
        title = claim.strip()
        if title.endswith(("。", ".", "!", "！", "?", "？")):
            title = title[:-1]
        return title

    def _role_for_index(self, index: int, total: int) -> str:
        if index == 1:
            return "opening"
        if index == total:
            return "recommendation"
        return "driver"
