from __future__ import annotations

import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from presentation_agent.connectors.registry import list_connectors
from presentation_agent.input_loader import load_agent_input
from presentation_agent.loop import LoopRunner


ROOT = Path(__file__).resolve().parents[1]


class ConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        for name in ("configs", "data", "examples", "skills"):
            shutil.copytree(ROOT / name, self.root / name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_csv_connector_feeds_loop_without_main_flow_changes(self) -> None:
        csv_path = self.root / "examples" / "arguments.csv"
        csv_path.write_text(
            "claim,evidence,so_what\n"
            "复杂任务场景拉长用户时长,复杂任务会话占比提升,优先投入复杂任务体验\n",
            encoding="utf-8",
        )

        runner = LoopRunner(self.root, provider_override="mock")
        result = runner.run(
            "argument_synthesis",
            csv_path,
            self.root / "artifacts" / "csv_argument",
        )
        loaded = load_agent_input(csv_path, runner.specs["argument_synthesis"])

        self.assertEqual(result["status"], "pending_human_review")
        self.assertEqual(loaded["source_type"], "csv")
        self.assertEqual(loaded["tables"][0]["columns"], ["claim", "evidence", "so_what"])
        self.assertEqual(loaded["materials"][0]["claim"], "复杂任务场景拉长用户时长")

    def test_xlsx_connector_extracts_sheet_names_and_rows(self) -> None:
        xlsx_path = self.root / "examples" / "metrics.xlsx"
        write_minimal_xlsx(xlsx_path)
        runner = LoopRunner(self.root, provider_override="mock")
        loaded = load_agent_input(xlsx_path, runner.specs["page_filling"])

        self.assertEqual(loaded["source_type"], "xlsx")
        self.assertEqual(loaded["sheets"][0]["name"], "metrics")
        self.assertEqual(loaded["sheets"][0]["rows"][0], ["metric", "value"])
        self.assertEqual(loaded["sheets"][0]["rows"][1], ["avg_duration", "12.5"])
        self.assertTrue(loaded["materials"])

    def test_registry_exposes_file_connectors(self) -> None:
        names = {item["name"] for item in list_connectors()}
        self.assertTrue({"docx_reader", "csv_reader", "xlsx_reader"}.issubset(names))


def write_minimal_xlsx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="metrics" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>metric</t></si>
  <si><t>value</t></si>
  <si><t>avg_duration</t></si>
</sst>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
    <row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>12.5</v></c></row>
  </sheetData>
</worksheet>""",
        )


if __name__ == "__main__":
    unittest.main()
