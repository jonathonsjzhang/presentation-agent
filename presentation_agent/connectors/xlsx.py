from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from presentation_agent.connectors.base import ConnectorContext, SuffixConnector


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"x": MAIN_NS, "r": REL_NS, "rel": PKG_REL_NS}


class XlsxConnector(SuffixConnector):
    name = "xlsx_reader"
    suffixes = (".xlsx",)

    def load(self, path: Path, context: ConnectorContext) -> dict[str, Any]:
        workbook = read_xlsx_workbook(path)
        return {
            "topic": path.stem,
            "source_path": str(path),
            "source_type": "xlsx",
            "target_agent": context.agent_id,
            "parsing_note": "Minimal stdlib XLSX parser; formulas/styles/charts are not evaluated.",
            "sheets": workbook,
            "materials": sheets_to_materials(workbook),
        }


def read_xlsx_workbook(path: Path) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "xl/workbook.xml" not in names:
            raise ValueError(f"Unsupported XLSX: missing xl/workbook.xml in {path}")
        shared_strings = read_shared_strings(archive, names)
        rels = read_workbook_relationships(archive, names)
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets: list[dict[str, Any]] = []
        for sheet in workbook_root.findall(".//x:sheet", NS):
            name = sheet.attrib.get("name", "")
            rel_id = sheet.attrib.get(f"{{{REL_NS}}}id", "")
            target = rels.get(rel_id)
            rows: list[list[str]] = []
            if target:
                worksheet_path = "xl/" + target.lstrip("/")
                if worksheet_path in names:
                    rows = read_worksheet_rows(archive.read(worksheet_path), shared_strings)
            sheets.append(
                {
                    "name": name,
                    "row_count": len(rows),
                    "rows": rows,
                    "columns": rows[0] if rows else [],
                }
            )
        return sheets


def read_shared_strings(archive: zipfile.ZipFile, names: set[str]) -> list[str]:
    if "xl/sharedStrings.xml" not in names:
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall(".//x:si", NS):
        text = "".join(node.text or "" for node in item.findall(".//x:t", NS))
        strings.append(text)
    return strings


def read_workbook_relationships(archive: zipfile.ZipFile, names: set[str]) -> dict[str, str]:
    if "xl/_rels/workbook.xml.rels" not in names:
        return {}
    root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rels: dict[str, str] = {}
    for rel in root.findall(".//rel:Relationship", NS):
        rel_id = rel.attrib.get("Id", "")
        target = rel.attrib.get("Target", "")
        if rel_id and target:
            rels[rel_id] = target
    return rels


def read_worksheet_rows(raw_xml: bytes, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(raw_xml)
    rows: list[list[str]] = []
    for row in root.findall(".//x:sheetData/x:row", NS):
        values_by_col: dict[int, str] = {}
        for cell in row.findall("x:c", NS):
            ref = cell.attrib.get("r", "")
            col_index = column_index(ref) if ref else len(values_by_col)
            values_by_col[col_index] = read_cell_value(cell, shared_strings)
        if values_by_col:
            max_col = max(values_by_col)
            rows.append([values_by_col.get(index, "") for index in range(max_col + 1)])
    return rows


def read_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", NS)).strip()
    value_node = cell.find("x:v", NS)
    if value_node is None or value_node.text is None:
        return ""
    value = value_node.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (IndexError, ValueError):
            return value
    return value


def column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref.upper())
    if not match:
        return 0
    index = 0
    for char in match.group(1):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def sheets_to_materials(sheets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []
    for sheet in sheets:
        rows = sheet.get("rows", [])
        if not rows:
            continue
        columns = [str(item) for item in rows[0]]
        for row_index, row in enumerate(rows[1:], start=2):
            pairs = [
                f"{columns[i] or f'列{i + 1}'}={value}"
                for i, value in enumerate(row)
                if str(value).strip()
            ]
            if pairs:
                materials.append(
                    {
                        "claim": f"{sheet['name']} 第 {row_index} 行数据",
                        "key_question": "这条表格记录说明了什么关键判断？",
                        "evidence": ["；".join(pairs)],
                        "so_what": "需要结合汇报目标提炼管理层含义。",
                        "tag": "mainline",
                        "source_sheet": sheet["name"],
                        "source_row": row_index,
                    }
                )
    return materials
