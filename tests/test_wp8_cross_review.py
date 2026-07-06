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
                self.report, self.formatted
            )["status"],
            "pass",
        )

    def test_runtime_unwraps_v03_canonical_upstream_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stage_dir = Path(temp_dir)
            input_path = stage_dir / "input.json"
            write_json(
                input_path,
                {
                    "schema": "worker_context.v1",
                    "analysis": self.analysis,
                },
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

    def test_analysis_to_storyline_blocks_missing_and_unsupported(self) -> None:
        artifact = copy.deepcopy(self.storyline)
        artifact["editorial_decisions"].pop()
        artifact["message_pyramid"]["supporting_messages"][0][
            "finding_refs"
        ] = ["F-404"]
        result = self.reviewer._check_analysis_to_storyline(
            self.analysis, artifact
        )
        self.assertEqual(result["status"], "block")
        self.assertEqual(
            {row["dimension"] for row in result["issues"]},
            {"finding_coverage", "unsupported_viewpoint"},
        )

    def test_advisory_revision_missing_editorial_row_is_warning_only(self) -> None:
        artifact = copy.deepcopy(self.storyline)
        removed = artifact["editorial_decisions"].pop()
        artifact["upstream_revision_requests"].append(
            {
                "request_type": "evidence_gap",
                "finding_refs": [removed["finding_id"]],
                "reason": "补充数据有助于增强但不影响主线成立",
                "blocking_level": "advisory",
            }
        )

        result = self.reviewer._check_analysis_to_storyline(
            self.analysis, artifact
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["issues"][0]["severity"], "P1")
        self.assertEqual(
            result["issues"][0]["dimension"],
            "advisory_finding_coverage",
        )

    def test_storyline_to_report_blocks_fidelity_loss(self) -> None:
        artifact = copy.deepcopy(self.report)
        artifact["sections"][0]["section_thesis"] = "改写后的过强结论"
        artifact["sections"][1]["finding_refs"] = []
        result = self.reviewer._check_storyline_to_report(
            self.storyline, artifact
        )
        self.assertEqual(result["status"], "block")
        self.assertEqual(result["issues"][0]["dimension"], "storyline_fidelity")

    def test_document_missing_number_blocks(self) -> None:
        artifact = copy.deepcopy(self.formatted)
        artifact["delivery_units"][0]["content"]["primary_text"] = "无数字"
        artifact["visual_assets"] = []
        result = self.reviewer._check_report_to_format(self.report, artifact)
        self.assertEqual(result["status"], "block")
        self.assertIn("content_retention", {
            row["dimension"] for row in result["issues"]
        })

    def _ppt_omitting_second_section(self) -> dict:
        artifact = copy.deepcopy(self.formatted)
        artifact["delivery_target"] = "ppt"
        artifact["artifact_manifest"]["target"] = "ppt"
        artifact["source_section_ids"] = ["S-01"]
        artifact["source_claim_ids"] = ["C-01"]
        artifact["delivery_units"] = [artifact["delivery_units"][0]]
        artifact["caveat_preservation"] = [artifact["caveat_preservation"][0]]
        return artifact

    def test_ppt_registered_non_protected_omission_passes(self) -> None:
        report = copy.deepcopy(self.report)
        report["format_handoff"]["protected_claim_ids"] = ["C-01"]
        report["format_handoff"]["protected_caveats"] = [
            "非随机分组，不能直接推断因果。"
        ]
        artifact = self._ppt_omitting_second_section()
        artifact["omitted_content_register"] = [
            {
                "source_ref": ref,
                "content_summary": "PPT 精简内容",
                "reason": "篇幅限制",
                "risk": "low",
                "recoverable_location": "source_report",
            }
            for ref in ("S-02", "C-02", "C-03", "E-I-01")
        ]
        self.assertEqual(
            self.reviewer._check_report_to_format(report, artifact)["status"],
            "pass",
        )

    def test_ppt_unregistered_omission_blocks(self) -> None:
        report = copy.deepcopy(self.report)
        report["format_handoff"]["protected_claim_ids"] = ["C-01"]
        report["format_handoff"]["protected_caveats"] = [
            "非随机分组，不能直接推断因果。"
        ]
        result = self.reviewer._check_report_to_format(
            report, self._ppt_omitting_second_section()
        )
        self.assertEqual(result["status"], "block")

    def test_protected_caveat_registered_as_omitted_still_blocks(self) -> None:
        artifact = copy.deepcopy(self.formatted)
        artifact["delivery_target"] = "ppt"
        artifact["delivery_units"][0]["caveats"] = []
        artifact["caveat_preservation"] = artifact["caveat_preservation"][1:]
        artifact["omitted_content_register"].append({
            "source_ref": "C-01",
            "content_summary": "非随机分组，不能直接推断因果。",
            "reason": "篇幅限制",
            "risk": "high",
            "recoverable_location": "source_report",
        })
        result = self.reviewer._check_report_to_format(self.report, artifact)
        self.assertEqual(result["status"], "block")
        retention = next(
            row for row in result["issues"]
            if row["dimension"] == "content_retention"
        )
        self.assertIn(
            "非随机分组，不能直接推断因果。",
            retention["evidence"]["missing_caveats"],
        )

    def test_ppt_unknown_reference_and_tampered_number_block(self) -> None:
        artifact = copy.deepcopy(self.formatted)
        artifact["delivery_target"] = "ppt"
        artifact["delivery_units"][0]["source_evidence_refs"].append("E-404")
        artifact["delivery_units"][0]["content"]["primary_text"] = (
            "成果保存组第 7 日回访率为 35%，仅单轮问答组为 18%。"
        )
        artifact["visual_assets"] = []
        result = self.reviewer._check_report_to_format(self.report, artifact)
        self.assertEqual(result["status"], "block")
        retention = next(
            row for row in result["issues"]
            if row["dimension"] == "content_retention"
        )["evidence"]
        self.assertIn("E-404", retention["unknown_evidence_refs"])
        self.assertIn("34", retention["missing_numbers"])

if __name__ == "__main__":
    unittest.main()
