from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from presentation_agent.io import read_json, write_json
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

    def _finish(self, report: dict | None = None) -> dict:
        generation = self.runner.prepare()
        write_json(Path(generation["output_path"]), report or read_json(REPORT_FIXTURE))
        review = self.runner.commit()
        write_json(Path(review["output_path"]), {"objections": []})
        return self.runner.commit()

    def test_success_materializes_canonical_markdown(self) -> None:
        result = self._finish()

        artifact = read_json(self.stage_dir / "artifact.json")
        markdown_path = self.stage_dir / "report.md"
        self.assertEqual(artifact["schema"], "report.v1")
        self.assertTrue(markdown_path.is_file())
        self.assertEqual(
            markdown_path.read_text(encoding="utf-8").rstrip(),
            artifact["report_markdown"].rstrip(),
        )
        self.assertEqual(result["status"], "pending_human_review")
        self.assertEqual(result["rendered_files"], [str(markdown_path)])
        self.assertEqual(result["render_result"]["format"], "markdown")

    def test_empty_markdown_is_rejected_before_finalize(self) -> None:
        report = read_json(REPORT_FIXTURE)
        report["report_markdown"] = ""
        generation = self.runner.prepare()
        write_json(Path(generation["output_path"]), report)
        review = self.runner.commit()
        self.assertEqual(review["step"], "review")
        write_json(Path(review["output_path"]), {"objections": []})
        result = self.runner.commit()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            self.runner._load_state()["next_action"],
            "retry_report_markdown_materialization",
        )
        self.assertFalse((self.stage_dir / "report.md").exists())


if __name__ == "__main__":
    unittest.main()
