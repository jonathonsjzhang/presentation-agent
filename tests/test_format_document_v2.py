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
                "执行摘要",
                "34%",
                "非随机分组，不能直接推断因果。",
                "访谈样本只用于机制探索。",
                "Section: S-01 | Claim: C-01 | Evidence: E-Q-01",
                "主张与证据追溯",
            ):
                self.assertIn(text, extracted)
            self.assertTrue(document.inline_shapes)

    def test_rejects_missing_protected_caveat(self) -> None:
        formatted = load(FORMATTED)
        formatted["caveat_preservation"] = formatted["caveat_preservation"][:1]
        with tempfile.TemporaryDirectory() as temp_dir:
            result = render_formatted_document_v2(formatted, load(REPORT), Path(temp_dir))
        self.assertEqual(result.status, "error")
        self.assertIn("protected report caveat", result.detail)

    def test_diagram_matrix_and_callout_use_supplied_data_and_png_fallback(self) -> None:
        formatted = load(FORMATTED)
        extras = [
            {
                "asset_id": "VA-DIAGRAM",
                "asset_type": "diagram",
                "title": "真实机制链路",
                "reader_takeaway": "按报告主张展示机制链路。",
                "data": {"nodes": ["形成成果", "保存成果", "再次复用"]},
                "source_section_ids": ["S-02"],
                "source_claim_ids": ["C-02"],
                "source_evidence_refs": ["E-I-01"],
                "source_note": "来源：报告机制主张。",
                "caveats": ["访谈样本只用于机制探索。"],
                "render_status": "planned",
            },
            {
                "asset_id": "VA-MATRIX",
                "asset_type": "matrix",
                "title": "实验优先级矩阵",
                "reader_takeaway": "矩阵标签来自输入。",
                "data": {"items": ["成果复用", "提醒触达"], "x_label": "证据强度", "y_label": "业务价值"},
                "source_section_ids": ["S-02"],
                "source_claim_ids": ["C-03"],
                "source_evidence_refs": ["E-Q-01", "E-I-01"],
                "source_note": "来源：报告建议。",
                "caveats": [],
                "render_status": "planned",
            },
            {
                "asset_id": "VA-CALLOUT",
                "asset_type": "callout",
                "title": "实验原则",
                "reader_takeaway": "控制初始意愿并设置提醒对照。",
                "data": {},
                "source_section_ids": ["S-02"],
                "source_claim_ids": ["C-03"],
                "source_evidence_refs": ["E-Q-01"],
                "source_note": "来源：报告建议。",
                "caveats": [],
                "render_status": "planned",
            },
        ]
        formatted["visual_assets"].extend(extras)
        formatted["render_plan"]["asset_order"].extend(item["asset_id"] for item in extras)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = render_formatted_document_v2(formatted, load(REPORT), Path(temp_dir))
            self.assertEqual(result.status, "rendered", result.detail)
            asset_dir = Path(temp_dir) / "report_formatted_assets"
            for stem in ("VA-DIAGRAM", "VA-MATRIX"):
                self.assertTrue((asset_dir / f"{stem}.svg").is_file())
                self.assertTrue((asset_dir / f"{stem}.png").is_file())


if __name__ == "__main__":
    unittest.main()
