from __future__ import annotations

import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from presentation_agent.renderers.base import render_material
from presentation_agent.renderers.formatted_document_v2 import render_formatted_document_v2

ROOT = Path(__file__).resolve().parents[1]
FORMATTED = ROOT / "tests/fixtures/v0_3/formatted_material.v2.valid.json"
REPORT = ROOT / "tests/fixtures/v0_3/report.v1.valid.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class FormattedDocumentV2Tests(unittest.TestCase):
    def test_dispatcher_renders_all_v2_targets(self) -> None:
        report = load(REPORT)
        for target, suffix in (
            ("document", ".docx"),
            ("html", ".html"),
            ("ppt", ".pptx"),
        ):
            formatted = load(FORMATTED)
            formatted["delivery_target"] = target
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temp_dir:
                result = render_material(
                    formatted,
                    Path(temp_dir),
                    source_report=report,
                    expected_format=target,
                )
                self.assertEqual(result.status, "rendered", result.detail)
                self.assertTrue(str(result.output_path).endswith(suffix))
                self.assertTrue(Path(str(result.output_path)).is_file())

    def test_fixture_renders_polished_traceable_docx(self) -> None:
        from docx import Document

        with tempfile.TemporaryDirectory() as temp_dir:
            result = render_formatted_document_v2(load(FORMATTED), load(REPORT), Path(temp_dir))
            self.assertEqual(result.status, "rendered", result.detail)
            output = Path(result.output_path or "")
            self.assertTrue(output.is_file())
            with zipfile.ZipFile(output) as package:
                self.assertIn("word/document.xml", package.namelist())
                xml = package.read("word/document.xml").decode("utf-8")
                self.assertIn("目录", xml)
                self.assertIn("方法与边界", xml)
                footer_xml = "".join(
                    package.read(name).decode("utf-8")
                    for name in package.namelist()
                    if name.startswith("word/footer") and name.endswith(".xml")
                )
                self.assertIn("PAGE", footer_xml)
            document = Document(output)
            extracted = "\n".join(p.text for p in document.paragraphs)
            extracted += "\n" + "\n".join(
                cell.text for table in document.tables for row in table.rows for cell in row.cells
            )
            for text in (
                "AI 助手用户留存改善机会",
                "目录",
                "Executive Summary",
                "34%",
                "Section: 一、成果保存与回访共同出现，但因果仍待验证",
                "Evidence: E-Q-01",
                "结论与战略含义",
            ):
                self.assertIn(text, extracted)
            self.assertTrue(document.inline_shapes)

    def test_renderer_does_not_require_worker_generated_caveat_register(self) -> None:
        formatted = load(FORMATTED)
        formatted.pop("caveat_preservation")
        with tempfile.TemporaryDirectory() as temp_dir:
            result = render_formatted_document_v2(formatted, load(REPORT), Path(temp_dir))
        self.assertEqual(result.status, "rendered", result.detail)

    def test_empty_chart_falls_back_to_callout(self) -> None:
        formatted = load(FORMATTED)
        formatted["visuals"][0]["type"] = "chart"
        formatted["visuals"][0]["data"] = {
            "categories": [],
            "values": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            result = render_formatted_document_v2(
                formatted,
                load(REPORT),
                Path(temp_dir),
            )
        self.assertEqual(result.status, "rendered", result.detail)

    def test_matrix_and_callout_use_supplied_data_and_png_fallback(self) -> None:
        formatted = load(FORMATTED)
        extras = [
            {
                "section_heading": "二、可复用成果提供了值得优先验证的回访理由",
                "type": "matrix",
                "title": "实验优先级矩阵",
                "data": {"items": ["成果复用", "提醒触达"], "x_label": "证据强度", "y_label": "业务价值"},
                "source_refs": ["E-Q-01", "E-I-01"]
            },
            {
                "section_heading": "二、可复用成果提供了值得优先验证的回访理由",
                "type": "callout",
                "title": "实验原则",
                "data": {},
                "source_refs": ["E-Q-01"]
            },
        ]
        formatted["visuals"].extend(extras)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = render_formatted_document_v2(formatted, load(REPORT), Path(temp_dir))
            self.assertEqual(result.status, "rendered", result.detail)
            asset_dir = Path(temp_dir) / "report_formatted_assets"
            self.assertTrue((asset_dir / "VIS-02.svg").is_file())
            self.assertTrue((asset_dir / "VIS-02.png").is_file())


if __name__ == "__main__":
    unittest.main()
