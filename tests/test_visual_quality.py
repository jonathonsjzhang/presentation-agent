from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw

from presentation_agent.renderers.base import RenderResult
from presentation_agent.renderers.visual_quality import (
    audit_render_output,
    renderer_readiness_issues,
)


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
