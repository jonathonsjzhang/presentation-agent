from __future__ import annotations

import unittest

from presentation_agent.visual_evidence import (
    audit_required_visual_evidence,
    revision_requests_from_audit,
)


class VisualEvidenceAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = {
            "schema": "report.v1",
            "report_markdown": (
                "# 用户时长分析\n\n## Executive Summary\n\n"
                "用户时长持续上升。\n\n[可视化论据：VE-01]\n"
            ),
            "visual_evidence_placements": [
                {
                    "id": "VE-01",
                    "claim": "用户时长持续上升",
                    "purpose": "展示完整历史变化",
                    "evidence_refs": ["E-01"],
                    "data_asset_refs": ["E-01:daily_duration"],
                    "data_type": "time_series",
                    "required": True,
                    "placement": "opening",
                    "section_heading": "Executive Summary",
                    "marker": "[可视化论据：VE-01]",
                }
            ],
        }

    def test_required_time_series_passes_with_complete_chart_data(self) -> None:
        formatted = {
            "visuals": [
                {
                    "visual_evidence_id": "VE-01",
                    "section_heading": "Executive Summary",
                    "type": "chart",
                    "title": "历史用户时长变化",
                    "source_refs": ["E-01:daily_duration"],
                    "required": True,
                    "placement": "opening",
                    "data": {
                        "chart_type": "line",
                        "categories": ["2026-01", "2026-02", "2026-03"],
                        "series": [{"name": "用户时长", "values": [8.3, 10.7, 15.0]}],
                    },
                }
            ]
        }
        audit = audit_required_visual_evidence(formatted, self.report)
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["resolved_count"], 1)

    def test_missing_data_blocks_and_requests_evidence_repair(self) -> None:
        formatted = {
            "visuals": [
                {
                    "visual_evidence_id": "VE-01",
                    "section_heading": "Executive Summary",
                    "type": "chart",
                    "title": "历史用户时长变化",
                    "source_refs": ["E-01"],
                    "required": True,
                    "placement": "opening",
                    "data": {},
                }
            ]
        }
        audit = audit_required_visual_evidence(formatted, self.report)
        self.assertFalse(audit["passed"])
        self.assertIn("缺少可绘制的完整数据", audit["issues"][0]["reason"])
        requests = revision_requests_from_audit(audit)
        self.assertEqual(requests[0]["target_agent"], "evidence_harvester")
        self.assertEqual(requests[0]["blocking_level"], "blocking")

    def test_missing_format_visual_is_not_silently_ignored(self) -> None:
        audit = audit_required_visual_evidence({"visuals": []}, self.report)
        self.assertFalse(audit["passed"])
        self.assertIn("没有生成", audit["issues"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
