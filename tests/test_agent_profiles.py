from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from presentation_agent.agent_profiles import (
    LEGACY_CONTRACT_PROFILE,
    load_agent_profile,
)
from presentation_agent.loop import LoopRunner
from presentation_agent.launch import normalize_brief
from presentation_agent.manager import ManagerOrchestrator
from presentation_agent.context import ContextAssembler
from presentation_agent.step import PipelineStepper, StepRunner


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v0_3"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class AgentProfileLoaderTests(unittest.TestCase):
    def test_v03_manager_starts_four_stage_document_first_gate(self) -> None:
        brief = normalize_brief(
            {
                "topic": "测试主题",
                "audience": "strategy_lead",
                "decision_goal": "决定下一步",
            },
            ROOT,
            "v0_3",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            brief_path = run_dir / "raw_brief.json"
            brief_path.write_text(
                json.dumps(brief, ensure_ascii=False), encoding="utf-8"
            )
            manager = ManagerOrchestrator(
                ROOT, run_dir, contract_profile="v0_3"
            )
            prepared = manager.initialize_run(brief_path)
            self.assertEqual(
                prepared["selected_workers"],
                ["analysis", "storyline", "report", "format"],
            )
            self.assertEqual(prepared["brief"]["delivery_targets"], ["document"])
            self.assertEqual(
                manager.status()["state"]["contract_profile"], "v0_3"
            )

    def test_v03_defers_requested_ppt_until_after_document(self) -> None:
        brief = normalize_brief(
            {
                "topic": "测试主题",
                "audience": "strategy_lead",
                "decision_goal": "决定下一步",
                "delivery_targets": ["ppt", "html"],
            },
            ROOT,
            "v0_3",
        )
        self.assertEqual(brief["delivery_targets"], ["document"])
        self.assertEqual(brief["output_format"], "document")
        self.assertEqual(
            brief["requested_followup_targets"], ["ppt", "html"]
        )

    def test_v03_normalization_preserves_material_references(self) -> None:
        brief = normalize_brief(
            {
                "topic": "测试主题",
                "audience": "strategy_lead",
                "decision_goal": "决定下一步",
                "materials": [
                    {
                        "material_id": "m1",
                        "fixture": "nested/input.json",
                        "role": "mechanism_exploration",
                    }
                ],
            },
            ROOT,
            "v0_3",
        )
        self.assertEqual(brief["materials"][0]["fixture"], "nested/input.json")

    def test_v03_analysis_lifts_interview_and_table_snapshots(self) -> None:
        assembler = ContextAssembler(ROOT, contract_profile="v0_3")
        charter = read_json(FIXTURES / "report_charter.v2.valid.json")
        for case_id, expected_key in (
            ("qualitative_interviews", "source_units"),
            ("quantitative_usage", "rows"),
        ):
            raw = read_json(
                FIXTURES / "golden_cases" / case_id / "input.json"
            )
            result = assembler.assemble(
                worker_id="analysis",
                report_charter=charter,
                manager_task={"acceptance_criteria": ["traceable"]},
                raw_brief=raw,
                raw_brief_path=None,
                artifacts=[],
            )
            self.assertTrue(result["raw_materials"])
            self.assertIn(expected_key, result["raw_materials"][0])

    def test_all_v03_golden_cases_reach_document_first_brief_gate(self) -> None:
        cases_root = FIXTURES / "golden_cases"
        manifest = read_json(cases_root / "manifest.json")
        for case in manifest["cases"]:
            source = ROOT / case["normalized_input"]
            with self.subTest(case=case["case_id"]), tempfile.TemporaryDirectory() as temp_dir:
                run_dir = Path(temp_dir)
                brief = normalize_brief(source, ROOT, "v0_3")
                brief_path = run_dir / "raw_brief.json"
                brief_path.write_text(
                    json.dumps(brief, ensure_ascii=False), encoding="utf-8"
                )
                prepared = ManagerOrchestrator(
                    ROOT, run_dir, contract_profile="v0_3"
                ).initialize_run(brief_path)
                self.assertEqual(prepared["gate"], "brief")
                self.assertEqual(prepared["missing_fields"], [])
                self.assertEqual(prepared["brief"]["delivery_targets"], ["document"])
                self.assertEqual(
                    prepared["selected_workers"],
                    ["analysis", "storyline", "report", "format"],
                )

    def test_default_profile_preserves_legacy_workers_and_pipeline(self) -> None:
        profile = load_agent_profile(ROOT)
        self.assertEqual(profile.contract_profile, LEGACY_CONTRACT_PROFILE)
        self.assertEqual(
            [spec.id for spec in profile.ordered_specs],
            [
                "argument_synthesis",
                "storyline_design",
                "page_filling",
                "format",
                "qa_preparation",
                "speaker_script",
            ],
        )
        self.assertIn("evidence_harvester", profile.specs)

    def test_explicit_v03_loads_executable_four_stage_specs(self) -> None:
        profile = load_agent_profile(ROOT, "v0_3")
        self.assertEqual(
            [spec.id for spec in profile.ordered_specs],
            ["analysis", "storyline", "report", "format"],
        )
        for spec in profile.ordered_specs:
            with self.subTest(agent=spec.id):
                self.assertEqual(spec.skill, spec.id)
                self.assertTrue(spec.memory_dimensions)
                self.assertGreater(spec.max_revision_rounds, 0)
                self.assertTrue(spec.loop_policy)
                self.assertTrue(spec.state_contract)
                self.assertTrue(spec.harness)
        self.assertEqual(profile.specs["analysis"].previous_agent_id, "manager")
        self.assertEqual(profile.specs["analysis"].next_agent_id, "storyline")
        self.assertEqual(profile.specs["storyline"].next_agent_id, "report")
        self.assertEqual(profile.specs["report"].next_agent_id, "format")
        self.assertIsNone(profile.specs["format"].next_agent_id)

    def test_loop_runner_accepts_explicit_profile_without_running_a_model(self) -> None:
        runner = LoopRunner(ROOT, provider_override="mock", contract_profile="v0_3")
        self.assertEqual(runner.contract_profile, "v0_3")
        self.assertEqual(
            [spec.id for spec in runner.list_agents()],
            ["analysis", "storyline", "report", "format"],
        )


class V03StepRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.run_dir = self.tmp / "run"
        self.data_root = self.tmp / "data"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pipeline_and_core_workers_use_frozen_contracts(self) -> None:
        stepper = PipelineStepper(
            ROOT,
            self.run_dir,
            data_root=self.data_root,
            contract_profile="v0_3",
        )
        initialized = stepper.init_pipeline(
            FIXTURES / "report_charter.v2.valid.json"
        )
        self.assertEqual(initialized["agent_id"], "analysis")
        self.assertEqual(
            [row["agent_id"] for row in stepper.pipeline_status()["stages"]],
            ["analysis", "storyline", "report", "format"],
        )

        fixtures = {
            "analysis": "analysis.v1.valid.json",
            "storyline": "storyline.v3.valid.json",
            "report": "report.v1.valid.json",
        }
        expected_schemas = {
            "analysis": "analysis.v1",
            "storyline": "storyline.v3",
            "report": "report.v1",
        }

        stage = initialized
        for index, agent_id in enumerate(("analysis", "storyline", "report")):
            with self.subTest(agent=agent_id):
                stage_dir = Path(stage["stage_dir"])
                run_state = read_json(stage_dir / "run_state.json")
                self.assertEqual(run_state["contract_profile"], "v0_3")
                self.assertEqual(run_state["agent_id"], agent_id)

                runner = StepRunner(
                    ROOT,
                    stage_dir,
                    data_root=self.data_root,
                    contract_profile="v0_3",
                )
                expected_schema = expected_schemas[agent_id]
                self.assertEqual(runner.skill.id, agent_id)
                self.assertEqual(runner.spec.output_schema, expected_schema)
                self.assertIn(expected_schema, runner.skill_package.schemas)

                prepared = runner.prepare()
                instruction = Path(prepared["instruction_path"]).read_text(
                    encoding="utf-8"
                )
                self.assertIn(f"严格符合 {expected_schema}", instruction)
                self.assertIn(runner.skill_package.instructions[:80], instruction)

                output = read_json(FIXTURES / fixtures[agent_id])
                Path(prepared["output_path"]).write_text(
                    json.dumps(output, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                review = runner.commit()
                self.assertEqual(review["step"], "review")
                Path(review["output_path"]).write_text(
                    '{"objections": []}',
                    encoding="utf-8",
                )
                done = runner.commit()
                self.assertEqual(done["step"], "done")
                self.assertEqual(done["agent_id"], agent_id)
                self.assertFalse(read_json(stage_dir / "run_state.json")["p0_open"])

                if index < 2:
                    stage = stepper.advance_stage()


if __name__ == "__main__":
    unittest.main()
