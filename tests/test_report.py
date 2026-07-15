from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from presentation_agent.llm.schema import validate
from presentation_agent.skill_package import load_skill_package


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v0_3"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ReportCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storyline = read_json(FIXTURES / "storyline.v3.valid.json")
        self.report = read_json(FIXTURES / "report.v1.valid.json")
        self.schema = read_json(ROOT / "skills" / "report" / "schemas" / "report.v1.json")

    def test_report_skill_defines_a_real_markdown_author(self) -> None:
        skill = (ROOT / "skills" / "report" / "SKILL.md").read_text(encoding="utf-8")
        rubrics = read_json(ROOT / "skills" / "report" / "rubrics.json")
        self.assertIn(
            "基于已批准的 Storyline，把论证骨架写成一篇完整",
            skill,
        )
        self.assertIn("report_markdown", skill)
        self.assertIn("唯一内容真相源", skill)
        self.assertNotIn("正文 block 必须", skill)
        ids = {item["id"] for item in rubrics["rubrics"]}
        self.assertTrue(
            {
                "REPORT-SCHEMA-001",
                "REPORT-MANUSCRIPT-001",
                "REPORT-PROSE-001",
                "REPORT-TRACE-001",
            }.issubset(ids)
        )

    def test_editorial_style_reference_is_bundled_for_generation(self) -> None:
        instructions = load_skill_package(ROOT, "report").instructions
        self.assertIn("BUNDLED REFERENCES", instructions)
        self.assertIn("Reference: references/editorial_style.md", instructions)
        self.assertIn("删除常见 AI 腔", instructions)

    def test_frozen_report_strictly_validates_as_report_v1(self) -> None:
        self.assertEqual(validate(self.report, self.schema), [])
        self.assertEqual(
            self.schema["required"],
            ["report_markdown", "visual_evidence_placements"],
        )
        self.assertEqual(self.report["agent_id"], "report")
        self.assertEqual(self.report["schema"], "report.v1")
        self.assertEqual(self.report["report_file"], "report.md")
        for legacy in ("executive_summary", "sections", "narrative_blocks", "recommendations"):
            self.assertNotIn(legacy, self.report)

    def test_markdown_is_complete_continuous_and_self_contained(self) -> None:
        markdown = self.report["report_markdown"]
        self.assertTrue(markdown.startswith("# AI 助手用户留存改善机会"))
        for heading in (
            "## Executive Summary",
            "## 一、成果保存与回访共同出现，但因果仍待验证",
            "## 二、可复用成果提供了值得优先验证的回访理由",
            "## 结论与战略含义",
            "## 方法与边界",
        ):
            self.assertIn(heading, markdown)
        self.assertGreater(len(markdown), 1000)
        self.assertNotRegex(markdown, r"(核心论点|本节结论|承接)：")
        self.assertIn("34%", markdown)
        self.assertIn("非随机", markdown)

    def test_markdown_covers_the_approved_storyline_spine(self) -> None:
        markdown = self.report["report_markdown"]
        for section in self.storyline["sections"]:
            self.assertIn(section["heading"], markdown)
        self.assertNotIn("section_manifest", self.schema["properties"])

    def test_markdown_uses_readable_sources_not_internal_ids(self) -> None:
        markdown = self.report["report_markdown"]
        self.assertIn("来源：冻结匿名化行为数据快照", markdown)
        self.assertNotRegex(markdown, r"\b(?:E-Q|E-I|C-|F-)\d")
        self.assertIn("冻结匿名化行为数据快照", markdown)


if __name__ == "__main__":
    unittest.main()
