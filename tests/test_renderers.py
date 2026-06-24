"""Tests for the render backends (renderers/) and StepRunner render wiring.

These tests assert that:
- render_material produces real files for ppt / html / document,
- draft and final fidelity differ,
- missing units / unknown formats degrade safely,
- StepRunner._render_deliverable dispatches by agent_id and never crashes.

python-pptx / python-docx are OPTIONAL: when missing, the backend returns a
`skipped_missing_dep` RenderResult, which these tests accept as a valid outcome
so the suite stays green in minimal environments.
"""
from __future__ import annotations

import tempfile
import unittest
from zipfile import ZipFile
from pathlib import Path

from presentation_agent.renderers import RenderResult, render_material
from presentation_agent.renderers.html import build_html_document


def _units():
    return [
        {
            "unit_id": "u1",
            "source_page_no": 1,
            "headline": "存量复购是下半年最高 ROI 的增长抓手",
            "layout_or_structure": {"layout_type": "cover"},
            "finalized_content": {"body": "2026 H1 战略复盘", "author": "战略部", "date": "2026-06"},
        },
        {
            "unit_id": "u2",
            "source_page_no": 2,
            "headline": "三大结论决定资源投放优先级",
            "layout_or_structure": {"layout_type": "executive_summary"},
            "finalized_content": {
                "supporting_points": ["复购：贡献 58% GMV", "拉新：CAC 上升 27%", "履约：NPS 待补"],
                "source": "经营数据 2026 H1",
            },
        },
        {
            "unit_id": "u3",
            "source_page_no": 3,
            "headline": "GMV 结构显示存量用户是绝对主力",
            "layout_or_structure": {"layout_type": "donut"},
            "visual_object": {
                "visual_type": "donut",
                "data_fields": [
                    {"label": "会员复购", "value": 62},
                    {"label": "新客首单", "value": 23},
                    {"label": "活动拉动", "value": 15},
                ],
            },
            "finalized_content": {"source": "GMV 拆解"},
        },
        {
            "unit_id": "u4",
            "source_page_no": 4,
            "headline": "下半年分三步落地会员增长",
            "layout_or_structure": {"layout_type": "closing"},
            "finalized_content": {"body": "Q3 搭体系 · Q4 提复购"},
        },
    ]


def _material(fmt: str) -> dict:
    return {"format": fmt, "topic": "增长复盘", "material_units": _units()}


def _chart_units():
    def unit(idx, layout, spec, title):
        return {
            "unit_id": f"c{idx}",
            "source_page_no": idx,
            "unit_type": "slide",
            "headline": title,
            "layout_or_structure": {"layout_type": layout},
            "finalized_content": {"primary_text": title, "source": "测试数据"},
            "visual_object": {
                "visual_type": layout,
                "reader_takeaway": "测试 takeaway",
                "chart_spec": spec,
            },
            "source_display": {"footer": "Source: smoke test"},
            "gap_display": {},
            "quality_status": "render_ready",
        }

    return [
        unit(1, "cover", {}, "复杂图表渲染能力验证"),
        unit(
            2,
            "grouped_bar",
            {
                "categories": ["Q1", "Q2", "Q3"],
                "series": ["A", "B"],
                "values": [[10, 8], [15, 11], [18, 16]],
                "summary": ["结论", "A 系列持续领先"],
            },
            "分组柱状图显示 A 系列持续领先",
        ),
        unit(
            3,
            "stacked_bar",
            {
                "periods": ["5月", "6月", "7月"],
                "series": ["拉新", "复购", "活动"],
                "values": [[30, 50, 20], [25, 55, 20], [20, 60, 20]],
                "summary": ["结构", "复购贡献提升"],
            },
            "堆叠柱状图显示复购贡献提升",
        ),
        unit(
            4,
            "horizontal_bar",
            {"items": [{"name": "产品 A", "value": 82}, {"name": "产品 B", "value": 61}]},
            "横向条形图凸显 产品 A 使用强度最高",
        ),
        unit(
            5,
            "multi_bar_panel",
            {
                "panels": [
                    {
                        "title": "产品 A **领先**",
                        "unit": "分钟",
                        "legend": "人均时长",
                        "categories": ["5月", "6月", "7月"],
                        "values": [18, 24, 31],
                        "highlight_idx": [2],
                    },
                    {
                        "title": "产品 B **追赶**",
                        "unit": "分钟",
                        "legend": "人均时长",
                        "categories": ["5月", "6月", "7月"],
                        "values": [8, 13, 17],
                        "highlight_idx": [2],
                    },
                ]
            },
            "多面板柱状图显示 产品 A 领先且产品 B 追赶",
        ),
    ]


def _chart_material() -> dict:
    return {"format": "ppt", "topic": "复杂图表测试", "material_units": _chart_units()}


