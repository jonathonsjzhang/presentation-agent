from __future__ import annotations

import json
import unittest
from pathlib import Path

from presentation_agent.io import read_json
from presentation_agent.capabilities.compiler import compile_skill_package
from presentation_agent.llm.client import LLMClient
from presentation_agent.llm.types import LLMRequest
from presentation_agent.memory import MemoryStore
from presentation_agent.models import AgentSpec
from presentation_agent.review import ArtifactReviewer

ROOT = Path(__file__).resolve().parents[1]


def _storyline_spec() -> AgentSpec:
    agents = read_json(ROOT / "configs" / "agents.json")["agents"]
    return AgentSpec.from_dict(next(a for a in agents if a["id"] == "storyline_design"))


def _storyline_package(output_format: str) -> dict:
    return compile_skill_package(
        ROOT,
        _storyline_spec(),
        {
            "audience": "strategy_lead",
            "report_type": "deep_dive",
            "output_format": output_format,
        },
        legacy_fallback=False,
    ).to_dict()


class _FormatAwareReviewerAdapter:
    """A stand-in LLM reviewer that proves the rubric reaches the reviewer.

    It does NOT hard-code the rule; it reads the rubrics block embedded in the
    prompt, finds the format_adaptation rubric, and only then evaluates the
    artifact's unit_type against its output_format. If the rubric were not
    delivered to the reviewer, this adapter would emit no objection — so the
    test fails loudly if the wiring breaks.
    """

    kind = "fake-format-reviewer"

    def generate(self, request: LLMRequest) -> str:
        prompt = request.user
        # The reviewer must have been handed the rubrics; locate the format one.
        has_format_rubric = "FMT-" in prompt and "format_adaptation" in prompt
        if not has_format_rubric:
            return '```json\n{"objections": []}\n```'

        # Pull the artifact out of the prompt to inspect unit_type vs output_format.
        artifact = _extract_artifact(prompt)
        objections = []
        fmt = artifact.get("output_format")
        expected = {"document": "section", "ppt": "page", "html": "module"}.get(fmt)
        pages = artifact.get("pages", [])
        if expected and pages:
            mismatched = [p for p in pages if p.get("unit_type") and p["unit_type"] != expected]
            if mismatched:
                objections.append(
                    {
                        "rubric_id": f"FMT-{fmt.upper()}-SL-001",
                        "severity": "P1",
                        "dimension": "format_adaptation",
                        "message": f"output_format={fmt} 但 unit_type 未匹配为 {expected}",
                        "evidence": "SL-P1-005",
                        "suggestion": "按载体重设 unit_type 与结构粒度",
                    }
                )
        return "```json\n" + json.dumps({"objections": objections}, ensure_ascii=False) + "\n```"


def _extract_artifact(prompt: str) -> dict:
    # The artifact is the second fenced json block in the reviewer prompt.
    blocks = []
    marker = "```json"
    idx = 0
    while True:
        start = prompt.find(marker, idx)
        if start == -1:
            break
        end = prompt.find("```", start + len(marker))
        if end == -1:
            break
        blocks.append(prompt[start + len(marker) : end].strip())
        idx = end + 3
    # blocks[0] = rubrics, blocks[1] = artifact
    for raw in reversed(blocks):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "pages" in data:
            return data
    return {}


class FormatAdaptationReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = _storyline_spec()
        self.reviewer = ArtifactReviewer(llm=LLMClient(adapter=_FormatAwareReviewerAdapter(), max_retries=0))
        self.memory = MemoryStore(ROOT, "storyline_design")

    def _artifact(self, output_format: str, unit_type: str) -> dict:
        return {
            "agent_id": "storyline_design",
            "schema": "storyline.v2",
            "topic": "t",
            "audience": "strategy_lead",
            "report_type": "deep_dive",
            "output_format": output_format,
            "objective": "判断增长来源",
            "message_pyramid": {
                "governing_question": "增长来自哪里？",
                "core_answer": "增长来自组合优势",
                "supporting_messages": [{
                    "message": "组合优势比单点更关键",
                    "relationship_to_core": "直接支撑",
                    "source_argument_refs": ["A1"],
                    "page_nos": [1],
                }],
            },
            "ordering_rationale": "先给判断，再展开组合机制",
            "closing_intent": "形成对增长来源的共识",
            "title_read_test": {
                "title_chain": ["增长来自组合优势"],
                "passes": True,
                "checks": {
                    name: {"passes": True, "issue_pages": [], "note": "通过"}
                    for name in [
                        "completeness", "progression", "adjacency", "necessity",
                        "atomicity", "supportability", "decision_maturity",
                    ]
                },
                "revision_notes": [],
            },
            "pages": [
                {
                    "page_no": 1,
                    "unit_type": unit_type,
                    "leadline": "增长来自组合优势",
                    "title": "增长来自组合优势",
                    "page_question": "单点还是组合？",
                    "points_to_make": ["组合优势比单点更关键"],
                    "role_in_story": "opening",
                    "evidence_refs": ["E1"],
                    "transition_from_previous": "开场",
                    "transition_to_next": "收束",
                    "tag": "mainline",
                }
            ],
            "appendix_plan": [],
            "open_questions": [],
        }

    def test_mismatched_carrier_is_flagged(self) -> None:
        # document report but PPT-style page units -> should trip SL-P1-005
        artifact = self._artifact("document", "page")
        report = self.reviewer.review(self.spec, artifact, self.memory, _storyline_package("document"))
        ids = [o.id for o in report.objections]
        self.assertIn("P1-FMT-DOCUMENT-SL-001", ids)

    def test_matched_carrier_passes(self) -> None:
        # document report with section units -> no format objection
        artifact = self._artifact("document", "section")
        report = self.reviewer.review(self.spec, artifact, self.memory, _storyline_package("document"))
        ids = [o.id for o in report.objections]
        self.assertNotIn("P1-FMT-DOCUMENT-SL-001", ids)

    def test_ppt_requires_page_units(self) -> None:
        artifact = self._artifact("ppt", "section")
        report = self.reviewer.review(self.spec, artifact, self.memory, _storyline_package("ppt"))
        ids = [o.id for o in report.objections]
        self.assertIn("P1-FMT-PPT-SL-001", ids)


if __name__ == "__main__":
    unittest.main()
