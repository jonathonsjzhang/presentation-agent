from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from presentation_agent.cross_review import CrossStageReviewer
from presentation_agent.io import read_json, write_json


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v0_3"


class WP8CrossReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reviewer = CrossStageReviewer(ROOT, ROOT / "unused")
        self.analysis = read_json(FIXTURES / "analysis.v1.valid.json")
        self.storyline = read_json(FIXTURES / "storyline.v3.valid.json")
        self.report = read_json(FIXTURES / "report.v1.valid.json")
        self.qa_report = copy.deepcopy(self.report)
        self.qa_report["agent_id"] = "qa_preparation"
        self.qa_report["report_markdown"] = (
            self.report["report_markdown"].rstrip()
            + "\n\n## 听众可能追问的问题\n\n"
            + "1. 如果成果保存组本身就是高意愿用户，当前证据如何区分意愿和机制？\n"
            + "2. 哪些证据一旦相反，会推翻优先验证成果复用闭环的判断？\n"
        )
        self.formatted = read_json(FIXTURES / "formatted_material.v2.valid.json")

    def test_frozen_chain_passes_all_checks(self) -> None:
        self.assertEqual(
            self.reviewer._check_analysis_to_storyline(
                self.analysis, self.storyline
            )["status"],
            "pass",
        )
        self.assertEqual(
            self.reviewer._check_storyline_to_report(
                self.storyline, self.report
            )["status"],
            "pass",
        )
        self.assertEqual(
            self.reviewer._check_report_to_format(
                self.qa_report, self.formatted
            )["status"],
            "pass",
        )
        self.assertEqual(
            self.reviewer._check_qa(self.report, self.qa_report)["status"],
            "pass",
        )

    def test_runtime_unwraps_canonical_upstream_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stage_dir = Path(temp_dir)
            input_path = stage_dir / "input.json"
            write_json(
                input_path,
                {"schema": "worker_context.v1", "analysis": self.analysis},
            )
            write_json(stage_dir / "artifact.json", self.storyline)
            write_json(
                stage_dir / "run_state.json",
                {
                    "agent_id": "storyline",
                    "current_step": "done",
                    "input_path": str(input_path),
                },
            )
            result = CrossStageReviewer(ROOT, stage_dir).review_stage(stage_dir)
            self.assertEqual(result["status"], "pass")

    def test_storyline_blocks_unknown_finding_reference_but_not_omissions(self) -> None:
        artifact = copy.deepcopy(self.storyline)
        artifact["sections"][0]["finding_refs"] = ["F-404"]
        result = self.reviewer._check_analysis_to_storyline(
            self.analysis, artifact
        )
        self.assertEqual(result["status"], "block")
        self.assertEqual(result["issues"][0]["dimension"], "unsupported_viewpoint")

    def test_report_heading_rewrite_is_non_blocking_signal(self) -> None:
        artifact = copy.deepcopy(self.report)
        artifact["report_markdown"] = artifact["report_markdown"].replace(
            self.storyline["sections"][0]["heading"], "被改写的标题"
        )
        result = self.reviewer._check_storyline_to_report(
            self.storyline, artifact
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["issues"][0]["severity"], "P1")
        self.assertEqual(result["issues"][0]["dimension"], "storyline_heading_literal")

    def test_format_blocks_visual_for_unknown_section(self) -> None:
        artifact = copy.deepcopy(self.formatted)
        artifact["visuals"][0]["section_heading"] = "不存在的章节"
        result = self.reviewer._check_report_to_format(self.qa_report, artifact)
        self.assertEqual(result["status"], "block")
        self.assertEqual(result["issues"][0]["dimension"], "visual_section_mapping")

    def test_qa_blocks_when_original_report_is_rewritten(self) -> None:
        artifact = copy.deepcopy(self.qa_report)
        artifact["report_markdown"] = artifact["report_markdown"].replace(
            "当前新用户首周回访不足",
            "被改写的开头",
        )
        result = self.reviewer._check_qa(self.report, artifact)
        self.assertEqual(result["status"], "block")
        self.assertEqual(result["issues"][0]["dimension"], "qa_rewrites_report")


if __name__ == "__main__":
    unittest.main()
