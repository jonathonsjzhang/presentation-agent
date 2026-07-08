from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from presentation_agent.agent_profiles import load_agent_profile
from presentation_agent.loop import LoopRunner
from presentation_agent.launch import normalize_brief
from presentation_agent.manager import (
    ManagerAgentRuntime,
    ManagerOrchestrator,
    WorkerExecutor,
)
from presentation_agent.context import ContextAssembler
from presentation_agent.cli import build_parser, _worker_spawn_response
from presentation_agent.step import PipelineStepper, StepError, StepRunner
from presentation_agent.spawn import WorkBuddySpawnAdapter
from presentation_agent.skill_package import load_skill_package


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v0_3"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class AgentProfileLoaderTests(unittest.TestCase):
    def test_user_facing_report_start_defaults_to_v03(self) -> None:
        args = build_parser().parse_args(
            ["report", "start", "--brief-file", "brief.json"]
        )
        self.assertEqual(args.contract_profile, "v0_3")
        approve = build_parser().parse_args(
            [
                "report",
                "approve",
                "--run",
                "run-id",
                "--run-mode",
                "full_auto",
                "--review-mode",
                "schema_only",
                "--delivery-option",
                "format:ppt",
            ]
        )
        self.assertEqual(approve.run_mode, "full_auto")
        self.assertEqual(approve.review_mode, "schema_only")
        self.assertEqual(approve.delivery_option, "format:ppt")
        default_approve = build_parser().parse_args(
            ["report", "approve", "--run", "run-id"]
        )
        self.assertEqual(default_approve.run_mode, "full_auto")
        self.assertEqual(default_approve.review_mode, "schema_only")
        custom = build_parser().parse_args(
            [
                "report",
                "approve",
                "--run",
                "run-id",
                "--run-mode",
                "custom",
                "--pause-after",
                "analysis",
                "--pause-after",
                "format",
            ]
        )
        self.assertEqual(custom.run_mode, "custom")
        self.assertEqual(custom.pause_after, ["analysis", "format"])
        submit = build_parser().parse_args(
            [
                "report",
                "submit",
                "--run",
                "run-id",
                "--spawn-completed",
            ]
        )
        self.assertTrue(submit.spawn_completed)

    def test_worker_spawn_is_exposed_consistently_at_cli_top_level(self) -> None:
        instruction = {
            "actor": "worker",
            "step": "gen",
            "spawn": {"status": "dispatched", "adapter": "workbuddy"},
        }
        for result in (instruction, {"instruction": instruction}):
            exposed = _worker_spawn_response(result)
            self.assertIs(exposed["instruction"], instruction)
            self.assertTrue(exposed["spawn_required"])

    def test_v03_manager_starts_five_stage_document_first_chain(self) -> None:
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
                ["analysis", "storyline", "report", "format", "qa_preparation"],
            )
            confirmation = prepared["present_to_user"]
            for hidden_worker in (
                "evidence_harvester",
                "argument_synthesis",
                "page_filling",
                "speaker_script",
            ):
                self.assertNotIn(hidden_worker, confirmation)
            self.assertIn("`report` 报告产出", confirmation)
            self.assertIn("`format` 可视化", confirmation)
            self.assertIn("`qa_preparation` QA 梳理", confirmation)
            self.assertEqual(prepared["brief"]["delivery_targets"], ["document"])
            self.assertEqual(
                manager.status()["state"]["contract_profile"], "v0_3"
            )
            self.assertEqual(
                set(prepared["review_mode_options"]),
                {"independent", "schema_only"},
            )
            review_question = next(
                question
                for question in prepared["questions"]
                if question["header"] == "Review模式"
            )
            self.assertEqual(
                [option["label"] for option in review_question["options"]],
                ["不启用（默认）", "启用（质量优先）"],
            )

            manager.approve()
            approved_state = manager.status()["state"]
            self.assertEqual(approved_state["run_mode"], "full_auto")
            self.assertEqual(approved_state["review_mode"], "schema_only")
            self.assertFalse(approved_state["review_subagents_enabled"])

    def test_v03_manager_uses_profile_specific_skill_without_legacy_workers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ManagerOrchestrator(
                ROOT,
                Path(temp_dir),
                contract_profile="v0_3",
            )
            instructions = manager.agent.package.instructions
            self.assertIn(
                "analysis → storyline → report → format(document) → qa_preparation",
                instructions,
            )
            for legacy_worker in (
                "argument_synthesis",
                "storyline_design",
                "page_filling",
                "evidence_harvester 任务",
                "speaker_script",
            ):
                self.assertNotIn(legacy_worker, instructions)

    def test_v03_manager_runtime_enforces_canonical_plan_and_routes(self) -> None:
        charter = read_json(FIXTURES / "report_charter.v2.valid.json")
        tasks = [
            {
                "task_id": f"t{index}",
                "agent_id": agent_id,
                "objective": agent_id,
                "dependencies": [] if index == 1 else [f"t{index - 1}"],
                "status": "planned",
            }
            for index, agent_id in enumerate(
                ("analysis", "storyline", "report", "format", "qa_preparation"),
                start=1,
            )
        ]
        packet = {
            "agent_id": "analysis",
            "recommendation_granularity": charter[
                "recommendation_granularity"
            ],
            "unsupported_specificity_policy": charter[
                "unsupported_specificity_policy"
            ],
        }
        self.assertEqual(
            ManagerAgentRuntime._v03_plan_errors(
                charter,
                {"tasks": tasks},
                packet,
            ),
            [],
        )
        self.assertTrue(
            ManagerAgentRuntime._v03_plan_errors(
                charter,
                {**packet, "agent_id": "storyline"},
            )
        )
        state = {
            "current_task": {"agent_id": "analysis"},
            "last_event": "worker_completed",
        }
        self.assertTrue(
            ManagerAgentRuntime._v03_acceptance_route_errors(
                "complete", state, None
            )
        )
        self.assertTrue(
            ManagerAgentRuntime._v03_acceptance_route_errors(
                "dispatch",
                state,
                {"agent_id": "report"},
            )
        )
        self.assertEqual(
            ManagerAgentRuntime._v03_acceptance_route_errors(
                "dispatch",
                state,
                {"agent_id": "storyline"},
            ),
            [],
        )
        format_state = {
            "current_task": {"agent_id": "format"},
            "last_event": "worker_completed",
        }
        self.assertTrue(
            ManagerAgentRuntime._v03_acceptance_route_errors(
                "complete", format_state, None
            )
        )
        self.assertEqual(
            ManagerAgentRuntime._v03_acceptance_route_errors(
                "dispatch",
                format_state,
                {"agent_id": "qa_preparation"},
            ),
            [],
        )

    def test_manager_planning_instruction_exposes_actual_nested_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            runtime = ManagerAgentRuntime(
                ROOT,
                temp / "run",
                temp / "data",
                contract_profile="v0_3",
            )
            instruction = runtime.prepare(
                {"schema": "manager_context.v1"},
                "planning",
            )
            text = Path(instruction["instruction_path"]).read_text(
                encoding="utf-8"
            )
            self.assertIn("### report_charter.v2", text)
            self.assertIn('"material_inventory"', text)
            self.assertNotIn("### execution_plan.v1", text)
            self.assertIn("### task_packet.v2", text)
            self.assertIn('"objective"', text)
            self.assertIn("固定流程、ID 和状态由 runtime 生成", text)

    def test_delivery_gate_exposes_structured_choice_and_routes_selection(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            manager = ManagerOrchestrator(
                ROOT,
                run_dir,
                contract_profile="v0_3",
            )
            state = {
                "version": "manager_state.v2",
                "run_id": "delivery-test",
                "contract_profile": "v0_3",
                "current_actor": "human",
                "human_gate": "delivery_options",
                "status": "awaiting_delivery_option_selection",
                "pending_decision": {"user_message": "文档已完成"},
                "current_task": {
                    "task_id": "format-document",
                    "agent_id": "format",
                },
                "tasks": [],
                "accepted_artifacts": [],
                "project_state": {},
                "manager_phase": "acceptance",
                "manager_step": "idle",
                "last_event": "worker_completed",
                "spawn_adapter": "inline",
            }
            manager._save_state(state)
            (run_dir / "raw_brief.json").write_text(
                '{"topic":"测试","audience":"strategy_lead","decision_goal":"决策"}',
                encoding="utf-8",
            )
            gate = manager.prepare()
            values = [
                option["value"]
                for option in gate["questions"][0]["options"]
            ]
            self.assertEqual(
                values,
                [
                    "format:ppt",
                    "format:html",
                    "skip",
                ],
            )

            result = manager.approve(delivery_option="format:ppt")

            self.assertEqual(result["actor"], "manager")
            updated = manager.status()["state"]
            self.assertEqual(updated["last_event"], "human_feedback")
            self.assertIn(
                "format:ppt",
                updated["human_feedback"][-1]["text"],
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

    def test_review_choice_is_copied_into_each_worker_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            raw_brief_path = run_dir / "raw_brief.json"
            raw_brief_path.write_text(
                json.dumps(
                    {
                        "topic": "测试主题",
                        "audience": "strategy_lead",
                        "decision_goal": "决定下一步",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            executor = WorkerExecutor(
                ROOT,
                run_dir,
                run_dir / "data",
                contract_profile="v0_3",
            )
            task = executor.create_task(
                {
                    "task_id": "analysis-001",
                    "agent_id": "analysis",
                    "objective": "形成可追溯的分析判断",
                    "input_artifacts": [],
                    "acceptance_criteria": ["结构有效"],
                },
                read_json(FIXTURES / "report_charter.v2.valid.json"),
                raw_brief_path,
                review_subagents_enabled=False,
            )
            task_state = read_json(Path(task["task_dir"]) / "run_state.json")
            self.assertFalse(task_state["review_subagents_enabled"])

    def test_step_runner_recompiles_stale_format_capabilities_from_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir)
            input_path = task_dir / "input.json"
            input_path.write_text(
                json.dumps(
                    {
                        "schema": "worker_context.v1",
                        "report": read_json(
                            FIXTURES / "report.v1.valid.json"
                        ),
                        "delivery_target": "document",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (task_dir / "run_state.json").write_text(
                json.dumps(
                    {
                        "agent_id": "format",
                        "contract_profile": "v0_3",
                        "input_path": str(input_path),
                        "current_step": "init",
                    }
                ),
                encoding="utf-8",
            )
            stale = load_skill_package(ROOT, "format").to_dict()
            stale["selected_capabilities"] = ["format.ppt"]
            (task_dir / "compiled_skill_package.json").write_text(
                json.dumps(stale),
                encoding="utf-8",
            )

            runner = StepRunner(
                ROOT,
                task_dir,
                data_root=task_dir / "data",
                contract_profile="v0_3",
            )

            self.assertIn(
                "format.document",
                runner.skill_package.selected_capabilities,
            )
            self.assertNotIn(
                "format.ppt",
                runner.skill_package.selected_capabilities,
            )

    def test_v03_downstream_task_requires_resolved_upstream_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            raw_brief_path = run_dir / "raw_brief.json"
            raw_brief_path.write_text(
                '{"topic":"测试","audience":"strategy_lead","decision_goal":"决策"}',
                encoding="utf-8",
            )
            executor = WorkerExecutor(
                ROOT,
                run_dir,
                run_dir / "data",
                contract_profile="v0_3",
            )
            packet = {
                "task_id": "storyline-001",
                "agent_id": "storyline",
                "objective": "形成故事线",
                "input_artifacts": ["missing-analysis.json"],
                "acceptance_criteria": ["结构有效"],
            }
            with self.assertRaisesRegex(
                StepError, "无法解析的 input_artifacts"
            ):
                executor.create_task(
                    packet,
                    read_json(FIXTURES / "report_charter.v2.valid.json"),
                    raw_brief_path,
                )

            wrong_schema_path = run_dir / "wrong.json"
            wrong_schema_path.write_text(
                '{"schema":"report.v1"}',
                encoding="utf-8",
            )
            packet["input_artifacts"] = [str(wrong_schema_path)]
            with self.assertRaisesRegex(StepError, "缺少必需上游 analysis.v1"):
                executor.create_task(
                    packet,
                    read_json(FIXTURES / "report_charter.v2.valid.json"),
                    raw_brief_path,
                )

    def test_spawn_chain_uses_worker_reviewer_worker_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir)
            handoff = task_dir / "handoff"
            handoff.mkdir()
            input_path = task_dir / "input.json"
            input_path.write_text("{}", encoding="utf-8")
            (task_dir / "run_state.json").write_text(
                '{"agent_id":"analysis"}',
                encoding="utf-8",
            )
            executor = WorkerExecutor(
                ROOT,
                task_dir,
                task_dir / "data",
                contract_profile="v0_3",
            )

            roles = {}
            for step in ("gen", "review", "revise"):
                request = executor._build_spawn_request(
                    task_dir,
                    {
                        "step": step,
                        "instruction_path": str(
                            handoff / f"instruction_{step}.md"
                        ),
                        "output_path": str(handoff / f"output_{step}.json"),
                        "input_path": str(input_path),
                    },
                )
                roles[step] = request.role
                if step == "review":
                    detail = WorkBuddySpawnAdapter().spawn(request).detail
                    self.assertEqual(detail["subagent_type"], "Explore")
                    self.assertEqual(detail["result_delivery"], "host_relay")

            self.assertEqual(
                roles,
                {"gen": "worker", "review": "reviewer", "revise": "worker"},
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
                    ["analysis", "storyline", "report", "format", "qa_preparation"],
                )

    def test_default_profile_activates_document_first_v03(self) -> None:
        profile = load_agent_profile(ROOT)
        self.assertEqual(profile.contract_profile, "v0_3")
        self.assertEqual(
            profile.profile_config["schema_gate_mode"],
            "advisory",
        )
        self.assertEqual(
            [spec.id for spec in profile.ordered_specs],
            ["analysis", "storyline", "report", "format", "qa_preparation"],
        )
        self.assertNotIn("evidence_harvester", profile.specs)
        self.assertIn("evidence_harvester", profile.support_specs)
        self.assertIn("qa_preparation", profile.specs)
        self.assertNotIn("speaker_script", profile.specs)

    def test_default_manager_entry_uses_five_public_stages(self) -> None:
        source = FIXTURES / "golden_cases" / "mixed_deep_dive" / "input.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            brief = normalize_brief(source, ROOT)
            brief_path = run_dir / "raw_brief.json"
            brief_path.write_text(
                json.dumps(brief, ensure_ascii=False), encoding="utf-8"
            )
            manager = ManagerOrchestrator(ROOT, run_dir)
            prepared = manager.initialize_run(brief_path)

        self.assertEqual(manager.contract_profile, "v0_3")
        self.assertEqual(prepared["brief"]["delivery_targets"], ["document"])
        self.assertEqual(
            prepared["selected_workers"],
            ["analysis", "storyline", "report", "format", "qa_preparation"],
        )
        self.assertNotIn("evidence_harvester", prepared["selected_workers"])

    def test_explicit_v03_loads_executable_five_stage_specs(self) -> None:
        profile = load_agent_profile(ROOT, "v0_3")
        self.assertEqual(
            [spec.id for spec in profile.ordered_specs],
            ["analysis", "storyline", "report", "format", "qa_preparation"],
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
        self.assertEqual(profile.specs["format"].next_agent_id, "qa_preparation")
        self.assertIsNone(profile.specs["qa_preparation"].next_agent_id)
        self.assertEqual(
            profile.specs["qa_preparation"].input_schema,
            "formatted_material.v2",
        )

    def test_loop_runner_accepts_explicit_profile_without_running_a_model(self) -> None:
        runner = LoopRunner(ROOT, provider_override="mock", contract_profile="v0_3")
        self.assertEqual(runner.contract_profile, "v0_3")
        self.assertEqual(
            [spec.id for spec in runner.list_agents()],
            ["analysis", "storyline", "report", "format", "qa_preparation"],
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
            ["analysis", "storyline", "report", "format", "qa_preparation"],
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
