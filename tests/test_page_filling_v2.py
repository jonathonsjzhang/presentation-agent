from __future__ import annotations

import unittest
from pathlib import Path

from presentation_agent.capabilities.compiler import compile_skill_package
from presentation_agent.context import ContextAssembler
from presentation_agent.io import read_json
from presentation_agent.llm.adapters.mock import synthesize_from_schema
from presentation_agent.llm.schema import validate
from presentation_agent.machine_check import run_machine_checks
from presentation_agent.models import AgentSpec
from presentation_agent.review import ArtifactReviewer


ROOT = Path(__file__).resolve().parents[1]


class PageFillingV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = read_json(
            ROOT / "skills" / "page_filling" / "schemas" / "page_content.v2.json"
        )
        self.rubrics = read_json(
            ROOT / "skills" / "page_filling" / "rubrics.json"
        )["rubrics"]

    def test_minimal_synthesized_v2_artifact_is_schema_valid(self) -> None:
        artifact = synthesize_from_schema(self.schema)
        self.assertEqual(artifact["schema"], "page_content.v2")
        self.assertEqual(validate(artifact, self.schema), [])

    def test_runtime_contract_selects_v2_and_inlines_references(self) -> None:
        rows = read_json(ROOT / "configs" / "agents.json")["agents"]
        spec = AgentSpec.from_dict(
            next(row for row in rows if row["id"] == "page_filling")
        )
        package = compile_skill_package(
            ROOT,
            spec,
            {
                "audience": "business_team",
                "report_type": "deep_dive",
                "output_format": "ppt",
            },
            legacy_fallback=False,
        )
        self.assertEqual(spec.output_schema, "page_content.v2")
        self.assertIn("BUNDLED REFERENCES", package.instructions)
        self.assertIn("caveat 改成行动建议", package.instructions)
        self.assertLess(package.budget["instruction_tokens_estimate"], 4000)

    def test_claim_strength_and_non_empty_visual_layers_are_enforced(self) -> None:
        artifact = synthesize_from_schema(self.schema)
        page = artifact["pages"][0]
        page.pop("claim_strength")
        page["visual_plan"]["visual_layers"] = []

        errors = validate(artifact, self.schema)
        self.assertTrue(any("claim_strength" in error for error in errors))
        self.assertTrue(any("visual_layers" in error and "at least 1" in error for error in errors))

    def test_comparison_page_without_matrix_is_reported_as_non_blocking_p1(self) -> None:
        artifact = synthesize_from_schema(self.schema)
        page = artifact["pages"][0]
        page["page_type"] = "comparison"
        page.pop("comparison_matrix", None)

        objections = run_machine_checks(artifact, self.rubrics)
        comparison = [
            objection
            for objection in objections
            if objection.id.endswith("PAGE-COMPARE-001")
        ]
        self.assertTrue(comparison)
        self.assertTrue(all(objection.severity == "P1" for objection in comparison))

    def test_unknown_machine_severity_downgrades_to_p1(self) -> None:
        objections = run_machine_checks(
            {},
            [{
                "id": "ADVISORY",
                "severity": "warning",
                "dimension": "test",
                "machine_check": {
                    "rules": [{"kind": "field_present", "path": "missing"}]
                },
            }],
        )
        self.assertEqual(objections[0].severity, "P1")

    def test_format_review_snapshot_preserves_page_evidence_contract(self) -> None:
        upstream = {
            "schema": "worker_context.v1",
            "upstream_signal": {"topic": "留存"},
            "inputs": {
                "page_filling": {
                    "inline_fields": {
                        "pages": [{
                            "page_no": 6,
                            "title": "纯白用户强留存更高",
                            "page_type": "comparison",
                            "page_takeaway": "DS 与元宝拉动更大",
                            "claim_strength": "finding",
                            "format_handoff_notes": {
                                "must_render_evidence": [{
                                    "evidence_ref": "E-6",
                                    "display_role": "comparison",
                                    "reason_required": "支撑横向比较",
                                }],
                                "on_screen_numbers": [],
                                "must_keep_caveats": ["相关不等于因果"],
                            },
                        }]
                    }
                }
            },
        }
        snapshot = ArtifactReviewer._signal_snapshot(upstream)
        contract = snapshot["page_evidence_contracts"][0]
        self.assertEqual(contract["page_no"], 6)
        self.assertEqual(contract["must_render_evidence"][0]["evidence_ref"], "E-6")
        self.assertEqual(contract["must_keep_caveats"], ["相关不等于因果"])

    def test_granular_evidence_and_format_pages_are_not_three_item_previews(self) -> None:
        assembler = ContextAssembler(ROOT)
        evidence = [
            {"id": f"E-{index}", "detail": "x" * 1000}
            for index in range(20)
        ]
        page_context = assembler.assemble(
            worker_id="page_filling",
            report_charter={},
            manager_task={},
            raw_brief={"evidence_bank": evidence},
            artifacts=[],
        )
        self.assertEqual(page_context["raw_brief"]["evidence_bank"], evidence)

        pages = [
            {"page_no": index, "body": "x" * 5000}
            for index in range(10)
        ]
        format_context = assembler.assemble(
            worker_id="format",
            report_charter={},
            manager_task={},
            raw_brief={},
            artifacts=[(
                Path("/tmp/page_content.json"),
                {"agent_id": "page_filling", "pages": pages},
            )],
        )
        self.assertEqual(
            format_context["inputs"]["page_filling"]["inline_fields"]["pages"],
            pages,
        )

    def test_verified_reference_does_not_contain_known_fabricated_metrics(self) -> None:
        paths = [
            ROOT / "skills" / "page_filling" / "references" / "information_sufficiency.md",
            ROOT / "skills" / "page_filling" / "examples" / "retention_manual_vs_ai.md",
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for forbidden in ["n=1,243", "n=3,871", "p < 0.01", "获客成本约 ¥23", "30 日强留存"]:
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
