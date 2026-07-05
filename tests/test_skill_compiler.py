from __future__ import annotations

import unittest
import shutil
import tempfile
from pathlib import Path

from presentation_agent.capabilities.compiler import compile_skill_package
from presentation_agent.capabilities.profile import ReportProfile
from presentation_agent.capabilities.resolver import resolve_capabilities
from presentation_agent.io import read_json, write_json
from presentation_agent.models import AgentSpec


ROOT = Path(__file__).resolve().parents[1]


def _spec(agent_id: str) -> AgentSpec:
    agents = read_json(ROOT / "configs" / "agents.json")["agents"]
    return AgentSpec.from_dict(next(item for item in agents if item["id"] == agent_id))


class SkillCompilerTests(unittest.TestCase):
    def test_resolver_supports_full_profile_matrix(self) -> None:
        agents = [
            "argument_synthesis",
            "storyline_design",
            "page_filling",
            "format",
            "qa_preparation",
            "speaker_script",
        ]
        count = 0
        for agent_id in agents:
            for audience in ["board", "exec_office", "strategy_lead", "business_team", "external"]:
                for report_type in ["deep_dive", "business_progress", "quick_sync"]:
                    for output_format in ["document", "ppt", "html"]:
                        selection = resolve_capabilities(
                            agent_id,
                            ReportProfile(audience, report_type, output_format),
                        )
                        self.assertEqual(len(selection.capability_ids), 4)
                        count += 1
        self.assertEqual(count, 270)

    def test_storyline_bundle_is_deterministic(self) -> None:
        data = {
            "audience": "board",
            "report_type": "deep_dive",
            "output_format": "ppt",
        }
        first = compile_skill_package(ROOT, _spec("storyline_design"), data, legacy_fallback=False)
        second = compile_skill_package(ROOT, _spec("storyline_design"), data, legacy_fallback=False)
        self.assertFalse(first.legacy)
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(
            first.selected_capabilities,
            [
                "core.storyline_design",
                "audience.board",
                "report.deep_dive",
                "format.ppt",
            ],
        )

    def test_prompt_contains_only_active_atomic_capabilities(self) -> None:
        package = compile_skill_package(
            ROOT,
            _spec("storyline_design"),
            {
                "audience": "board",
                "report_type": "deep_dive",
                "output_format": "ppt",
            },
            legacy_fallback=False,
        )
        self.assertIn("重大取舍", package.instructions)
        self.assertIn("按页组织", package.instructions)
        self.assertNotIn("内部授权诉求", package.instructions)
        self.assertNotIn("摘要、导航、内容模块", package.instructions)
        rubric_ids = {item["id"] for item in package.rubrics}
        self.assertIn("AUD-BOARD-SL-001", rubric_ids)
        self.assertIn("FMT-PPT-SL-001", rubric_ids)
        self.assertNotIn("AUD-EXT-SL-001", rubric_ids)
        self.assertNotIn("FMT-HTML-SL-001", rubric_ids)

    def test_business_progress_has_distinct_structure(self) -> None:
        package = compile_skill_package(
            ROOT,
            _spec("storyline_design"),
            {
                "audience": "business_team",
                "report_type": "business_progress",
                "output_format": "document",
            },
            legacy_fallback=False,
        )
        self.assertIn("目标/承诺", package.instructions)
        self.assertIn("关键偏差", package.instructions)
        self.assertIn("具体顺序由最重要的判断及其论证依赖决定", package.instructions)
        self.assertNotIn("不要扩展成完整战略专题", package.instructions)

    def test_format_worker_uses_compiled_format_package(self) -> None:
        package = compile_skill_package(
            ROOT,
            _spec("format"),
            {
                "audience": "board",
                "report_type": "deep_dive",
                "output_format": "ppt",
            },
        )
        self.assertFalse(package.legacy)
        self.assertEqual(
            package.selected_capabilities,
            [
                "core.format",
                "audience.board",
                "report.deep_dive",
                "format.ppt",
            ],
        )
        self.assertIn("mck_ppt_shape_native", package.instructions)
        self.assertNotIn("docx_report_renderer", package.instructions)

    def test_all_content_workers_compile_all_profiles(self) -> None:
        agents = [
            "argument_synthesis",
            "storyline_design",
            "page_filling",
            "qa_preparation",
            "speaker_script",
        ]
        for agent_id in agents:
            for audience in ["board", "exec_office", "strategy_lead", "business_team", "external"]:
                for report_type in ["deep_dive", "business_progress", "quick_sync"]:
                    for output_format in ["document", "ppt", "html"]:
                        package = compile_skill_package(
                            ROOT,
                            _spec(agent_id),
                            {
                                "audience": audience,
                                "report_type": report_type,
                                "output_format": output_format,
                            },
                            legacy_fallback=False,
                        )
                        self.assertFalse(package.legacy)
                        self.assertEqual(len(package.selected_capabilities), 4)
                        self.assertTrue(package.fingerprint)

    def test_external_html_rules_are_isolated_for_every_content_worker(self) -> None:
        for agent_id in [
            "argument_synthesis",
            "storyline_design",
            "page_filling",
            "qa_preparation",
            "speaker_script",
        ]:
            package = compile_skill_package(
                ROOT,
                _spec(agent_id),
                {
                    "audience": "external",
                    "report_type": "quick_sync",
                    "output_format": "html",
                },
                legacy_fallback=False,
            )
            self.assertIn(f"audience.external", package.selected_capabilities)
            self.assertIn(f"format.html", package.selected_capabilities)
            self.assertNotIn("重大取舍、风险收益", package.instructions)
            self.assertNotIn("按页讲", package.instructions)

    def test_global_feature_flag_restores_legacy_loader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "configs", root / "configs")
            shutil.copytree(ROOT / "skills", root / "skills")
            config_path = root / "configs" / "capabilities.json"
            config = read_json(config_path)
            config["runtime"]["enabled"] = False
            write_json(config_path, config)
            package = compile_skill_package(
                root,
                _spec("storyline_design"),
                {
                    "audience": "board",
                    "report_type": "deep_dive",
                    "output_format": "ppt",
                },
            )
            self.assertTrue(package.legacy)
            self.assertEqual(package.selected_capabilities, [])

    def test_compiled_prompt_budget_is_bounded(self) -> None:
        package = compile_skill_package(
            ROOT,
            _spec("storyline_design"),
            {
                "audience": "external",
                "report_type": "quick_sync",
                "output_format": "html",
            },
            legacy_fallback=False,
        )
        self.assertLess(package.budget["instruction_tokens_estimate"], 4000)
        self.assertLess(package.budget["rubric_tokens_estimate"], 3000)

    def test_page_filling_bundle_inlines_declared_references_and_uses_v2(self) -> None:
        package = compile_skill_package(
            ROOT,
            _spec("page_filling"),
            {
                "audience": "business_team",
                "report_type": "deep_dive",
                "output_format": "ppt",
            },
            legacy_fallback=False,
        )
        self.assertIn("BUNDLED REFERENCES", package.instructions)
        self.assertIn("主证据", package.instructions)
        self.assertIn("caveat 改成行动建议", package.instructions)
        self.assertEqual(_spec("page_filling").output_schema, "page_content.v2")
        self.assertEqual(
            package.schemas["page_content.v2"]["properties"]["schema"]["const"],
            "page_content.v2",
        )
        self.assertLess(package.budget["instruction_tokens_estimate"], 4000)


if __name__ == "__main__":
    unittest.main()
