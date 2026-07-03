from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path

from presentation_agent.agent_profiles import load_agent_profile
from presentation_agent.capabilities.compiler import compile_skill_package
from presentation_agent.capabilities.models import CapabilityError
from presentation_agent.capabilities.profile import normalize_report_profile
from presentation_agent.llm.schema import validate


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v0_3"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class V03SchemaContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = read_json(FIXTURES / "fixture_manifest.json")

    def test_all_frozen_fixtures_validate(self) -> None:
        for contract in self.manifest["contracts"]:
            with self.subTest(schema=contract["schema"]):
                schema = read_json(ROOT / contract["schema_path"])
                fixture = read_json(ROOT / contract["fixture_path"])
                self.assertEqual(schema["schema"], contract["schema"])
                self.assertEqual(fixture["schema"], contract["schema"])
                self.assertEqual(validate(fixture, schema), [])

    def test_each_contract_rejects_a_missing_required_root_field(self) -> None:
        for contract in self.manifest["contracts"]:
            schema = read_json(ROOT / contract["schema_path"])
            fixture = read_json(ROOT / contract["fixture_path"])
            for required_field in schema["required"]:
                with self.subTest(schema=contract["schema"], field=required_field):
                    invalid = copy.deepcopy(fixture)
                    invalid.pop(required_field)
                    errors = validate(invalid, schema)
                    self.assertTrue(
                        any(f"missing required field '{required_field}'" in error for error in errors),
                        errors,
                    )

    def test_storyline_v3_is_section_based_and_has_no_pages_contract(self) -> None:
        schema = read_json(ROOT / "skills/storyline/schemas/storyline.v3.json")
        fixture = read_json(FIXTURES / "storyline.v3.valid.json")
        self.assertNotIn("pages", schema["properties"])
        self.assertNotIn("pages", fixture)
        self.assertTrue(fixture["report_outline"]["sections"])
        self.assertTrue(
            all(section["content_units"] for section in fixture["report_outline"]["sections"])
        )
        self.assertTrue(fixture["executive_summary"]["core_answer"])
        self.assertTrue(fixture["message_pyramid"]["apex"]["finding_refs"])

    def test_handoffs_are_traceable_across_the_four_stage_chain(self) -> None:
        analysis = read_json(FIXTURES / "analysis.v1.valid.json")
        storyline = read_json(FIXTURES / "storyline.v3.valid.json")
        report = read_json(FIXTURES / "report.v1.valid.json")
        formatted = read_json(FIXTURES / "formatted_material.v2.valid.json")

        analysis_findings = {item["finding_id"] for item in analysis["findings"]}
        storyline_findings = set(storyline["message_pyramid"]["apex"]["finding_refs"])
        self.assertLessEqual(storyline_findings, analysis_findings)

        report_findings = {item["finding_id"] for item in report["findings"]}
        self.assertLessEqual(report_findings, analysis_findings)

        report_sections = {item["section_id"] for item in report["sections"]}
        report_claims = {item["claim_id"] for item in report["claims"]}
        self.assertEqual(set(formatted["source_section_ids"]), report_sections)
        self.assertEqual(set(formatted["source_claim_ids"]), report_claims)
        for unit in formatted["delivery_units"]:
            self.assertLessEqual(set(unit["source_section_ids"]), report_sections)
            self.assertLessEqual(set(unit["source_claim_ids"]), report_claims)

    def test_v03_agent_contract_is_default_user_entry_but_legacy_api_is_preserved(self) -> None:
        config = read_json(ROOT / "configs/agents.json")
        profile = config["contract_profiles"]["v0_3"]
        self.assertEqual(config["active_contract_profile"], "legacy.v0_2")
        self.assertEqual(profile["status"], "frozen")
        self.assertEqual(profile["activation"], "default_user_entry")
        self.assertEqual(
            profile["canonical_stages"],
            ["analysis", "storyline", "report", "format"],
        )
        self.assertEqual(profile["default_delivery_targets"], ["document"])
        self.assertEqual(profile["internal_subagents"], ["evidence_harvester"])

        workers = {worker["id"]: worker for worker in profile["workers"]}
        self.assertEqual(set(workers), {"analysis", "storyline", "report", "format"})
        self.assertEqual(workers["analysis"]["input_schema"], "report_charter.v2")
        self.assertEqual(workers["analysis"]["output_schema"], "analysis.v1")
        self.assertEqual(workers["storyline"]["input_schema"], "analysis.v1")
        self.assertEqual(workers["report"]["input_schema"], "storyline.v3")
        self.assertEqual(workers["format"]["input_schema"], "report.v1")
        frozen_schemas = {contract["schema"] for contract in self.manifest["contracts"]}
        for worker in workers.values():
            self.assertIn(worker["input_schema"], frozen_schemas)
            self.assertIn(worker["output_schema"], frozen_schemas)
        self.assertTrue(
            all(worker["implementation_status"] == "contract_only_wp1" for worker in workers.values())
        )

    def test_capability_and_context_profiles_use_delivery_target(self) -> None:
        capabilities = read_json(ROOT / "configs/capabilities.json")
        capability_profile = capabilities["contract_profiles"]["v0_3"]
        self.assertEqual(capability_profile["default_delivery_targets"], ["document"])
        self.assertEqual(
            capability_profile["delivery_targets"],
            ["document", "ppt", "html"],
        )
        self.assertEqual(
            capability_profile["format_selection"],
            "exactly_one_delivery_target_capability_per_task",
        )

        context = read_json(ROOT / "configs/context_requirements.json")
        context_workers = context["contract_profiles"]["v0_3"]["workers"]
        self.assertEqual(set(context_workers), {"analysis", "storyline", "report", "format"})
        self.assertIn("raw_materials", context_workers["storyline"]["excluded_fields"])
        self.assertIn("delivery_target", context_workers["format"]["task_fields"])
        self.assertIn("storyline.pages", context_workers["format"]["excluded_fields"])

    def test_golden_case_set_covers_required_material_modes(self) -> None:
        golden = read_json(FIXTURES / "golden_cases" / "manifest.json")
        self.assertEqual(golden["status"], "frozen")
        self.assertEqual(len(golden["cases"]), 3)

        coverage = {label for case in golden["cases"] for label in case["coverage"]}
        self.assertIn("qualitative", coverage)
        self.assertIn("interview", coverage)
        self.assertIn("excel", coverage)
        self.assertIn("quantitative", coverage)
        self.assertIn("mixed_materials", coverage)
        self.assertIn("deep_dive", coverage)

        output_formats = {
            output["format"]
            for case in golden["cases"]
            for output in case["legacy_output_snapshots"]
        }
        output_formats.update(
            case["human_report_sample"]["format"]
            for case in golden["cases"]
            if "human_report_sample" in case
        )
        self.assertTrue({"document", "ppt"}.issubset(output_formats))

        for case in golden["cases"]:
            with self.subTest(case=case["case_id"]):
                self.assertTrue((ROOT / case["normalized_input"]).is_file())
                self.assertTrue(case["human_minimum_quality"])
                for snapshot in (
                    case["local_source_snapshots"] + case["legacy_output_snapshots"]
                ):
                    self.assertRegex(snapshot["sha256"], re.compile(r"^[0-9a-f]{64}$"))
                    self.assertGreater(snapshot["bytes"], 0)

    def test_fixture_manifest_provides_each_worker_an_independent_input(self) -> None:
        worker_inputs = self.manifest["worker_inputs"]
        self.assertEqual(set(worker_inputs), {"analysis", "storyline", "report", "format"})
        for worker, input_spec in worker_inputs.items():
            with self.subTest(worker=worker):
                referenced = [
                    value
                    for key, value in input_spec.items()
                    if key.endswith("_fixture")
                ]
                self.assertTrue(referenced)
                self.assertTrue(all((ROOT / path).is_file() for path in referenced))


class FormatCoreCompilationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = read_json(FIXTURES / "report.v1.valid.json")
        self.formatted = read_json(FIXTURES / "formatted_material.v2.valid.json")
        self.spec = load_agent_profile(ROOT, "v0_3").specs["format"]

    def compile(self, target: str = "document"):
        return compile_skill_package(
            ROOT,
            self.spec,
            {"report": self.report, "delivery_target": target},
        )

    def test_report_fixture_compiles_v2_skill_with_one_target_capability(self) -> None:
        package = self.compile()
        selected = [
            item for item in package.selected_capabilities if item.startswith("format.")
        ]
        self.assertFalse(package.legacy)
        self.assertEqual(selected, ["format.document"])
        self.assertIn("formatted_material.v2", package.instructions)
        self.assertIn("delivery_target=document", package.instructions)
        self.assertNotIn("page_content → formatted_material.v1", package.instructions)
        self.assertIn("formatted_material.v2", package.schemas)

    def test_each_delivery_target_selects_exactly_one_matching_capability(self) -> None:
        for target in ("document", "ppt", "html"):
            with self.subTest(target=target):
                package = self.compile(target)
                selected = [
                    item
                    for item in package.selected_capabilities
                    if item.startswith("format.")
                ]
                self.assertEqual(selected, [f"format.{target}"])
                self.assertIn(f"delivery_target={target}", package.instructions)

    def test_report_profile_defaults_to_document(self) -> None:
        profile = normalize_report_profile(self.report, root=ROOT)
        self.assertEqual(profile.version, "v0_3")
        self.assertEqual(profile.delivery_target, "document")
        self.assertEqual(profile.audience, self.report["report_metadata"]["audience"])

    def test_v03_rejects_legacy_or_multi_target_input_without_fallback(self) -> None:
        invalid_inputs = [
            {"report": self.report, "output_format": "ppt"},
            {"report": self.report, "delivery_target": ["document", "ppt"]},
            {"report": self.report, "delivery_target": "video"},
        ]
        for input_data in invalid_inputs:
            with self.subTest(input_data=input_data):
                with self.assertRaises(CapabilityError):
                    compile_skill_package(ROOT, self.spec, input_data)

    def test_legacy_page_content_compilation_remains_available(self) -> None:
        legacy_spec = load_agent_profile(ROOT).specs["format"]
        package = compile_skill_package(
            ROOT,
            legacy_spec,
            {
                "schema": "page_content.v2",
                "audience": "business_team",
                "report_type": "deep_dive",
                "output_format": "ppt",
            },
            legacy_fallback=False,
        )
        self.assertFalse(package.legacy)
        self.assertIn("format.ppt", package.selected_capabilities)
        self.assertIn("Format Skill v3.12", package.instructions)
        self.assertIn("formatted_material.v1", package.schemas)

    def test_fixture_records_mapping_and_all_translation_audits(self) -> None:
        report_sections = {row["section_id"] for row in self.report["sections"]}
        report_claims = {row["claim_id"] for row in self.report["claims"]}
        self.assertEqual(set(self.formatted["source_section_ids"]), report_sections)
        self.assertEqual(set(self.formatted["source_claim_ids"]), report_claims)
        protected = set(self.report["format_handoff"]["protected_caveats"])
        recorded = {
            row["source_caveat"] for row in self.formatted["caveat_preservation"]
        }
        self.assertEqual(recorded, protected)
        self.assertTrue(self.formatted["compression_decisions"])
        self.assertTrue(self.formatted["omitted_content_register"])
        self.assertEqual(self.formatted["render_result"]["status"], "planned")

    def test_v2_schema_rejects_missing_translation_audit_fields(self) -> None:
        schema = read_json(
            ROOT
            / "skills"
            / "format_report"
            / "schemas"
            / "formatted_material.v2.json"
        )
        for field in (
            "source_section_ids",
            "source_claim_ids",
            "compression_decisions",
            "omitted_content_register",
            "caveat_preservation",
        ):
            with self.subTest(field=field):
                invalid = copy.deepcopy(self.formatted)
                invalid.pop(field)
                self.assertTrue(validate(invalid, schema))


if __name__ == "__main__":
    unittest.main()
