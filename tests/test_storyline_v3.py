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

    def test_skill_defines_two_outputs_and_one_serialization(self) -> None:
        package = load_skill_package(ROOT, "storyline")
        self.assertIn("任务一：形成完整 Storyline", package.instructions)
        self.assertIn("任务二：基于 Storyline 写 Executive Summary", package.instructions)
        self.assertIn("250–350", package.instructions)
        self.assertIn("Executive Summary：用 bullet 呈现报告全貌", package.instructions)
        self.assertIn("以 Minto 金字塔原理作为默认论证结构", package.instructions)
        self.assertIn("结论先行、以上统下、归类分组、逻辑递进", package.instructions)
        self.assertIn("默认用正面陈述", package.instructions)
        self.assertIn("不用“不是 A，而是 B”制造转折语势", package.instructions)
        self.assertIn("完整推理链和证据链", package.instructions)
        self.assertIn("已经完成分析取舍的**编辑蓝图**", package.instructions)
        self.assertIn("不同时输出 Markdown 和 JSON", package.instructions)
        self.assertIn("不重读 Raw Materials 补做分析", package.instructions)
        self.assertNotIn("最终可独立阅读的 Executive Summary 由 Report 写成", package.instructions)
        self.assertIn("storyline.v3", package.schemas)

    def test_executive_summary_is_required_and_within_budget(self) -> None:
        summary = self.storyline["executive_summary"]
        self.assertIsInstance(summary, str)
        self.assertLessEqual(250, len(summary))
        self.assertLessEqual(len(summary), 350)
        top_level_bullets = [
            line for line in summary.splitlines() if line.startswith("- ")
        ]
        self.assertLessEqual(2, len(top_level_bullets))
        self.assertLessEqual(len(top_level_bullets), 4)
        self.assertTrue(all(line.startswith("- **") for line in top_level_bullets))
        self.assertIn("executive_summary", self.storyline_schema["required"])

        agents = read_json(ROOT / "configs" / "agents.json")
        active = agents["contract_profiles"]["v0_4"]
        storyline = next(worker for worker in active["workers"] if worker["id"] == "storyline")
        self.assertIn("Executive Summary", storyline["output_contract"]["required_headings"])

    def test_storyline_submission_is_ordered_sections_without_pages(self) -> None:
        self.assertTrue(self.storyline["core_answer"])
        self.assertTrue(self.storyline["executive_summary"])
        self.assertTrue(self.storyline["sections"])
        self.assertTrue(
            all(
                set(section)
                >= {"chapter", "heading", "brief", "finding_refs", "evidence_refs"}
                for section in self.storyline["sections"]
            )
        )
        self.assertTrue(all(section["chapter"] for section in self.storyline["sections"]))
        section_schema = self.storyline_schema["properties"]["sections"]["items"]
        self.assertIn("evidence_refs", section_schema["required"])
        self.assertNotIn("pages", self.storyline_schema["properties"])
        self.assertNotIn("message_pyramid", self.storyline_schema["properties"])
        self.assertNotIn("report_outline", self.storyline_schema["properties"])

    def test_every_section_references_real_analysis_finding(self) -> None:
        finding_ids = {item["id"] for item in self.analysis["findings"]}
        for section in self.storyline["sections"]:
            self.assertTrue(section["finding_refs"])
            self.assertLessEqual(set(section["finding_refs"]), finding_ids)

    def test_every_section_only_references_upstream_evidence(self) -> None:
        evidence_ids = {
            ref
            for finding in self.analysis["findings"]
            for ref in finding["evidence_refs"]
        }
        for section in self.storyline["sections"]:
            self.assertTrue(section["evidence_refs"])
            self.assertLessEqual(set(section["evidence_refs"]), evidence_ids)

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
