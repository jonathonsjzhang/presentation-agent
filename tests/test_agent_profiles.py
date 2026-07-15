from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from presentation_agent.agent_profiles import load_agent_profile
from presentation_agent.loop import LoopRunner
from presentation_agent.launch import normalize_brief
from presentation_agent.manager import (
    ManagerAgentRuntime,
    ManagerOrchestrator,
    WorkerExecutor,
    _should_pause,
)
from presentation_agent.context import ContextAssembler
from presentation_agent.cli import build_parser, _current_instruction
from presentation_agent.step import PipelineStepper, StepError, StepRunner
from presentation_agent.spawn import WorkBuddySpawnAdapter
from presentation_agent.skill_package import load_skill_package


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v0_3"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class AgentProfileLoaderTests(unittest.TestCase):
    def test_report_builder_requires_workbuddy_question_tool_call(self) -> None:
        instructions = (ROOT / "skills" / "report_builder" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("下一步唯一合法动作是实际调用 `AskUserQuestion` 工具", instructions)
        self.assertIn("ask_user_question_payload", instructions)
        self.assertIn("禁止只把问题写成普通文本", instructions)
        self.assertIn('"options": []', instructions)
        self.assertIn("同一个工具调用中原样传入 4 个问题", instructions)
        self.assertIn("`presentation_text`（即完整 `present_to_user`）", instructions)
        self.assertIn("禁止把 Brief 塞进某一道题", instructions)
        self.assertIn("独立且不带任何 tool call", instructions)
        self.assertIn("同时含有 `tool_calls`", instructions)

    def test_user_facing_report_start_defaults_to_v04(self) -> None:
        args = build_parser().parse_args(
            [
                "report",
                "start",
                "--brief-file",
                "brief.json",
                "--spawn-adapter",
                "codex",
            ]
        )
        self.assertEqual(args.contract_profile, "v0_4")
        self.assertEqual(args.spawn_adapter, "codex")
        approve = build_parser().parse_args(
            [
                "report",
                "approve",
                "--run",
                "run-id",
                "--run-mode",
                "full_auto",
                "--delivery-option",
                "format:ppt",
            ]
        )
        self.assertEqual(approve.run_mode, "full_auto")
        self.assertEqual(approve.delivery_option, "format:ppt")
        default_approve = build_parser().parse_args(
            ["report", "approve", "--run", "run-id"]
        )
        self.assertIsNone(default_approve.run_mode)
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

    def test_user_facing_report_start_requires_worker_spawn_adapter(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(
                ["report", "start", "--brief-file", "brief.json"]
            )

    def test_worker_spawn_is_normalized_as_current_instruction(self) -> None:
        instruction = {
            "actor": "worker",
            "step": "gen",
            "spawn": {"status": "dispatched", "adapter": "workbuddy"},
        }
        for result in (instruction, {"instruction": instruction}):
            exposed = _current_instruction(result)
            self.assertEqual(exposed, instruction)

    def test_default_run_mode_pauses_after_analysis_and_storyline(self) -> None:
        self.assertTrue(_should_pause(None, "analysis"))
        self.assertTrue(_should_pause(None, "storyline"))
        self.assertFalse(_should_pause(None, "report"))
        self.assertFalse(_should_pause(None, "format"))
        self.assertFalse(_should_pause(None, "qa_preparation"))

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
            confirmation = prepared["present_to_user"]
            for hidden_worker in (
                "evidence_harvester",
                "argument_synthesis",
                "page_filling",
                "speaker_script",
            ):
                self.assertNotIn(hidden_worker, confirmation)
            self.assertIn(
                "analysis（分析） → storyline（故事线） → report（报告产出） → qa_preparation（追问清单） → format（可视化排版）",
                confirmation,
            )
            self.assertIn("是否发起review sub_agent", confirmation)
            self.assertIn("否（更高效）", confirmation)
            self.assertNotIn("`qa_preparation` QA 梳理", confirmation)
            expected_order = [
                "**报告主题**",
                "**听众**",
                "**项目类型**",
                "**交付形式**",
                "**报告篇幅**",
                "**agent执行流程**",
                "**是否发起review sub_agent**",
            ]
            positions = [confirmation.index(item) for item in expected_order]
            self.assertEqual(positions, sorted(positions))
            self.assertIn("研究背景", confirmation)
            self.assertNotIn("研究目的", confirmation)
            self.assertIn("当前研究 hypo", confirmation)
            question_headers = [item["header"] for item in prepared["questions"]]
            self.assertIn("研究背景", question_headers)
            self.assertNotIn("研究目的", question_headers)
            self.assertIn("当前研究 hypo", question_headers)
            self.assertIn("高可信论据", question_headers)
            self.assertNotIn("Review模式", question_headers)
            self.assertNotIn("运行模式", question_headers)
            self.assertEqual(prepared["brief"]["delivery_targets"], ["document"])
            self.assertEqual(
                manager.status()["state"]["contract_profile"], "v0_3"
            )
            self.assertNotIn("review_mode_options", prepared)
            self.assertEqual(len(prepared["questions"]), 4)
            self.assertEqual(
                prepared["brief_stage"], "collection_and_confirmation"
            )
            self.assertFalse(prepared["confirmation_ready"])
            self.assertTrue(prepared["interaction_required"])
            self.assertEqual(prepared["preferred_tool"], "AskUserQuestion")
            self.assertTrue(prepared["must_call_tool_before_next_cli"])
            self.assertEqual(
                prepared["next_action"],
                "host_call_AskUserQuestion_then_report_feedback",
            )
            self.assertTrue(
                all(
                    question.get("options") == []
                    for question in prepared["questions"][:3]
                )
            )
            self.assertEqual(prepared["questions"][3]["header"], "Brief确认")
            self.assertTrue(prepared["presentation_required_before_tool"])
            self.assertEqual(
                prepared["presentation_text"], prepared["present_to_user"]
            )
            self.assertEqual(
                prepared["presentation_delivery_mode"],
                "separate_user_visible_message_before_tool",
            )
            self.assertEqual(
                prepared["host_action_sequence"],
                ["send_present_to_user_message", "call_AskUserQuestion"],
            )
            self.assertIn("## Brief 草案", prepared["presentation_text"])
            self.assertNotIn(
                "Brief 草案", prepared["questions"][0]["question"]
            )
            self.assertEqual(
                prepared["ask_user_question_payload"]["questions"],
                [
                    {
                        "question": question["question"],
                        "header": question["header"],
                        "options": question.get("options", []),
                        "multiSelect": False,
                    }
                    for question in prepared["questions"]
                ],
            )
            self.assertNotIn("用户提供", json.dumps(prepared, ensure_ascii=False))
            self.assertNotIn("用户填写", json.dumps(prepared, ensure_ascii=False))
            with self.assertRaises(StepError):
                manager.approve()

            incomplete = manager.record_human_feedback(json.dumps({
                "brief_confirmed": True,
            }))
            self.assertTrue(incomplete["interaction_required"])
            self.assertIn("缺少字段", incomplete["feedback_error"])

            prepared = manager.record_human_feedback(json.dumps({
                "research_background": "测试主题近期成为业务优先议题",
                "research_direction": "测试主题由价值提升驱动",
                "high_confidence_evidence": [],
                "brief_confirmed": True,
            }, ensure_ascii=False))
            self.assertEqual(prepared["brief_stage"], "confirmed")
            self.assertTrue(prepared["confirmation_ready"])
            self.assertEqual(
                prepared["next_action"],
                "report_approve_without_asking_again",
            )
            self.assertFalse(prepared["interaction_required"])
            self.assertEqual(prepared["questions"], [])
            self.assertIn("Brief 最终确认", prepared["present_to_user"])
            self.assertIn("测试主题近期成为业务优先议题", prepared["present_to_user"])
            self.assertIn("用户标记的高可信论据", prepared["present_to_user"])

            prepared = manager.record_human_feedback(json.dumps({
                "brief_updates": {"topic": "修改后的测试主题"},
                "brief_confirmed": False,
            }, ensure_ascii=False))
            self.assertEqual(prepared["brief_stage"], "confirmation")
            self.assertIn("修改后的测试主题", prepared["present_to_user"])
            self.assertEqual(prepared["questions"][0]["header"], "Brief确认")
            prepared = manager.record_human_feedback(json.dumps({
                "brief_confirmed": True,
            }, ensure_ascii=False))
            manager.approve()
            approved_state = manager.status()["state"]
            self.assertEqual(approved_state["run_mode"], ["analysis", "storyline"])

    def test_brief_gate_exposes_evidence_confidence_text_input(self) -> None:
        brief = normalize_brief(
            {
                "topic": "AI 产品",
                "research_purpose": "判断成果保存是否值得优先验证",
                "research_direction": "优先讨论复用路径而不是单纯提醒",
                "materials": [
                    {
                        "material_id": "m1",
                        "claim": "保存成果用户的回访率更高",
                        "evidence": ["保存成果组 D7 回访率 34%，单轮问答组 18%"],
                    }
                ],
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
            prepared = ManagerOrchestrator(
                ROOT, run_dir, contract_profile="v0_3"
            ).initialize_run(brief_path)

        evidence_question = next(
            question
            for question in prepared["questions"]
            if question["header"] == "高可信论据"
        )
        self.assertFalse(evidence_question["multiSelect"])
        self.assertEqual(evidence_question["inputType"], "text")
        self.assertEqual(evidence_question["options"], [])
        self.assertEqual(
            prepared["evidence_options"][0]["label"],
            "保存成果用户的回访率更高",
        )
        self.assertIn("保存成果组 D7 回访率", prepared["present_to_user"])
        self.assertEqual(
            prepared["brief_stage"], "collection_and_confirmation"
        )
        self.assertEqual(len(prepared["questions"]), 4)
        self.assertEqual(
            [question["header"] for question in prepared["questions"]],
            ["研究背景", "当前研究 hypo", "高可信论据", "Brief确认"],
        )

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
                "analysis → storyline → report → qa_preparation → format(document)",
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
                ("analysis", "storyline", "report", "qa_preparation", "format"),
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
        qa_state = {
            "current_task": {"agent_id": "qa_preparation"},
            "last_event": "worker_completed",
        }
        self.assertTrue(
            ManagerAgentRuntime._v03_acceptance_route_errors(
                "complete", qa_state, None
            )
        )
        self.assertEqual(
            ManagerAgentRuntime._v03_acceptance_route_errors(
                "dispatch",
                qa_state,
                {"agent_id": "format"},
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

    def test_v03_acceptance_synthesizes_packet_and_binds_formal_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            task_dir = run_dir / "tasks" / "analysis-001_analysis"
            artifact_path = task_dir / "artifact.json"
            write_json_file(
                artifact_path,
                read_json(FIXTURES / "analysis.v1.valid.json"),
            )
            write_json_file(
                run_dir / "manager_state.json",
                {
                    "current_task": {
                        "task_id": "analysis-001",
                        "agent_id": "analysis",
                        "artifact_path": str(artifact_path),
                    },
                    "worker_result": {"artifact_path": str(artifact_path)},
                },
            )
            runtime = ManagerAgentRuntime(
                ROOT,
                run_dir,
                run_dir / "data",
                contract_profile="v0_3",
            )
            write_json_file(
                runtime.output_path("acceptance"),
                {
                    "action": "dispatch",
                    "acceptance_report": {
                        "verdict": "accept",
                        "reason": "analysis accepted",
                    },
                },
            )

            decision = runtime.read_decision("acceptance")

            self.assertEqual(decision["task_packet"]["agent_id"], "storyline")
            self.assertEqual(
                decision["task_packet"]["input_artifacts"],
                [str(artifact_path)],
            )
            self.assertEqual(
                decision["acceptance_report"]["task_id"],
                "analysis-001",
            )
            self.assertTrue(decision.get("runtime_normalizations"))

    def test_v03_revision_feedback_uses_current_acceptance_round(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            old_packet = {
                "agent_id": "report",
                "objective": "修订报告",
                "input_artifacts": ["storyline.json"],
                "revision_feedback": ["正文控制在1800-2000字符"],
            }
            write_json_file(
                run_dir / "manager_state.json",
                {
                    "current_task": {
                        "task_id": "report-001",
                        "agent_id": "report",
                        "packet": old_packet,
                    },
                    "tasks": [
                        {
                            "task_id": "report-001",
                            "agent_id": "report",
                            "packet": old_packet,
                        }
                    ],
                    "worker_result": {"artifact": {}},
                },
            )
            runtime = ManagerAgentRuntime(
                ROOT,
                run_dir,
                run_dir / "data",
                contract_profile="v0_3",
            )
            write_json_file(
                runtime.output_path("acceptance"),
                {
                    "action": "revise",
                    "acceptance_report": {
                        "verdict": "revise",
                        "reason": "继续压缩并拆分方法边界",
                        "revision_requirements": [
                            "正文控制在1500-1700字符",
                            "方法与边界使用独立字段",
                        ],
                    },
                },
            )

            decision = runtime.read_decision("acceptance")

            self.assertEqual(
                decision["task_packet"]["revision_feedback"],
                [
                    "正文控制在1500-1700字符",
                    "方法与边界使用独立字段",
                ],
            )

    def test_worker_artifact_resolver_prefers_artifact_over_handoff_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            task_dir = run_dir / "tasks" / "analysis-001_analysis"
            artifact_path = task_dir / "artifact.json"
            handoff_path = task_dir / "handoff" / "output_gen.json"
            write_json_file(
                artifact_path,
                read_json(FIXTURES / "analysis.v1.valid.json"),
            )
            write_json_file(handoff_path, {"schema": "analysis.v1"})
            executor = WorkerExecutor(
                ROOT,
                run_dir,
                run_dir / "data",
                contract_profile="v0_3",
            )

            self.assertEqual(
                executor._resolve_artifact(str(handoff_path)),
                artifact_path.resolve(),
            )

    def test_manager_commit_failure_rolls_back_to_retryable_output_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            task_dir = run_dir / "tasks" / "analysis-001_analysis"
            artifact_path = task_dir / "artifact.json"
            artifact = read_json(FIXTURES / "analysis.v1.valid.json")
            write_json_file(artifact_path, artifact)
            task = {
                "task_id": "analysis-001",
                "agent_id": "analysis",
                "task_dir": str(task_dir),
                "artifact_path": str(artifact_path),
                "status": "worker_completed",
            }
            manager = ManagerOrchestrator(
                ROOT,
                run_dir,
                contract_profile="v0_3",
            )
            manager._save_state(
                {
                    "version": "manager_state.v2",
                    "run_id": "rollback-test",
                    "contract_profile": "v0_3",
                    "current_actor": "manager",
                    "manager_phase": "acceptance",
                    "manager_step": "awaiting_output",
                    "human_gate": None,
                    "current_task": task,
                    "tasks": [task],
                    "worker_result": {
                        "artifact_path": str(artifact_path),
                        "artifact": artifact,
                    },
                    "accepted_artifacts": [],
                    "project_state": {},
                    "run_mode": "full_auto",
                    "report_charter": {},
                    "review_subagents_enabled": False,
                }
            )
            write_json_file(
                run_dir / "manager_plan.json",
                {
                    "plan_id": "runtime-canonical-chain",
                    "tasks": [
                        {
                            "task_id": "analysis-001",
                            "agent_id": "analysis",
                            "status": "completed",
                        }
                    ],
                },
            )
            write_json_file(
                manager.agent.output_path("acceptance"),
                {
                    "action": "dispatch",
                    "acceptance_report": {
                        "verdict": "accept",
                        "reason": "analysis accepted",
                    },
                },
            )

            with patch.object(
                manager,
                "_dispatch",
                side_effect=StepError("simulated dispatch failure"),
            ), self.assertRaisesRegex(StepError, "simulated dispatch failure"):
                manager.commit_manager()

            restored = manager.status()["state"]
            self.assertEqual(restored["current_actor"], "manager")
            self.assertEqual(restored["manager_step"], "awaiting_output")
            self.assertIsNone(restored["human_gate"])
            self.assertEqual(restored["last_event"], "manager_commit_failed")
            self.assertIn("report next", restored["last_error"]["recovery"])

    def test_format_render_failure_is_reported_before_missing_page_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            task_dir = run_dir / "tasks" / "format-001_format"
            artifact_path = task_dir / "artifact.json"
            render_detail = "可视化论据检查未通过：缺少可绘制的完整数据"
            artifact = {
                "agent_id": "format",
                "schema": "formatted_material.v2",
                "delivery_target": "document",
                "visuals": [],
                "render_result": {
                    "status": "error",
                    "target": "document",
                    "output_path": "",
                    "detail": render_detail,
                },
            }
            write_json_file(artifact_path, artifact)
            task = {
                "task_id": "format-001",
                "agent_id": "format",
                "task_dir": str(task_dir),
                "artifact_path": str(artifact_path),
                "status": "worker_completed",
            }
            manager = ManagerOrchestrator(
                ROOT,
                run_dir,
                contract_profile="v0_3",
            )
            manager._save_state(
                {
                    "version": "manager_state.v2",
                    "run_id": "format-error-priority-test",
                    "contract_profile": "v0_3",
                    "current_actor": "manager",
                    "manager_phase": "acceptance",
                    "manager_step": "awaiting_output",
                    "human_gate": None,
                    "current_task": task,
                    "tasks": [task],
                    "worker_result": {
                        "artifact_path": str(artifact_path),
                        "artifact": artifact,
                        "render_result": artifact["render_result"],
                    },
                    "accepted_artifacts": [],
                    "project_state": {
                        "delivery_budget": {"body_page_limit": 7}
                    },
                    "run_mode": "full_auto",
                    "report_charter": {},
                    "review_subagents_enabled": False,
                }
            )
            write_json_file(
                manager.agent.output_path("acceptance"),
                {
                    "action": "complete",
                    "acceptance_report": {
                        "verdict": "accept",
                        "reason": "format accepted",
                    },
                },
            )

            with self.assertRaisesRegex(StepError, "可视化论据检查未通过") as caught:
                manager.commit_manager()

            self.assertNotIn("正文页数硬约束未通过", str(caught.exception))

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
            self.assertTrue(gate["interaction_required"])
            self.assertEqual(gate["preferred_tool"], "AskUserQuestion")
            self.assertEqual(
                gate["ask_user_question_payload"]["questions"][0]["header"],
                "追加交付",
            )

            result = manager.approve(delivery_option="format:ppt")

            self.assertEqual(result["actor"], "manager")
            updated = manager.status()["state"]
            self.assertEqual(updated["last_event"], "human_feedback")
            self.assertIn(
                "format:ppt",
                updated["human_feedback"][-1]["text"],
            )

    def _analysis_gate_manager(
        self,
        run_dir: Path,
        *,
        with_task_files: bool = False,
    ) -> ManagerOrchestrator:
        manager = ManagerOrchestrator(
            ROOT,
            run_dir,
            contract_profile="v0_3",
        )
        artifact = read_json(FIXTURES / "analysis.v1.valid.json")
        task_dir = run_dir / "tasks" / "analysis-001_analysis"
        artifact_path = task_dir / "artifact.json"
        if with_task_files:
            input_path = task_dir / "input.json"
            write_json_file(
                input_path,
                {
                    "schema": "worker_context.v1",
                    "contract_profile": "v0_3",
                    "report_charter": {},
                    "manager_task": {
                        "agent_id": "analysis",
                        "objective": "形成可确认的论点组选项",
                        "input_artifacts": [],
                    },
                    "raw_brief": {},
                    "raw_materials": [
                        {
                            "material_type": "notes",
                            "notes": "测试材料",
                        }
                    ],
                    "input_readiness": {"status": "ready"},
                },
            )
            write_json_file(task_dir / "draft_round_0.json", artifact)
            write_json_file(artifact_path, artifact)
            write_json_file(
                task_dir / "run_state.json",
                {
                    "run_id": "analysis-001-run",
                    "task_id": "analysis-001",
                    "agent_id": "analysis",
                    "agent_name": "Analysis",
                    "stage": 1,
                    "status": "pending_human_review",
                    "current_step": "done",
                    "round_index": 0,
                    "max_revision_rounds": 2,
                    "input_path": str(input_path),
                    "manager_task": {
                        "agent_id": "analysis",
                        "objective": "形成可确认的论点组选项",
                        "input_artifacts": [],
                    },
                    "resolved_input_artifacts": [],
                    "context_mode": "projected",
                    "context_manifest_path": "",
                    "output_dir": str(task_dir),
                    "p0_open": [],
                    "p1_open": [],
                    "produced_artifacts": [str(task_dir / "draft_round_0.json")],
                    "history": [],
                    "contract_profile": "v0_3",
                    "review_subagents_enabled": False,
                },
            )
        task = {
            "task_id": "analysis-001",
            "agent_id": "analysis",
            "agent_name": "Analysis",
            "task_dir": str(task_dir),
            "artifact_path": str(artifact_path),
            "status": "accepted",
        }
        state = {
            "version": "manager_state.v2",
            "run_id": "analysis-gate-test",
            "contract_profile": "v0_3",
            "status": "awaiting_intermediate_review",
            "current_actor": "human",
            "manager_phase": "acceptance",
            "manager_step": "decision_committed",
            "last_event": "worker_completed",
            "spawn_adapter": "inline",
            "human_gate": "worker_result",
            "current_task": task,
            "tasks": [task],
            "accepted_artifacts": [
                {
                    "task_id": "analysis-001",
                    "agent_id": "analysis",
                    "artifact_path": str(artifact_path),
                    "task_dir": str(task_dir),
                }
            ],
            "project_state": {},
            "run_mode": ["analysis", "storyline"],
            "review_mode": "schema_only",
            "review_subagents_enabled": False,
            "worker_result": {
                "task_id": "analysis-001",
                "agent_id": "analysis",
                "artifact_path": str(artifact_path),
                "artifact": artifact,
            },
            "pending_decision": {
                "action": "dispatch",
                "acceptance_report": {
                    "task_id": "analysis-001",
                    "verdict": "accept",
                    "reason": "analysis accepted",
                },
                "task_packet": {
                    "task_id": "storyline-001",
                    "agent_id": "storyline",
                    "objective": "形成故事线",
                    "input_artifacts": [str(artifact_path)],
                },
            },
        }
        manager._save_state(state)
        return manager

    def test_analysis_worker_result_exposes_thesis_selection_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._analysis_gate_manager(Path(temp_dir))

            gate = manager.prepare()

            self.assertEqual(gate["next_action"], "human_feedback")
            self.assertIn("Analysis 论点组确认", gate["present_to_user"])
            self.assertIn("TG-01", gate["present_to_user"])
            self.assertIn("论点组", gate["questions"][0]["header"])
            self.assertEqual(len(gate["questions"]), 1)
            self.assertEqual(gate["questions"][0]["inputType"], "text")
            self.assertEqual(gate["questions"][0]["options"], [])
            self.assertIn("TG-01 / TG-02", gate["questions"][0]["question"])
            self.assertIn("一个输入框", gate["questions"][0]["question"])
            self.assertTrue(gate["interaction_required"])
            self.assertEqual(gate["preferred_tool"], "AskUserQuestion")
            self.assertEqual(
                gate["ask_user_question_payload"]["questions"][0]["header"],
                "论点组确认",
            )

    def test_analysis_thesis_selection_is_stored_for_storyline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._analysis_gate_manager(Path(temp_dir))

            result = manager.record_human_feedback(
                "选择 TG-02，理由：更适合审慎推进验证。"
            )

            self.assertEqual(result["next_action"], "report_approve")
            updated = manager.status()["state"]
            selection = updated["project_state"]["analysis_thesis_selection"]
            self.assertEqual(selection["option_id"], "TG-02")
            packet = updated["pending_decision"]["task_packet"]
            self.assertEqual(
                packet["selected_analysis_thesis"]["option_id"],
                "TG-02",
            )

    def test_analysis_rewrite_feedback_reuses_current_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._analysis_gate_manager(
                Path(temp_dir),
                with_task_files=True,
            )

            result = manager.record_human_feedback(
                "都不好，原因：这些方案都太像事实摘要，没有形成对总办有用的取舍判断。"
            )

            self.assertEqual(result["actor"], "worker")
            self.assertEqual(result["step"], "revise")
            updated = manager.status()["state"]
            self.assertEqual(len(updated["tasks"]), 1)
            self.assertEqual(
                updated["current_task"]["task_dir"],
                str(Path(temp_dir) / "tasks" / "analysis-001_analysis"),
            )
            self.assertEqual(updated["accepted_artifacts"], [])
            run_state = read_json(
                Path(updated["current_task"]["task_dir"]) / "run_state.json"
            )
            self.assertEqual(run_state["current_step"], "awaiting_revise_output")
            self.assertEqual(run_state["round_index"], 1)
            instruction = Path(result["instruction_path"]).read_text(
                encoding="utf-8"
            )
            self.assertIn("这些方案都太像事实摘要", instruction)

    def test_analysis_custom_feedback_reuses_current_task_for_structuring(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._analysis_gate_manager(
                Path(temp_dir),
                with_task_files=True,
            )

            result = manager.record_human_feedback(
                "我自己修改：主论点改成首周留存关键不是提醒触达，而是用户是否形成可再次使用的成果；分论点保留样本自选择边界。"
            )

            self.assertEqual(result["actor"], "worker")
            self.assertEqual(result["step"], "revise")
            updated = manager.status()["state"]
            self.assertEqual(len(updated["tasks"]), 1)
            run_state = read_json(
                Path(updated["current_task"]["task_dir"]) / "run_state.json"
            )
            self.assertEqual(run_state["current_step"], "awaiting_revise_output")
            self.assertIn(
                "用户提供了自定义修改意见",
                run_state["p0_open"][0]["message"],
            )

    def test_analysis_rewrite_feedback_requires_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._analysis_gate_manager(Path(temp_dir))

            result = manager.record_human_feedback("都不好")

            self.assertEqual(result["actor"], "human")
            self.assertEqual(result["next_action"], "human_feedback")
            self.assertIn("需要说明原因", result["present_to_user"])
            updated = manager.status()["state"]
            self.assertEqual(updated["current_actor"], "human")
            self.assertIn("analysis_feedback_error", updated)

    def _storyline_gate_manager(
        self,
        run_dir: Path,
        *,
        with_task_files: bool = False,
    ) -> ManagerOrchestrator:
        manager = ManagerOrchestrator(
            ROOT,
            run_dir,
            contract_profile="v0_3",
        )
        artifact = read_json(FIXTURES / "storyline.v3.valid.json")
        analysis = read_json(FIXTURES / "analysis.v1.valid.json")
        task_dir = run_dir / "tasks" / "storyline-001_storyline"
        artifact_path = task_dir / "artifact.json"
        if with_task_files:
            input_path = task_dir / "input.json"
            write_json_file(
                input_path,
                {
                    "schema": "worker_context.v1",
                    "contract_profile": "v0_3",
                    "report_charter": read_json(
                        FIXTURES / "report_charter.v2.valid.json"
                    ),
                    "manager_task": {
                        "agent_id": "storyline",
                        "objective": "形成单版故事线",
                        "input_artifacts": [
                            str(run_dir / "tasks" / "analysis-001_analysis" / "artifact.json")
                        ],
                    },
                    "raw_brief": {},
                    "analysis": analysis,
                    "input_readiness": {"status": "ready"},
                },
            )
            write_json_file(task_dir / "draft_round_0.json", artifact)
            write_json_file(artifact_path, artifact)
            write_json_file(
                task_dir / "run_state.json",
                {
                    "run_id": "storyline-001-run",
                    "task_id": "storyline-001",
                    "agent_id": "storyline",
                    "agent_name": "Storyline",
                    "stage": 2,
                    "status": "pending_human_review",
                    "current_step": "done",
                    "round_index": 0,
                    "max_revision_rounds": 2,
                    "input_path": str(input_path),
                    "manager_task": {
                        "agent_id": "storyline",
                        "objective": "形成单版故事线",
                        "input_artifacts": [],
                    },
                    "resolved_input_artifacts": [],
                    "context_mode": "projected",
                    "context_manifest_path": "",
                    "output_dir": str(task_dir),
                    "p0_open": [],
                    "p1_open": [],
                    "produced_artifacts": [str(task_dir / "draft_round_0.json")],
                    "history": [],
                    "contract_profile": "v0_3",
                    "review_subagents_enabled": False,
                },
            )
        task = {
            "task_id": "storyline-001",
            "agent_id": "storyline",
            "agent_name": "Storyline",
            "task_dir": str(task_dir),
            "artifact_path": str(artifact_path),
            "status": "accepted",
        }
        state = {
            "version": "manager_state.v2",
            "run_id": "storyline-gate-test",
            "contract_profile": "v0_3",
            "status": "awaiting_intermediate_review",
            "current_actor": "human",
            "manager_phase": "acceptance",
            "manager_step": "decision_committed",
            "last_event": "worker_completed",
            "spawn_adapter": "inline",
            "human_gate": "worker_result",
            "current_task": task,
            "tasks": [task],
            "accepted_artifacts": [
                {
                    "task_id": "storyline-001",
                    "agent_id": "storyline",
                    "artifact_path": str(artifact_path),
                    "task_dir": str(task_dir),
                }
            ],
            "project_state": {
                "analysis_thesis_selection": {
                    "option_id": "TG-01",
                    "main_thesis": "优先验证成果形成与复用闭环",
                }
            },
            "run_mode": ["analysis", "storyline"],
            "review_mode": "schema_only",
            "review_subagents_enabled": False,
            "report_charter": read_json(FIXTURES / "report_charter.v2.valid.json"),
            "worker_result": {
                "task_id": "storyline-001",
                "agent_id": "storyline",
                "artifact_path": str(artifact_path),
                "artifact": artifact,
            },
            "pending_decision": {
                "action": "dispatch",
                "acceptance_report": {
                    "task_id": "storyline-001",
                    "verdict": "accept",
                    "reason": "storyline accepted",
                },
                "task_packet": {
                    "task_id": "report-001",
                    "agent_id": "report",
                    "objective": "写作完整报告",
                    "input_artifacts": [str(artifact_path)],
                },
            },
        }
        manager._save_state(state)
        return manager

    def test_storyline_worker_result_exposes_single_storyline_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._storyline_gate_manager(Path(temp_dir))

            gate = manager.prepare()

            self.assertEqual(gate["next_action"], "report_approve_or_feedback")
            self.assertIn("Storyline 确认", gate["present_to_user"])
            self.assertIn("核心答案", gate["present_to_user"])
            self.assertIn("Executive Summary", gate["present_to_user"])
            self.assertIn("故事线", gate["present_to_user"])
            self.assertIn(
                "| 序号 | 章节 | 标题（Leadline） | 核心论证 |",
                gate["present_to_user"],
            )
            self.assertIn("行为差异与证据边界", gate["present_to_user"])
            self.assertIn(
                "成果保存与回访共同出现，但因果仍待验证",
                gate["present_to_user"],
            )
            values = [option["value"] for option in gate["questions"][0]["options"]]
            self.assertEqual(values, ["approve", "rewrite", "custom"])
            self.assertEqual(len(gate["questions"]), 1)
            self.assertEqual(gate["questions"][0]["header"], "Storyline确认")
            self.assertNotIn(
                "修改说明", [question["header"] for question in gate["questions"]]
            )
            self.assertTrue(gate["interaction_required"])
            self.assertEqual(gate["preferred_tool"], "AskUserQuestion")
            self.assertEqual(
                gate["ask_user_question_payload"]["questions"],
                [
                    {
                        "question": question["question"],
                        "header": question["header"],
                        "options": question.get("options", []),
                        "multiSelect": bool(question.get("multiSelect", False)),
                    }
                    for question in gate["questions"]
                ],
            )

    def test_storyline_approval_dispatches_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._storyline_gate_manager(
                Path(temp_dir),
                with_task_files=True,
            )

            result = manager.approve()

            self.assertEqual(result["actor"], "worker")
            updated = manager.status()["state"]
            self.assertEqual(updated["current_task"]["agent_id"], "report")
            self.assertEqual(
                updated["project_state"]["storyline_confirmation"]["status"],
                "approved",
            )

    def test_storyline_rewrite_feedback_reuses_current_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._storyline_gate_manager(
                Path(temp_dir),
                with_task_files=True,
            )

            result = manager.record_human_feedback(
                "不好，原因：现在像两个发现拼接，没有形成总办能顺着接受的认知推进。"
            )

            self.assertEqual(result["actor"], "worker")
            self.assertEqual(result["step"], "revise")
            updated = manager.status()["state"]
            self.assertEqual(len(updated["tasks"]), 1)
            self.assertEqual(
                updated["current_task"]["task_dir"],
                str(Path(temp_dir) / "tasks" / "storyline-001_storyline"),
            )
            self.assertEqual(updated["accepted_artifacts"], [])
            run_state = read_json(
                Path(updated["current_task"]["task_dir"]) / "run_state.json"
            )
            self.assertEqual(run_state["current_step"], "awaiting_revise_output")
            self.assertEqual(run_state["round_index"], 1)
            instruction = Path(result["instruction_path"]).read_text(
                encoding="utf-8"
            )
            self.assertIn("两个发现拼接", instruction)

    def test_storyline_custom_feedback_reuses_current_task_for_structuring(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._storyline_gate_manager(
                Path(temp_dir),
                with_task_files=True,
            )

            result = manager.record_human_feedback(
                "我自己修改：核心答案改成不是立刻加提醒，而是先证明可复用成果能形成再次打开理由；章节先讲证据边界，再讲机制。"
            )

            self.assertEqual(result["actor"], "worker")
            self.assertEqual(result["step"], "revise")
            updated = manager.status()["state"]
            self.assertEqual(len(updated["tasks"]), 1)
            run_state = read_json(
                Path(updated["current_task"]["task_dir"]) / "run_state.json"
            )
            self.assertEqual(run_state["current_step"], "awaiting_revise_output")
            self.assertIn(
                "用户提供了自定义 Storyline 修改意见",
                run_state["p0_open"][0]["message"],
            )

    def test_storyline_rewrite_feedback_requires_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._storyline_gate_manager(Path(temp_dir))

            result = manager.record_human_feedback("不好")

            self.assertEqual(result["actor"], "human")
            self.assertEqual(result["next_action"], "report_approve_or_feedback")
            self.assertIn("需要说明原因", result["present_to_user"])
            self.assertEqual(len(result["questions"]), 1)
            self.assertEqual(result["questions"][0]["header"], "修改说明")
            self.assertEqual(result["questions"][0]["options"], [])
            updated = manager.status()["state"]
            self.assertEqual(updated["current_actor"], "human")
            self.assertIn("storyline_feedback_error", updated)
            self.assertEqual(
                updated["project_state"]["storyline_pending_feedback_intent"],
                "rewrite",
            )

    def test_storyline_rewrite_detail_followup_reuses_pending_intent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._storyline_gate_manager(
                Path(temp_dir),
                with_task_files=True,
            )
            manager.record_human_feedback("不好")

            result = manager.record_human_feedback(
                "章节顺序缺少从现象到机制的递进关系"
            )

            self.assertEqual(result["actor"], "worker")
            self.assertEqual(result["step"], "revise")
            run_state = read_json(
                Path(manager.status()["state"]["current_task"]["task_dir"])
                / "run_state.json"
            )
            self.assertIn(
                "不好，原因：章节顺序缺少从现象到机制的递进关系",
                run_state["p0_open"][0]["evidence"],
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

    def test_worker_task_has_no_reviewer_control_flags(self) -> None:
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
            )
            task_state = read_json(Path(task["task_dir"]) / "run_state.json")
            self.assertNotIn("review_subagents_enabled", task_state)
            self.assertNotIn("review_mode", task_state)

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

    def test_spawn_chain_uses_worker_role_for_generation_and_revision(self) -> None:
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
            for step in ("gen", "revise"):
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
            self.assertEqual(
                roles,
                {"gen": "worker", "revise": "worker"},
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

    def test_v03_large_catalog_is_ready_when_canonical_input_is_full(self) -> None:
        assembler = ContextAssembler(ROOT, contract_profile="v0_3")
        charter = read_json(FIXTURES / "report_charter.v2.valid.json")
        catalog = {
            "schema": "evidence_catalog.v1",
            "items": [
                {
                    "id": f"EV-{index:03d}",
                    "source_ref": f"source-{index}",
                    "content": "完整论据内容" * 300,
                }
                for index in range(1, 39)
            ],
            "unresolved": [],
        }

        result = assembler.assemble(
            worker_id="analysis",
            report_charter=charter,
            manager_task={"acceptance_criteria": ["traceable"]},
            raw_brief={
                "schema": "raw_brief.v1",
                "evidence_catalog": catalog,
                "evidence_catalog_ref": "artifacts/evidence_catalog.json",
            },
            raw_brief_path=Path("artifacts/raw_brief.json"),
            artifacts=[],
        )

        self.assertEqual(
            result["raw_brief"]["evidence_catalog"]["_projection"],
            "object_index",
        )
        self.assertEqual(result["evidence_catalog"], catalog)
        self.assertEqual(result["input_readiness"]["status"], "ready")
        self.assertEqual(result["input_readiness"]["blocking_issues"], [])
        self.assertTrue(
            any(
                "evidence_catalog" in row.get("projected_fields", [])
                for row in result["material_refs"]
            )
        )

    def test_v03_golden_cases_run_evidence_intake_before_brief_when_needed(self) -> None:
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
                if case["case_id"] in {
                    "qualitative_interviews",
                    "quantitative_usage",
                }:
                    self.assertEqual(prepared["actor"], "worker")
                    self.assertTrue(prepared["evidence_intake"])
                    self.assertEqual(prepared["agent_id"], "evidence_harvester")
                    continue
                self.assertEqual(prepared["gate"], "brief")
                self.assertIn("研究背景", prepared["missing_fields"])
                self.assertIn("当前研究 hypo", prepared["missing_fields"])
                self.assertEqual(prepared["brief"]["delivery_targets"], ["document"])
                self.assertIn(
                    "analysis（分析） → storyline（故事线） → report（报告产出） → qa_preparation（追问清单） → format（可视化排版）",
                    prepared["present_to_user"],
                )

    def test_default_profile_activates_markdown_first_v04(self) -> None:
        profile = load_agent_profile(ROOT)
        self.assertEqual(profile.contract_profile, "v0_4")
        self.assertEqual(
            profile.profile_config["schema_gate_mode"],
            "advisory",
        )
        self.assertEqual(
            [spec.id for spec in profile.ordered_specs],
            ["analysis", "storyline", "report", "qa_preparation", "format"],
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

        self.assertEqual(manager.contract_profile, "v0_4")
        self.assertEqual(prepared["brief"]["delivery_targets"], ["document"])
        self.assertIn(
            "analysis（分析） → storyline（故事线） → report（报告产出） → qa_preparation（追问清单） → format（可视化排版）",
            prepared["present_to_user"],
        )
        self.assertNotIn("evidence_harvester", prepared["present_to_user"])

    def test_explicit_v03_loads_executable_five_stage_specs(self) -> None:
        profile = load_agent_profile(ROOT, "v0_3")
        self.assertEqual(
            [spec.id for spec in profile.ordered_specs],
            ["analysis", "storyline", "report", "qa_preparation", "format"],
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
        self.assertEqual(profile.specs["report"].next_agent_id, "qa_preparation")
        self.assertEqual(profile.specs["qa_preparation"].next_agent_id, "format")
        self.assertIsNone(profile.specs["format"].next_agent_id)
        self.assertEqual(
            profile.specs["qa_preparation"].input_schema,
            "report.v1",
        )

    def test_loop_runner_accepts_explicit_profile_without_running_a_model(self) -> None:
        runner = LoopRunner(ROOT, provider_override="mock", contract_profile="v0_3")
        self.assertEqual(runner.contract_profile, "v0_3")
        self.assertEqual(
            [spec.id for spec in runner.list_agents()],
            ["analysis", "storyline", "report", "qa_preparation", "format"],
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
            ["analysis", "storyline", "report", "qa_preparation", "format"],
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
                done = runner.commit()
                self.assertEqual(done["step"], "done")
                self.assertEqual(done["agent_id"], agent_id)
                self.assertFalse(read_json(stage_dir / "run_state.json")["p0_open"])

                if index < 2:
                    stage = stepper.advance_stage()


if __name__ == "__main__":
    unittest.main()
