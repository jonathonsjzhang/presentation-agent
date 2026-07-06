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
                "ANALYSIS-DISCOVERY-001",
                "ANALYSIS-INSIGHT-001",
                "ANALYSIS-EVIDENCE-001",
                "ANALYSIS-CHALLENGE-001",
                "ANALYSIS-CONVERGENCE-001",
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

    def test_fixture_covers_minimal_analysis_submission(self) -> None:
        self.assertTrue(self.artifact["findings"])
        for finding in self.artifact["findings"]:
            with self.subTest(finding=finding["id"]):
                self.assertTrue(finding["claim"])
                self.assertTrue(finding["evidence_refs"])
                self.assertIn(finding["confidence"], {"high", "medium", "low"})
                self.assertTrue(finding["so_what"])
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
