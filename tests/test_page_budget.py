from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from presentation_agent.page_budget import (
    audit_document_body_pages,
    body_character_count,
    derive_delivery_budget,
    executive_summary_character_count,
    extract_body_markdown,
    parse_body_page_limit,
)
from presentation_agent.renderers.base import RenderResult
from presentation_agent.step import StepRunner


class PageBudgetTests(unittest.TestCase):
    def test_parses_document_body_limit_and_ignores_ppt(self) -> None:
        charter = {
            "report_length": "3页文档",
            "requested_delivery_targets": ["document"],
        }
        self.assertEqual(parse_body_page_limit(charter), 3)
        self.assertEqual(
            derive_delivery_budget(charter),
            {
                "requested_body_page_limit": 3,
                "body_page_limit": 3,
                "automatic_page_tolerance": 1,
                "automatic_body_page_limit": 4,
                "maximum_body_page_limit": 4,
                "counting_policy": "body_only",
                "excluded_section_roles": ["methods_and_limitations", "qa"],
                "body_char_min": 2400,
                "body_char_target": 2550,
                "body_char_warning": 2700,
                "report_body_char_limit": 3600,
                "body_char_enforcement": "advisory",
                "max_body_visuals": 3,
                "appendix_policy": "allowed",
                "qa_included": True,
            },
        )
        self.assertIsNone(
            parse_body_page_limit(
                {
                    "report_length": "10页PPT",
                    "requested_delivery_targets": ["ppt"],
                }
            )
        )

    def test_scales_report_text_budget_linearly_without_fixed_summary_band(self) -> None:
        five_pages = derive_delivery_budget(
            {
                "report_length": "5页文档",
                "requested_delivery_targets": ["document"],
            }
        )
        six_pages = derive_delivery_budget(
            {
                "report_length": "6页文档",
                "requested_delivery_targets": ["document"],
            }
        )
        self.assertEqual(
            (five_pages["body_char_min"], five_pages["body_char_target"], five_pages["report_body_char_limit"]),
            (4000, 4250, 5400),
        )
        self.assertEqual(
            (six_pages["body_char_min"], six_pages["body_char_target"], six_pages["report_body_char_limit"]),
            (4800, 5100, 6300),
        )
        self.assertNotIn("executive_summary_char_min", five_pages)
        self.assertNotIn("executive_summary_char_max", six_pages)

    def test_explicit_page_budget_distinguishes_body_and_total_pages(self) -> None:
        budget = derive_delivery_budget(
            {
                "requested_delivery_targets": ["document"],
                "page_budget": {
                    "body_page_limit": 3,
                    "total_page_limit": 6,
                    "appendix_policy": "forbidden",
                    "qa_included": False,
                },
            }
        )
        self.assertEqual(budget["body_page_limit"], 3)
        self.assertEqual(budget["total_page_limit"], 6)
        self.assertEqual(budget["appendix_policy"], "forbidden")
        self.assertFalse(budget["qa_included"])

    def test_format_total_page_limit_is_a_hard_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = object.__new__(StepRunner)
            runner.run_dir = Path(temp_dir)
            runner._delivery_budget = lambda: {  # type: ignore[method-assign]
                "body_page_limit": 3,
                "maximum_body_page_limit": 4,
                "total_page_limit": 6,
            }
            result = RenderResult(
                status="rendered",
                fmt="document",
                fidelity="formatted",
                output_path=str(Path(temp_dir) / "report.docx"),
            )
            body_audit = {
                "passed": True,
                "requires_user_decision": False,
                "detail": "正文实际 3 页",
            }
            with patch(
                "presentation_agent.page_budget.audit_document_body_pages",
                return_value=body_audit,
            ), patch(
                "presentation_agent.page_budget.count_docx_pages",
                return_value=7,
            ):
                runner._apply_format_body_budget_audit(
                    {"delivery_target": "document", "visuals": []},
                    {"report_markdown": "# 报告"},
                    result,
                )
            audit = result.metrics["body_budget_audit"]
            self.assertEqual(audit["total_page_count"], 7)
            self.assertFalse(audit["total_pages_passed"])
            self.assertEqual(result.status, "error")

    def test_extracts_body_but_preserves_methods_and_qa_in_source(self) -> None:
        markdown = (
            "# 标题\n\n"
            "## Executive Summary\n\n摘要\n\n"
            "## 一、主体判断\n\n正文证据\n\n"
            "## 方法与边界\n\n方法内容\n\n"
            "## 听众可能追问的问题\n\n1. 问题？\n"
        )
        body = extract_body_markdown(markdown)
        self.assertIn("# 标题", body)
        self.assertIn("## Executive Summary", body)
        self.assertIn("## 一、主体判断", body)
        self.assertNotIn("方法与边界", body)
        self.assertNotIn("听众可能追问的问题", body)
        self.assertIn("方法与边界", markdown)
        self.assertGreater(body_character_count(markdown), 0)

    def test_counts_executive_summary_only(self) -> None:
        markdown = (
            "# 标题\n\n## Executive Summary\n\n摘要内容。\n\n"
            "## 一、主体判断\n\n正文内容。\n"
        )
        self.assertEqual(
            executive_summary_character_count(markdown), len("摘要内容。")
        )

    def test_counts_bullet_summary_content_without_markdown_markers(self) -> None:
        markdown = (
            "# 标题\n\n## Executive Summary\n\n"
            "- **用户时长接近翻倍：** 过去一年增长94%。\n"
            "  - 使用频次提升66%。\n"
            "- **增长来自复杂任务：** 办公和创作贡献更高时长。\n\n"
            "## 一、主体判断\n\n正文内容。\n"
        )
        expected = len(
            "用户时长接近翻倍：过去一年增长94%。"
            "使用频次提升66%。"
            "增长来自复杂任务：办公和创作贡献更高时长。"
        )
        self.assertEqual(executive_summary_character_count(markdown), expected)

    def test_audit_uses_body_only_report_and_filters_excluded_visuals(self) -> None:
        captured: dict = {}

        def fake_renderer(formatted, report, out_dir, *, file_stem):
            captured["formatted"] = formatted
            captured["report"] = report
            return RenderResult(
                status="rendered",
                fmt="document",
                fidelity="formatted",
                output_path=str(Path(out_dir) / f"{file_stem}.docx"),
            )

        report = {
            "agent_id": "qa_preparation",
            "schema": "report.v1",
            "report_markdown": (
                "# 标题\n\n## Executive Summary\n\n摘要\n\n"
                "## 一、主体判断\n\n正文\n\n"
                "## 方法与边界\n\n方法\n\n"
                "## 听众可能追问的问题\n\n1. 问题？\n"
            ),
        }
        formatted = {
            "agent_id": "format",
            "schema": "formatted_material.v2",
            "delivery_target": "document",
            "visuals": [
                {"section_heading": "一、主体判断", "type": "chart"},
                {"section_heading": "方法与边界", "type": "callout"},
                {"section_heading": "听众可能追问的问题", "type": "callout"},
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            audit = audit_document_body_pages(
                report=report,
                formatted=formatted,
                out_dir=Path(temp_dir),
                body_page_limit=3,
                stage="format_final",
                renderer=fake_renderer,
                page_counter=lambda _: 3,
            )
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["body_page_count"], 3)
        self.assertEqual(audit["visual_count"], 1)
        self.assertNotIn("方法与边界", captured["report"]["report_markdown"])
        self.assertEqual(len(captured["formatted"]["visuals"]), 1)

    def test_audit_automatically_allows_one_extra_page(self) -> None:
        def fake_renderer(formatted, report, out_dir, *, file_stem):
            return RenderResult(
                status="rendered",
                fmt="document",
                fidelity="formatted",
                output_path=str(Path(out_dir) / f"{file_stem}.docx"),
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            audit = audit_document_body_pages(
                report={
                    "agent_id": "report",
                    "schema": "report.v1",
                    "report_markdown": "# 标题\n\n## Executive Summary\n\n摘要\n",
                },
                formatted={"visuals": []},
                out_dir=Path(temp_dir),
                body_page_limit=3,
                stage="report_preflight",
                renderer=fake_renderer,
                page_counter=lambda _: 4,
            )
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["body_page_count"], 4)
        self.assertTrue(audit["automatic_tolerance_used"])
        self.assertFalse(audit["requires_user_decision"])

    def test_audit_requires_user_decision_beyond_one_extra_page(self) -> None:
        def fake_renderer(formatted, report, out_dir, *, file_stem):
            return RenderResult(
                status="rendered",
                fmt="document",
                fidelity="formatted",
                output_path=str(Path(out_dir) / f"{file_stem}.docx"),
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            audit = audit_document_body_pages(
                report={
                    "agent_id": "report",
                    "schema": "report.v1",
                    "report_markdown": "# 标题\n\n## Executive Summary\n\n摘要\n",
                },
                formatted={"visuals": []},
                out_dir=Path(temp_dir),
                body_page_limit=3,
                maximum_body_page_limit=4,
                stage="report_preflight",
                renderer=fake_renderer,
                page_counter=lambda _: 5,
            )
        self.assertFalse(audit["passed"])
        self.assertTrue(audit["requires_user_decision"])
        self.assertEqual(audit["maximum_body_page_limit"], 4)

    def test_audit_distinguishes_automatic_and_user_approved_limits(self) -> None:
        def fake_renderer(formatted, report, out_dir, *, file_stem):
            return RenderResult(
                status="rendered",
                fmt="document",
                fidelity="formatted",
                output_path=str(Path(out_dir) / f"{file_stem}.docx"),
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            audit = audit_document_body_pages(
                report={
                    "agent_id": "format",
                    "schema": "report.v1",
                    "report_markdown": "# 标题\n\n## Executive Summary\n\n摘要\n",
                },
                formatted={"visuals": []},
                out_dir=Path(temp_dir),
                body_page_limit=3,
                maximum_body_page_limit=5,
                user_approved_body_page_limit=5,
                stage="format_final",
                renderer=fake_renderer,
                page_counter=lambda _: 6,
            )
        self.assertEqual(audit["automatic_body_page_limit"], 4)
        self.assertEqual(audit["user_approved_body_page_limit"], 5)
        self.assertIn("用户批准上限 5 页", audit["detail"])

    def test_format_final_audit_marks_render_error_when_body_overflows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = object.__new__(StepRunner)
            runner.run_dir = Path(temp_dir)
            runner.full_global_state = {
                "delivery_budget": {"body_page_limit": 3, "max_body_visuals": 3}
            }
            render_result = RenderResult(
                status="rendered",
                fmt="document",
                fidelity="formatted",
                output_path=str(Path(temp_dir) / "report.docx"),
            )
            audit = {
                "stage": "format_final",
                "body_page_limit": 3,
                "body_page_count": 4,
                "available": True,
                "passed": False,
                "detail": "正文实际渲染 4 页，限制 3 页",
            }
            with patch(
                "presentation_agent.page_budget.audit_document_body_pages",
                return_value=audit,
            ):
                runner._apply_format_body_budget_audit(
                    {"delivery_target": "document", "visuals": []},
                    {
                        "agent_id": "qa_preparation",
                        "schema": "report.v1",
                        "report_markdown": "# 标题\n\n## Executive Summary\n\n摘要\n",
                    },
                    render_result,
                )
        self.assertEqual(render_result.status, "error")
        self.assertFalse(
            render_result.metrics["body_budget_audit"]["passed"]
        )
        self.assertIn("正文实际渲染 4 页", render_result.detail)


if __name__ == "__main__":
    unittest.main()
