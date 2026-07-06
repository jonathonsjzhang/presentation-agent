from __future__ import annotations

import tempfile
import unittest
from itertools import product
from pathlib import Path

from presentation_agent.capabilities.compiler import compile_skill_package
from presentation_agent.agent_profiles import load_agent_profile
from presentation_agent.io import read_json
from presentation_agent.models import AgentSpec
from presentation_agent.renderers import render_material
from presentation_agent.machine_check import run_machine_checks
from presentation_agent.review import ArtifactReviewer
from presentation_agent.memory import MemoryStore
from presentation_agent.skill_package import load_skill_package


ROOT = Path(__file__).resolve().parents[1]


def _specs() -> dict[str, AgentSpec]:
    return load_agent_profile(ROOT).specs


class FormatCapabilityTests(unittest.TestCase):
    def test_all_270_worker_profile_bundles_compile_without_fallback(self) -> None:
        dimensions = read_json(ROOT / "configs" / "capabilities.json")["dimensions"]
        count = 0
        for spec, audience, report_type, output_format in product(
            _specs().values(),
            dimensions["audience"],
            dimensions["report_type"],
            dimensions["output_format"],
        ):
            package = compile_skill_package(
                ROOT,
                spec,
                {
                    "audience": audience,
                    "report_type": report_type,
                    "output_format": output_format,
                },
            )
            self.assertFalse(package.legacy)
            self.assertIn(f"format.{output_format}", package.selected_capabilities)
            count += 1
        self.assertEqual(count, 270)

    def test_format_prompt_contains_only_selected_carrier_harness(self) -> None:
        spec = _specs()["format"]
        expectations = {
            "ppt": ("renderer=ppt_renderer", ["renderer=docx_renderer", "renderer=html_renderer"]),
            "document": ("renderer=docx_renderer", ["renderer=ppt_renderer", "renderer=html_renderer"]),
            "html": ("renderer=html_renderer", ["renderer=ppt_renderer", "renderer=docx_renderer"]),
        }
        for output_format, (included, excluded) in expectations.items():
            package = compile_skill_package(
                ROOT,
                spec,
                {
                    "audience": "board",
                    "report_type": "deep_dive",
                    "output_format": output_format,
                },
            )
            self.assertIn(included, package.instructions)
            for marker in excluded:
                self.assertNotIn(marker, package.instructions)

    def test_format_conflict_is_p0_and_renderer_refuses_dispatch(self) -> None:
        spec = _specs()["format"]
        package = compile_skill_package(
            ROOT,
            spec,
            {
                "audience": "board",
                "report_type": "deep_dive",
                "output_format": "ppt",
            },
        )
        artifact = {
            "schema": spec.output_schema,
            "agent_id": "format",
            "format": "html",
            "material_units": [{"unit_id": "u1"}],
        }
        with tempfile.TemporaryDirectory() as temp:
            memory = MemoryStore(ROOT, "format", data_root=Path(temp))
            report = ArtifactReviewer().review(
                spec, artifact, memory, package.to_dict()
            )
            result = render_material(
                artifact,
                Path(temp),
                expected_format="ppt",
                selected_capabilities=package.selected_capabilities,
            )

        self.assertTrue(any(obj.id == "P0-format-capability-mismatch" for obj in report.p0))
        self.assertEqual(result.status, "error")
        self.assertIn("delivery_target mismatch", result.detail)

    def test_negated_kpi_policy_statement_does_not_trigger_forbidden_pattern(self) -> None:
        package = load_skill_package(ROOT, "format")
        artifact = {
            "delivery_units": [
                {
                    "headline": "边界说明",
                    "content": {
                        "primary_text": "本报告不涉及 KPI、预算或时间表，也不得新增负责人。"
                    },
                    "visual_asset_refs": [],
                }
            ],
        }

        objections = run_machine_checks(artifact, package.rubrics)

        self.assertFalse(
            any(
                item.dimension == "recommendation_scope"
                for item in objections
            ),
            [item.to_dict() for item in objections],
        )


if __name__ == "__main__":
    unittest.main()
