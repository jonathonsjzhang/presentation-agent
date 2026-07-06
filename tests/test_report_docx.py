from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "v0_3" / "report.v1.valid.json"


class ReportMarkdownArtifactTests(unittest.TestCase):
    def test_report_stage_emits_markdown_not_docx(self) -> None:
        report = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(report["report_file"], "report.md")
        self.assertTrue(report["report_markdown"].startswith("# "))
        self.assertNotIn("content_deliverable", report)
        self.assertNotIn("sections", report)


if __name__ == "__main__":
    unittest.main()
