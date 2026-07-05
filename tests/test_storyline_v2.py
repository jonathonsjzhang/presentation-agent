from __future__ import annotations

import unittest
from pathlib import Path

from presentation_agent.capabilities.compiler import compile_skill_package
from presentation_agent.io import read_json
from presentation_agent.llm.adapters.mock import synthesize_from_schema
from presentation_agent.llm.schema import validate
from presentation_agent.machine_check import run_machine_checks
from presentation_agent.models import AgentSpec
from presentation_agent.skills.base import SkillContext
from presentation_agent.skills.storyline import StorylineDesignSkill


ROOT = Path(__file__).resolve().parents[1]


def _spec() -> AgentSpec:
    rows = read_json(ROOT / "configs" / "agents.json")["agents"]
    return AgentSpec.from_dict(next(row for row in rows if row["id"] == "storyline_design"))


class StorylineV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = read_json(
            ROOT / "skills" / "storyline_design" / "schemas" / "storyline.v2.json"
        )
        self.rubrics = read_json(
            ROOT / "skills" / "storyline_design" / "rubrics.json"
        )["rubrics"]

    def test_minimal_synthesized_artifact_is_schema_valid(self) -> None:
        artifact = synthesize_from_schema(self.schema)
        self.assertEqual(artifact["schema"], "storyline.v2")
        self.assertEqual(validate(artifact, self.schema), [])

    def test_runtime_contract_selects_v2_and_dynamic_ordering(self) -> None:
        spec = _spec()
        package = compile_skill_package(
            ROOT,
            spec,
            {
                "audience": "business_team",
                "report_type": "business_progress",
                "output_format": "ppt",
            },
            legacy_fallback=False,
        )
        self.assertEqual(spec.output_schema, "storyline.v2")
        self.assertIn("dynamic message pyramid", package.instructions)
        self.assertIn("不得先选固定 Story Arc", package.instructions)
        self.assertIn("具体顺序由最重要的判断及其论证依赖决定", package.instructions)

    def test_page_contract_machine_check_requires_points(self) -> None:
        artifact = synthesize_from_schema(self.schema)
        artifact["pages"][0]["points_to_make"] = []
        objections = run_machine_checks(artifact, self.rubrics)
        ids = [objection.id for objection in objections]
        self.assertTrue(any(item.endswith("SL-CONTRACT-001") for item in ids))

    def test_legacy_fallback_does_not_force_recommendation_arc(self) -> None:
        spec = _spec()
        artifact = StorylineDesignSkill().run(
            spec,
            {
                "topic": "留存",
                "audience": "strategy_lead",
                "report_type": "deep_dive",
                "output_format": "ppt",
                "core_question": "留存差异来自哪里？",
                "core_thesis": "用户结构与产品体验共同相关",
                "key_arguments": [
                    {
                        "claim": "纯白用户价值更高但更难获取",
                        "logic_chain": "价值与获取难度同时上升",
                        "evidence_refs": ["E1"],
                        "so_what": "增长机会需要考虑获客约束",
                    }
                ],
            },
            SkillContext(),
        )
        self.assertEqual(artifact["schema"], "storyline.v2")
        self.assertEqual(artifact["pages"][0]["leadline"], artifact["pages"][0]["title"])
        self.assertNotEqual(artifact["pages"][-1]["role_in_story"], "recommendation")
        self.assertIn("不自动补行动建议", artifact["closing_intent"])

    def test_page_filling_review_snapshot_keeps_storyline_contract(self) -> None:
        from presentation_agent.review import ArtifactReviewer

        snapshot = ArtifactReviewer._signal_snapshot(
            {
                "pages": [{
                    "page_no": 3,
                    "leadline": "渠道拓新更强，但未改善强留存",
                    "title": "渠道拓新更强，但未改善强留存",
                    "page_question": "渠道是否同时提升用户质量和留存？",
                    "points_to_make": ["纯白占比更高", "强留存差异不显著"],
                    "evidence_refs": ["E3", "E4"],
                }]
            }
        )
        contract = snapshot["page_evidence_contracts"][0]
        self.assertEqual(contract["leadline"], "渠道拓新更强，但未改善强留存")
        self.assertEqual(contract["points_to_make"], ["纯白占比更高", "强留存差异不显著"])


if __name__ == "__main__":
    unittest.main()