_OK = {"rendered", "skipped_missing_dep"}


class RenderMaterialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _assert_rendered_or_skipped(self, res: RenderResult, fmt: str, unit_count: int | None = None):
        self.assertIsInstance(res, RenderResult)
        self.assertEqual(res.fmt, fmt)
        self.assertIn(res.status, _OK, f"unexpected status {res.status}: {res.detail}")
        if res.status == "rendered":
            self.assertTrue(res.output_path and Path(res.output_path).exists())
            self.assertGreater(res.file_bytes, 0)
            self.assertEqual(res.unit_count, unit_count or len(_units()))

    def test_ppt_render(self):
        res = render_material(_material("ppt"), self.tmp, fidelity="final", file_stem="t")
        self._assert_rendered_or_skipped(res, "ppt")

    def test_ppt_complex_chart_layouts_render(self):
        res = render_material(_chart_material(), self.tmp, fidelity="final", file_stem="charts")
        self._assert_rendered_or_skipped(res, "ppt", unit_count=len(_chart_units()))
        if res.status == "rendered":
            self.assertFalse(res.degraded, res.degraded_units)
            self.assertIn("mck_ppt shape-native PPT", res.warnings)

    def test_html_render(self):
        # HTML backend has zero deps; must always render.
        res = render_material(_material("html"), self.tmp, fidelity="final", file_stem="t")
        self.assertEqual(res.status, "rendered")
        self.assertTrue(Path(res.output_path).exists())
        self.assertTrue(res.output_path.endswith("_final.html"))

    def test_docx_render(self):
        res = render_material(_material("document"), self.tmp, fidelity="final", file_stem="t")
        self._assert_rendered_or_skipped(res, "document")
        if res.status == "rendered":
            with ZipFile(res.output_path) as zf:
                media = [n for n in zf.namelist() if n.startswith("word/media/")]
            self.assertTrue(media, "document chart units should embed a figure image")

    def test_html_draft_vs_final_differ(self):
        draft = render_material(_material("html"), self.tmp, fidelity="draft", file_stem="t")
        final = render_material(_material("html"), self.tmp, fidelity="final", file_stem="t")
        self.assertEqual(draft.status, "rendered")
        self.assertEqual(final.status, "rendered")
        self.assertNotEqual(draft.output_path, final.output_path)
        draft_html = Path(draft.output_path).read_text(encoding="utf-8")
        self.assertIn("草稿", draft_html)  # draft watermark

    def test_html_ppt_export_mode_uses_slide_canvas(self):
        html = build_html_document(_material("ppt"), fidelity="final", export_mode="ppt")
        self.assertIn("ppt-export", html)
        self.assertIn("width:1600px", html)
        self.assertIn("height:900px", html)

    def test_no_units(self):
        res = render_material({"format": "ppt", "material_units": []}, self.tmp)
        self.assertEqual(res.status, "no_units")

    def test_format_alias(self):
        # pptx / doc / docx aliases route to the right backend
        for fmt, expect in (("pptx", "ppt"), ("doc", "document"), ("docx", "document")):
            res = render_material(_material(fmt), self.tmp, file_stem="alias")
            self.assertEqual(res.fmt, expect)


class StepRenderWiringTests(unittest.TestCase):
    """_render_deliverable dispatches by agent_id without a full commit cycle."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = Path(__file__).resolve().parent.parent

    def _runner(self, agent_id: str):
        # Build a minimal StepRunner-like object: we only need spec.id + run_dir.
        from presentation_agent.step import StepRunner

        runner = StepRunner.__new__(StepRunner)
        runner.run_dir = self.tmp

        class _Spec:
            id = agent_id

        runner.spec = _Spec()
        return runner

    def test_format_agent_renders_final(self):
        runner = self._runner("format")
        artifact = _material("html")
        res = runner._render_deliverable(artifact)
        self.assertIsNotNone(res)
        self.assertEqual(res.fidelity, "final")
        self.assertEqual(res.status, "rendered")

    def test_page_filling_agent_renders_draft(self):
        runner = self._runner("page_filling")
        artifact = {"topic": "增长复盘", "draft_material": _material("html")}
        res = runner._render_deliverable(artifact)
        self.assertIsNotNone(res)
        self.assertEqual(res.fidelity, "draft")
        self.assertEqual(res.status, "rendered")

    def test_other_agent_returns_none(self):
        runner = self._runner("task_positioning")
        self.assertIsNone(runner._render_deliverable(_tp := {"topic": "x"}))

    def test_missing_material_returns_none(self):
        runner = self._runner("page_filling")
        self.assertIsNone(runner._render_deliverable({"topic": "x"}))  # no draft_material


if __name__ == "__main__":
    unittest.main()
