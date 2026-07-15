from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from presentation_agent.io import read_json, write_json
from presentation_agent.renderers.base import RenderResult
from presentation_agent.step import StepRunner, _resolve_global_state_path


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

    def test_manager_nested_task_loads_run_level_delivery_budget(self) -> None:
        run_dir = self.tmp / "manager-run"
        task_dir = run_dir / "tasks" / "report-001_report"
        task_dir.mkdir(parents=True)
        global_state_path = run_dir / "state.json"
        write_json(
            global_state_path,
            {
                "delivery_budget": {
                    "body_page_limit": 3,
                    "report_body_char_limit": 2700,
                    "executive_summary_char_min": 300,
                    "executive_summary_char_max": 350,
                }
            },
        )
        input_path = task_dir / "input.json"
        write_json(input_path, {"report_objective": "nested task test"})
        write_json(
            task_dir / "run_state.json",
            {
                "run_id": "nested-report-test",
                "contract_profile": "v0_3",
                "agent_id": "report",
                "agent_name": "报告产出",
                "stage": 3,
                "status": "init",
                "current_step": "init",
                "round_index": 0,
                "input_path": str(input_path),
                "output_dir": str(task_dir),
                "global_state_path": str(global_state_path),
                "p0_open": [],
                "p1_open": [],
                "produced_artifacts": [],
                "history": [],
            },
        )

        runner = StepRunner(
            ROOT,
            task_dir,
            data_root=self.tmp / "data",
            contract_profile="v0_3",
        )
        render_result = RenderResult(
            status="rendered",
            fmt="markdown",
            fidelity="content",
        )
        audit = {
            "available": True,
            "passed": True,
            "body_page_count": 2,
            "body_page_limit": 3,
            "body_chars": 2000,
            "detail": "正文实际渲染 2 页，限制 3 页",
        }
        with patch(
            "presentation_agent.page_budget.audit_document_body_pages",
            return_value=audit,
        ) as mocked_audit:
            runner._apply_report_body_budget_audit(
                read_json(REPORT_FIXTURE), render_result
            )

        mocked_audit.assert_called_once()
        self.assertEqual(runner.global_state_path, global_state_path)
        self.assertTrue(render_result.metrics["body_budget_audit"]["passed"])

    def test_legacy_manager_task_discovers_run_level_state(self) -> None:
        run_dir = self.tmp / "legacy-manager-run"
        task_dir = run_dir / "tasks" / "report-001_report"
        task_dir.mkdir(parents=True)
        write_json(run_dir / "manager_state.json", {"run_id": "legacy"})
        write_json(run_dir / "state.json", {"delivery_budget": {}})

        self.assertEqual(
            _resolve_global_state_path(task_dir),
            run_dir / "state.json",
        )

    def test_empty_markdown_is_rejected_before_finalize(self) -> None:
        report = read_json(REPORT_FIXTURE)
        report["report_markdown"] = ""
        generation = self.runner.prepare()
        write_json(Path(generation["output_path"]), report)
        result = self.runner.commit()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            self.runner._load_state()["next_action"],
            "retry_report_markdown_materialization",
        )
        self.assertFalse((self.stage_dir / "report.md").exists())

    def test_body_page_preflight_passes_and_is_exposed_in_metrics(self) -> None:
        self.runner.full_global_state["delivery_budget"] = {
            "body_page_limit": 3,
            "body_char_min": 2400,
            "body_char_target": 2550,
            "body_char_warning": 2700,
            "report_body_char_limit": 2700,
            "executive_summary_char_min": 300,
            "executive_summary_char_max": 350,
            "max_body_visuals": 3,
        }
        audit = {
            "stage": "report_preflight",
            "body_page_limit": 3,
            "body_page_count": 3,
            "body_chars": 2700,
            "available": True,
            "passed": True,
            "detail": "正文实际渲染 3 页，限制 3 页",
        }
        with patch(
            "presentation_agent.page_budget.audit_document_body_pages",
            return_value=audit,
        ):
            result = self._finish()
        self.assertEqual(result["status"], "pending_human_review")
        self.assertTrue(
            result["render_result"]["metrics"]["body_budget_audit"]["passed"]
        )

    def test_body_page_preflight_blocks_overlength_report(self) -> None:
        self.runner.full_global_state["delivery_budget"] = {
            "body_page_limit": 3,
            "body_char_min": 2400,
            "body_char_target": 2550,
            "body_char_warning": 2700,
            "report_body_char_limit": 2700,
            "executive_summary_char_min": 300,
            "executive_summary_char_max": 350,
            "max_body_visuals": 3,
        }
        audit = {
            "stage": "report_preflight",
            "body_page_limit": 3,
            "body_page_count": 4,
            "body_chars": 3900,
            "available": True,
            "passed": False,
            "detail": "正文实际渲染 4 页，限制 3 页",
        }
        with patch(
            "presentation_agent.page_budget.audit_document_body_pages",
            return_value=audit,
        ):
            result = self._finish()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            self.runner._load_state()["next_action"],
            "retry_report_markdown_materialization",
        )
        self.assertIn("正文实际渲染 4 页", result["render_result"]["detail"])

    def test_report_text_limit_blocks_even_when_shadow_doc_is_three_pages(self) -> None:
        self.runner.full_global_state["delivery_budget"] = {
            "body_page_limit": 3,
            "body_char_min": 2400,
            "body_char_target": 2550,
            "body_char_warning": 2700,
            "report_body_char_limit": 2700,
            "executive_summary_char_min": 300,
            "executive_summary_char_max": 350,
            "max_body_visuals": 3,
        }
        audit = {
            "stage": "report_preflight",
            "body_page_limit": 3,
            "body_page_count": 3,
            "body_chars": 2701,
            "available": True,
            "passed": True,
            "detail": "正文实际渲染 3 页，限制 3 页",
        }
        with patch(
            "presentation_agent.page_budget.audit_document_body_pages",
            return_value=audit,
        ):
            result = self._finish()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("超过预留视觉空间后的硬上限", result["render_result"]["detail"])

    def test_executive_summary_fixed_range_is_enforced(self) -> None:
        self.runner.full_global_state["delivery_budget"] = {
            "body_page_limit": 3,
            "body_char_min": 2400,
            "body_char_target": 2550,
            "body_char_warning": 2700,
            "report_body_char_limit": 2700,
            "executive_summary_char_min": 300,
            "executive_summary_char_max": 350,
            "max_body_visuals": 3,
        }
        report = read_json(REPORT_FIXTURE)
        summary = report["report_markdown"].split(
            "## Executive Summary\n\n", 1
        )[1].split("\n\n## ", 1)[0]
        report["report_markdown"] = report["report_markdown"].replace(
            summary, "摘要过短。", 1
        )
        audit = {
            "stage": "report_preflight",
            "body_page_limit": 3,
            "body_page_count": 2,
            "body_chars": 2000,
            "available": True,
            "passed": True,
            "detail": "正文实际渲染 2 页，限制 3 页",
        }
        with patch(
            "presentation_agent.page_budget.audit_document_body_pages",
            return_value=audit,
        ):
            result = self._finish(report)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Executive Summary", result["render_result"]["detail"])
        self.assertIn("300–350", result["render_result"]["detail"])


if __name__ == "__main__":
    unittest.main()
