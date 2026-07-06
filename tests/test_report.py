from __future__ import annotations

import json
import unittest
from pathlib import Path

from presentation_agent.llm.schema import validate


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v0_3"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ReportCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storyline = read_json(FIXTURES / "storyline.v3.valid.json")
        self.report = read_json(FIXTURES / "report.v1.valid.json")
        self.schema = read_json(ROOT / "skills" / "report" / "schemas" / "report.v1.json")

    def test_report_skill_and_rubrics_are_report_specific(self) -> None:
        skill = (ROOT / "skills" / "report" / "SKILL.md").read_text(encoding="utf-8")
        rubrics = read_json(ROOT / "skills" / "report" / "rubrics.json")
        self.assertIn("Markdown 报告", skill)
        self.assertIn("连续段落", skill)
        self.assertIn("report.v1", skill)
        self.assertNotIn("material_units 作为输出", skill)
        ids = {item["id"] for item in rubrics["rubrics"]}
        self.assertTrue(
            {
                "REPORT-SCHEMA-001",
                "REPORT-PROSE-001",
                "REPORT-TRACE-001",
                "REPORT-CAVEAT-001",
            }.issubset(ids)
        )
        self.assertTrue(all(item["id"].startswith("REPORT-") for item in rubrics["rubrics"]))

    def test_frozen_report_strictly_validates_as_report_v1(self) -> None:
        self.assertEqual(validate(self.report, self.schema), [])
        self.assertEqual(set(self.report), set(self.schema["required"]))
        self.assertEqual(self.report["agent_id"], "report")
        self.assertEqual(self.report["schema"], "report.v1")
        self.assertNotIn("pages", self.report)
        self.assertNotIn("material_units", self.report)

    def test_report_projects_storyline_without_changing_section_spine(self) -> None:
        storyline_sections = self.storyline["report_outline"]["sections"]
        report_sections = self.report["sections"]
        self.assertEqual(
            [item["section_id"] for item in report_sections],
            [item["section_id"] for item in storyline_sections],
        )
        self.assertEqual(
            [item["heading"] for item in report_sections],
            [item["heading"] for item in storyline_sections],
        )
        report_answer = self.report["executive_summary"]["core_answer"]
        storyline_answer = self.storyline["executive_summary"]["core_answer"]
        for protected_concept in ("成果", "复用", "闭环", "实验", "自选择"):
            self.assertIn(protected_concept, report_answer)
            self.assertIn(protected_concept, storyline_answer)
        self.assertIn("两周", self.report["executive_summary"]["expected_action"])
        for storyline_section, report_section in zip(storyline_sections, report_sections):
            self.assertEqual(report_section["section_thesis"], storyline_section["section_thesis"])
            self.assertEqual(set(report_section["finding_refs"]), set(storyline_section["finding_refs"]))

    def test_report_contains_continuous_prose_and_required_content_forms(self) -> None:
        for section in self.report["sections"]:
            paragraphs = [
                block["content"]
                for block in section["narrative_blocks"]
                if block["block_type"] == "paragraph"
            ]
            self.assertTrue(paragraphs, section["section_id"])
            self.assertTrue(any(len(paragraph) >= 60 for paragraph in paragraphs))
            self.assertTrue(section["section_conclusion"])
        self.assertTrue(any(
            block["block_type"] == "table"
            for section in self.report["sections"]
            for block in section["narrative_blocks"]
        ))
        self.assertTrue(self.report["source_registry"])
        self.assertTrue(self.report["caveats_and_limits"]["approach"])
        self.assertTrue(self.report["caveats_and_limits"]["limitations"])
        self.assertTrue(self.report["appendices"])

    def test_claim_finding_evidence_and_source_trace_is_closed(self) -> None:
        analysis = read_json(FIXTURES / "analysis.v1.valid.json")
        finding_ids = {item["finding_id"] for item in analysis["findings"]}
        for section in self.report["sections"]:
            self.assertLessEqual(set(section["finding_refs"]), finding_ids)
            block_claim_ids = {
                claim_id
                for block in section["narrative_blocks"]
                for claim_id in block["claim_ids"]
            }
            self.assertEqual(set(section["claim_ids"]), block_claim_ids)
            for block in section["narrative_blocks"]:
                self.assertTrue(block["claim_ids"])
                self.assertIn("evidence_refs", block)


if __name__ == "__main__":
    unittest.main()
