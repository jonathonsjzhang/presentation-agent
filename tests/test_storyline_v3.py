from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from presentation_agent.llm.schema import validate
from presentation_agent.skill_package import load_skill_package


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v0_3"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class StorylineV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.analysis = read_json(FIXTURES / "analysis.v1.valid.json")
        self.storyline = read_json(FIXTURES / "storyline.v3.valid.json")
        self.analysis_schema = read_json(
            ROOT / "skills/analysis/schemas/analysis.v1.json"
        )
        self.storyline_schema = read_json(
            ROOT / "skills/storyline/schemas/storyline.v3.json"
        )

    def test_minimal_artifacts_validate(self) -> None:
        self.assertEqual(validate(self.analysis, self.analysis_schema), [])
        self.assertEqual(validate(self.storyline, self.storyline_schema), [])

    def test_skill_keeps_reasoning_method_but_serializes_one_view(self) -> None:
        package = load_skill_package(ROOT, "storyline")
        self.assertIn("金字塔原理", package.instructions)
        self.assertIn("一句话可复述", package.instructions)
        self.assertIn("可被反方挑战", package.instructions)
        self.assertIn("论证累进", package.instructions)
        self.assertIn("受众决策链", package.instructions)
        self.assertIn("Pyramid 是内部思考工具，不进入最终输出", package.instructions)
        self.assertIn("storyline.v3", package.schemas)

    def test_storyline_submission_is_ordered_sections_without_pages(self) -> None:
        self.assertTrue(self.storyline["core_answer"])
        self.assertTrue(self.storyline["sections"])
        self.assertTrue(
            all(
                set(section) >= {"chapter", "heading", "brief", "finding_refs"}
                for section in self.storyline["sections"]
            )
        )
        self.assertTrue(all(section["chapter"] for section in self.storyline["sections"]))
        self.assertNotIn("pages", self.storyline_schema["properties"])
        self.assertNotIn("message_pyramid", self.storyline_schema["properties"])
        self.assertNotIn("report_outline", self.storyline_schema["properties"])

    def test_every_section_references_real_analysis_finding(self) -> None:
        finding_ids = {item["id"] for item in self.analysis["findings"]}
        for section in self.storyline["sections"]:
            self.assertTrue(section["finding_refs"])
            self.assertLessEqual(set(section["finding_refs"]), finding_ids)

    def test_unknown_finding_ref_is_detectable_without_full_disposition_table(self) -> None:
        invalid = copy.deepcopy(self.storyline)
        invalid["sections"][0]["finding_refs"] = ["F-404"]
        finding_ids = {item["id"] for item in self.analysis["findings"]}
        unknown = {
            ref
            for section in invalid["sections"]
            for ref in section["finding_refs"]
            if ref not in finding_ids
        }
        self.assertEqual(unknown, {"F-404"})


if __name__ == "__main__":
    unittest.main()
