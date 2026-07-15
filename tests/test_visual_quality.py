from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw

from presentation_agent.io import read_json, write_json
from presentation_agent.renderers.base import RenderResult
from presentation_agent.renderers.visual_quality import (
    audit_render_output,
    renderer_readiness_issues,
)
from presentation_agent.step import StepRunner


ROOT = Path(__file__).resolve().parents[1]


class VisualQualityTests(unittest.TestCase):
    def test_renderer_readiness_rejects_empty_matrix_and_callout(self) -> None:
        issues = renderer_readiness_issues(
            [
                {
                    "type": "matrix",
                    "title": "空矩阵",
                    "source_refs": ["E1"],
                    "data": {"items": ["A", "B"]},
                },
                {
                    "type": "callout",
                    "title": "空提示",
                    "source_refs": ["E2"],
                    "data": {},
                },
            ]
        )
        self.assertTrue(any("恰好 4 个" in issue for issue in issues))
        self.assertTrue(any("text/quote" in issue for issue in issues))

    def test_renderer_readiness_accepts_native_chart_and_matrix(self) -> None:
        self.assertEqual(
            renderer_readiness_issues(
                [
                    {
                        "type": "chart",
                        "title": "趋势",
                        "source_refs": ["E1"],
                        "data": {
                            "chart_type": "line",
                            "categories": ["1月", "2月"],
                            "series": [{"name": "时长", "values": [8, 12]}],
                        },
                    },
                    {
                        "type": "matrix",
                        "title": "边界",
                        "source_refs": ["E2"],
                        "data": {"dimensions": ["A", "B", "C", "D"]},
                    },
                ]
            ),
            [],
        )

    def test_post_render_audit_passes_real_non_empty_asset_and_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "report_formatted.docx"
            output.write_bytes(b"docx-placeholder")
            asset = root / "report_formatted_assets" / "VIS-01.png"
            page = root / "page-001.png"
            self._meaningful_image(asset, (600, 300))
            self._meaningful_image(page, (800, 1000))
            prepared = SimpleNamespace(
                warnings=[],
                contact_sheet_path=str(root / "contact-sheet.png"),
                visual_paths=[str(page)],
            )
            with patch(
                "presentation_agent.evaluation.adapters.prepare_artifact",
                return_value=prepared,
            ):
                audit = audit_render_output(
                    self._material(),
                    self._render_result(output),
                    root,
                )
            self.assertTrue(audit["passed"], audit["issues"])
            self.assertEqual(len(audit["inspected_assets"]), 1)
            self.assertEqual(len(audit["inspected_pages"]), 1)

    def test_post_render_audit_blocks_blank_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "report_formatted.docx"
            output.write_bytes(b"docx-placeholder")
            asset = root / "report_formatted_assets" / "VIS-01.png"
            asset.parent.mkdir(parents=True)
            Image.new("RGB", (600, 300), "white").save(asset)
            page = root / "page-001.png"
            self._meaningful_image(page, (800, 1000))
            prepared = SimpleNamespace(
                warnings=[], contact_sheet_path=None, visual_paths=[str(page)]
            )
            with patch(
                "presentation_agent.evaluation.adapters.prepare_artifact",
                return_value=prepared,
            ):
                audit = audit_render_output(
                    self._material(), self._render_result(output), root
                )
            self.assertFalse(audit["passed"])
            self.assertIn("near_blank_raster", self._codes(audit))

    def test_post_render_audit_blocks_black_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "report_formatted.docx"
            output.write_bytes(b"docx-placeholder")
            asset = root / "report_formatted_assets" / "VIS-01.png"
            self._meaningful_image(asset, (600, 300))
            page = root / "page-001.png"
            Image.new("RGB", (800, 1000), "black").save(page)
            prepared = SimpleNamespace(
                warnings=[], contact_sheet_path=None, visual_paths=[str(page)]
            )
            with patch(
                "presentation_agent.evaluation.adapters.prepare_artifact",
                return_value=prepared,
            ):
                audit = audit_render_output(
                    self._material(), self._render_result(output), root
                )
            self.assertFalse(audit["passed"])
            self.assertIn("near_black_raster", self._codes(audit))

    def test_v04_format_commit_persists_real_page_quality_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "handoff").mkdir()
            write_json(
                root / "input.json",
                {
                    "contract_profile": "v0_4",
                    "delivery_target": "document",
                    "report_markdown": (
                        "# 测试报告\n\n## Executive Summary\n\n"
                        "留存率由 20% 提升到 30%。\n"
                    ),
                    "brief": {
                        "title": "测试报告",
                        "audience": "strategy_lead",
                        "purpose": "decision_support",
                    },
                    "audience": "strategy_lead",
                    "purpose": "decision_support",
                    "input_readiness": {"status": "ready"},
                    "manager_task": {"agent_id": "format"},
                    "evidence_assets": [
                        {
                            "evidence_id": "E1",
                            "asset_id": "T1-retention",
                            "ref": "E1:T1-retention",
                            "chart_ready": True,
                            "chart_data": {
                                "chart_type": "bar",
                                "categories": ["之前", "现在"],
                                "values": [20, 30],
                            },
                        }
                    ],
                },
            )
            write_json(
                root / "run_state.json",
                {
                    "run_id": "visual-quality-integration",
                    "task_id": "format-1",
                    "agent_id": "format",
                    "agent_name": "Format",
                    "stage": 5,
                    "status": "running",
                    "current_step": "awaiting_gen_output",
                    "round_index": 0,
                    "input_path": str(root / "input.json"),
                    "produced_artifacts": [],
                    "history": [],
                    "p0_open": [],
                    "p1_open": [],
                    "contract_profile": "v0_4",
                    "review_subagents_enabled": False,
                },
            )
            write_json(
                root / "handoff" / "output_gen.json",
                {
                    "visuals": [
                        {
                            "type": "chart",
                            "title": "留存率提升",
                            "source_refs": ["E1:T1-retention"],
                            "after_heading": "Executive Summary",
                        }
                    ]
                },
            )
            result = StepRunner(
                ROOT,
                root,
                data_root=root / "data",
                contract_profile="v0_4",
            ).commit()
            artifact = read_json(root / "artifact.json")
            audit = read_json(Path(artifact["visual_quality_manifest_path"]))
            self.assertEqual(result["status"], "pending_human_review")
            self.assertTrue(audit["passed"], audit["issues"])
            self.assertTrue(audit["inspected_assets"])
            self.assertTrue(audit["inspected_pages"])

    @staticmethod
    def _material() -> dict:
        return {
            "visuals": [
                {
                    "visual_evidence_id": "VIS-01",
                    "type": "chart",
                    "title": "趋势",
                    "source_refs": ["E1"],
                    "data": {"categories": ["A"], "values": [1]},
                }
            ]
        }

    @staticmethod
    def _render_result(output: Path) -> RenderResult:
        return RenderResult(
            status="rendered",
            fmt="document",
            fidelity="formatted",
            output_path=str(output),
        )

    @staticmethod
    def _meaningful_image(path: Path, size: tuple[int, int]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", size, "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            (size[0] // 8, size[1] // 8, size[0] * 7 // 8, size[1] * 7 // 8),
            fill="#006BA6",
        )
        image.save(path)

    @staticmethod
    def _codes(audit: dict) -> set[str]:
        return {str(item.get("code")) for item in audit.get("issues") or []}


if __name__ == "__main__":
    unittest.main()
