from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from presentation_agent.io import read_json, write_json
from presentation_agent.renderers.base import RenderResult
from presentation_agent.step import StepRunner


ROOT = Path(__file__).resolve().parents[1]
REPORT_FIXTURE = ROOT / "tests" / "fixtures" / "v0_3" / "report.v1.valid.json"


class ReportFinalizeIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.stage_dir = self.tmp / "stage_3_report"
        self.stage_dir.mkdir()
        input_path = self.stage_dir / "input.json"
        write_json(input_path, {"report_objective": "integration test"})
        write_json(
            self.stage_dir / "run_state.json",
            {
                "run_id": "report-finalize-test",
                "contract_profile": "v0_3",
                "agent_id": "report",
                "agent_name": "报告产出",
                "stage": 3,
                "status": "init",
                "current_step": "init",
                "round_index": 0,
                "input_path": str(input_path),
                "output_dir": str(self.stage_dir),
                "p0_open": [],
                "p1_open": [],
                "produced_artifacts": [],
                "history": [],
            },
        )
        self.runner = StepRunner(
            ROOT,
            self.stage_dir,
            data_root=self.tmp / "data",
            contract_profile="v0_3",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _finish(self, render_result: RenderResult) -> dict:
        generation = self.runner.prepare()
        write_json(Path(generation["output_path"]), read_json(REPORT_FIXTURE))
        review = self.runner.commit()
        write_json(Path(review["output_path"]), {"objections": []})
        with patch(
            "presentation_agent.renderers.report_docx.render_report_docx",
            return_value=render_result,
        ) as renderer:
            result = self.runner.commit()
        renderer.assert_called_once()
        self.assertEqual(renderer.call_args.kwargs["file_stem"], "report")
        return result

    def test_success_updates_artifact_and_returns_docx(self) -> None:
        output_path = self.stage_dir / "report.docx"
        result = self._finish(
            RenderResult(
                status="rendered",
                fmt="document",
                fidelity="content",
                output_path=str(output_path),
                file_bytes=123,
            )
        )

        artifact = read_json(self.stage_dir / "artifact.json")
        self.assertEqual(artifact["schema"], "report.v1")
        self.assertEqual(artifact["content_deliverable"]["status"], "rendered")
        self.assertEqual(
            artifact["content_deliverable"]["intended_path"], str(output_path)
        )
        self.assertNotIn("error", artifact["content_deliverable"])
        self.assertEqual(result["status"], "pending_human_review")
        self.assertEqual(result["rendered_files"], [str(output_path)])

    def test_failure_blocks_but_keeps_semantic_report_for_retry(self) -> None:
        result = self._finish(
            RenderResult(
                status="error",
                fmt="document",
                fidelity="content",
                detail="synthetic renderer failure",
            )
        )

        artifact = read_json(self.stage_dir / "artifact.json")
        self.assertEqual(artifact["schema"], "report.v1")
        self.assertTrue(artifact["sections"])
        self.assertEqual(artifact["content_deliverable"]["status"], "error")
        self.assertEqual(
            artifact["content_deliverable"]["error"],
            "synthetic renderer failure",
        )
        self.assertEqual(
            artifact["content_deliverable"]["intended_path"],
            str(self.stage_dir / "report.docx"),
        )
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("rendered_files", result)
        state = read_json(self.stage_dir / "run_state.json")
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(state["next_action"], "retry_report_docx_render")


if __name__ == "__main__":
    unittest.main()
