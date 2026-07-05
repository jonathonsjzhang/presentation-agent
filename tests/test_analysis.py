from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from presentation_agent.llm.schema import validate
from presentation_agent.machine_check import run_machine_checks
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

    def test_skill_package_contains_instructions_rubrics_schema_and_reference(self) -> None:
        self.assertIn("证据准备度", self.package.instructions)
        self.assertIn("比较和追问", self.package.instructions)
        self.assertIn("analysis.v1", self.package.schemas)
        rubric_ids = {rubric["id"] for rubric in self.package.rubrics}
        self.assertTrue(
            {
                "AN-EVIDENCE-DECISION-001",
                "AN-FINDING-GROUNDING-001",
                "AN-SO-WHAT-001",
                "AN-COUNTER-001",
                "AN-ALTERNATIVE-001",
                "AN-CONFIDENCE-001",
                "AN-SCHEMA-001",
            }.issubset(rubric_ids)
        )

    def test_frozen_fixture_is_strict_analysis_v1_and_passes_machine_review(self) -> None:
        self.assertEqual(self.artifact["agent_id"], "analysis")
        self.assertEqual(self.artifact["schema"], "analysis.v1")
        self.assertEqual(validate(self.artifact, self.schema), [])
        self.assertEqual(
            run_machine_checks(self.artifact, self.package.rubrics),
            [],
        )

    def test_fixture_covers_required_analysis_reasoning_fields(self) -> None:
        self.assertTrue(self.artifact["findings"])
        for finding in self.artifact["findings"]:
            with self.subTest(finding=finding["finding_id"]):
                self.assertTrue(finding["supporting_evidence"])
                self.assertIn("counter_evidence", finding)
                self.assertTrue(finding["alternative_explanations"])
                self.assertIn(finding["confidence"], {"high", "medium", "low"})
                self.assertTrue(finding["so_what"])
                self.assertTrue(finding["decision_relevance"])
        self.assertTrue(self.artifact["decision_tensions"])
        self.assertTrue(self.artifact["discussion_points"])

    def test_schema_review_rejects_missing_required_finding_fields(self) -> None:
        for field in (
            "supporting_evidence",
            "counter_evidence",
            "alternative_explanations",
            "confidence",
            "so_what",
            "decision_relevance",
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

    def test_machine_review_rejects_empty_grounding_so_what_and_confidence(self) -> None:
        invalid = copy.deepcopy(self.artifact)
        finding = invalid["findings"][0]
        finding["supporting_evidence"] = []
        finding["so_what"] = ""
        finding["confidence"] = "certain"

        objections = run_machine_checks(invalid, self.package.rubrics)
        rubric_ids = {objection.id for objection in objections}
        self.assertIn("P0-AN-FINDING-GROUNDING-001", rubric_ids)
        self.assertIn("P0-AN-SO-WHAT-001", rubric_ids)
        self.assertIn("P0-AN-CONFIDENCE-001", rubric_ids)


if __name__ == "__main__":
    unittest.main()
