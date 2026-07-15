from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from presentation_agent.llm.schema import validate
from presentation_agent.skill_package import load_skill_package


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "v0_3" / "analysis.v1.valid.json"
SCHEMA = ROOT / "skills" / "analysis" / "schemas" / "analysis.v1.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class AnalysisSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = read_json(FIXTURE)
        self.schema = read_json(SCHEMA)
        self.package = load_skill_package(ROOT, "analysis")

    def test_skill_package_contains_complete_instructions_and_schema(self) -> None:
        self.assertIn("证据综合与候选论点设计者", self.package.instructions)
        self.assertIn("用 Minto 金字塔构造真正可选的论点组", self.package.instructions)
        self.assertIn("结论先行、以上统下、归类分组、逻辑递进", self.package.instructions)
        self.assertIn("关键证据或比较 → 识别出的模式", self.package.instructions)
        self.assertIn("选择不同 option 是否会实质改变最终核心答案", self.package.instructions)
        self.assertIn("不把 sub-theses 排成最终章节", self.package.instructions)
        self.assertIn("核心视觉证据候选", self.package.instructions)
        self.assertIn("analysis.v1", self.package.schemas)
        self.assertNotIn("BUNDLED REFERENCES", self.package.instructions)

        agents = read_json(ROOT / "configs" / "agents.json")
        active = agents["contract_profiles"]["v0_4"]
        analysis = next(worker for worker in active["workers"] if worker["id"] == "analysis")
        self.assertIn(
            "核心视觉证据候选",
            analysis["output_contract"]["required_headings"],
        )

    def test_frozen_fixture_is_strict_analysis_v1(self) -> None:
        self.assertEqual(self.artifact["agent_id"], "analysis")
        self.assertEqual(self.artifact["schema"], "analysis.v1")
        self.assertEqual(validate(self.artifact, self.schema), [])

    def test_fixture_covers_minimal_analysis_submission(self) -> None:
        self.assertTrue(self.artifact["findings"])
        for finding in self.artifact["findings"]:
            with self.subTest(finding=finding["id"]):
                self.assertTrue(finding["claim"])
                self.assertTrue(finding["evidence_refs"])
                self.assertIn(finding["confidence"], {"high", "medium", "low"})
                self.assertTrue(finding["so_what"])
        self.assertIn("thesis_options", self.schema["properties"])
        self.assertGreaterEqual(len(self.artifact["thesis_options"]), 2)
        for option in self.artifact["thesis_options"]:
            with self.subTest(option=option["option_id"]):
                self.assertTrue(option["main_thesis"])
                self.assertGreaterEqual(len(option["sub_theses"]), 2)
                self.assertLessEqual(len(option["sub_theses"]), 4)
        self.assertNotIn("viewpoint_candidates", self.schema["properties"])
        self.assertNotIn("quality_checks", self.schema["properties"])

    def test_schema_review_rejects_missing_required_finding_fields(self) -> None:
        for field in (
            "id",
            "claim",
            "evidence_refs",
            "confidence",
            "so_what",
        ):
            with self.subTest(field=field):
                invalid = copy.deepcopy(self.artifact)
                invalid["findings"][0].pop(field)
                errors = validate(invalid, self.schema)
                self.assertTrue(
                    any(
                        f"missing required field '{field}'" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_schema_review_rejects_missing_thesis_options(self) -> None:
        invalid = copy.deepcopy(self.artifact)
        invalid.pop("thesis_options")
        errors = validate(invalid, self.schema)
        self.assertTrue(
            any("missing required field 'thesis_options'" in error for error in errors),
            errors,
        )

    def test_schema_rejects_empty_grounding_so_what_and_confidence(self) -> None:
        invalid = copy.deepcopy(self.artifact)
        finding = invalid["findings"][0]
        finding["evidence_refs"] = [""]
        finding["so_what"] = ""
        finding["confidence"] = "certain"
        errors = validate(invalid, self.schema)
        self.assertTrue(any("evidence_refs" in error for error in errors), errors)
        self.assertTrue(any("so_what" in error for error in errors), errors)
        self.assertTrue(any("confidence" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
