from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from presentation_agent.agent_profiles import LEGACY_CONTRACT_PROFILE
from presentation_agent.io import read_json, write_json
from presentation_agent.manager import ManagerOrchestrator
from presentation_agent.memory_router import MemoryRouter
from presentation_agent.step import StepError


ROOT = Path(__file__).resolve().parents[1]


def _planning_decision() -> dict:
    return {
        "schema": "manager_decision.v1",
        "phase": "planning",
        "action": "dispatch",
        "reason_summary": "先提炼核心论点",
        "report_charter": {
            "topic": "用户时长战略分析",
            "audience": "exec_office",
            "report_type": "deep_dive",
            "output_format": "ppt",
            "decision_goal": "判断下一阶段增长重点",
            "expected_action": "确认资源优先级",
            "scope": ["用户时长"],
            "out_of_scope": ["广告变现"],
            "constraints": ["不编造数据"],
            "success_criteria": ["形成可拍板结论"],
            "recommendation_granularity": "strategic_direction",
            "unsupported_specificity_policy": "forbid",
            "evidence_inventory_policy": "lightweight_prepass",
            "material_inventory": [],
            "global_state_seed": {
                "audience_profile": "exec_office",
                "target_action": "确认资源优先级",
            },
            "blocking_questions": [],
            "assumptions": [],
        },
        "execution_plan": {
            "plan_id": "plan-001",
            "tasks": [{
                "task_id": "argument-001",
                "agent_id": "argument_synthesis",
                "objective": "形成核心论点",
                "dependencies": [],
                "status": "planned",
            }],
            "human_gates": ["plan", "final"],
            "completion_criteria": ["形成正式汇报材料"],
            "planning_notes": [],
        },
        "task_packet": {
            "task_id": "argument-001",
            "agent_id": "argument_synthesis",
            "objective": "形成核心论点和证据链",
            "input_artifacts": ["raw_brief.json"],
            "context": {"audience": "exec_office"},
            "constraints": ["不编造数据"],
            "deliverables": {"schema": "argument_synthesis.v1"},
            "acceptance_criteria": ["结论可决策", "证据可追溯", "action 明确"],
            "dependencies": [],
            "memory_dimensions": ["结论", "证据", "Action"],
            "recommendation_granularity": "strategic_direction",
            "unsupported_specificity_policy": "forbid",
            "evidence_inventory_policy": "lightweight_prepass",
            "revision_of": None,
            "revision_feedback": [],
        },
        "state_updates": {},
        "questions_for_human": [],
        "user_message": "请确认任务定义和执行计划。",
        "memory_candidates": [],
    }


def _completion_decision(task_id: str) -> dict:
    return {
        "schema": "manager_decision.v1",
        "phase": "acceptance",
        "action": "complete",
        "reason_summary": "全部交付标准已经满足",
        "acceptance_report": {
            "task_id": task_id,
            "verdict": "accept",
            "criteria_results": [
                {"criterion": "结论可决策", "passed": True, "evidence": "artifact"}
            ],
            "cross_stage_findings": [],
            "reason": "产物满足任务和项目目标",
            "revision_requirements": [],
        },
        "state_updates": {},
        "questions_for_human": [],
        "user_message": "Manager 已完成整体验收，请确认最终交付。",
        "memory_candidates": [],
    }


class ManagerOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.run_dir = root / "run"
        self.data_root = root / "data"
        self.brief = root / "brief.json"
        write_json(self.brief, {
            "topic": "用户时长战略分析",
            "audience": "exec_office",
            "report_type": "deep_dive",
            "output_format": "ppt",
            "decision_goal": "判断下一阶段增长重点",
            "materials": [],
        })

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _manager(self, **kwargs) -> ManagerOrchestrator:
        return ManagerOrchestrator(
            ROOT,
            self.run_dir,
            data_root=self.data_root,
            contract_profile=LEGACY_CONTRACT_PROFILE,
            **kwargs,
        )

    def test_plan_gate_then_dispatches_first_worker(self) -> None:
        manager = self._manager()
        brief_gate = manager.initialize_run(self.brief)
        self.assertEqual(brief_gate["gate"], "brief")
        manager.approve()  # confirm brief → planning
        instruction = manager.prepare()

        self.assertEqual(instruction["actor"], "manager")
        self.assertEqual(instruction["step"], "planning")
        write_json(Path(instruction["output_path"]), _planning_decision())

        gate = manager.commit_manager()
        self.assertEqual(gate["gate"], "plan")
        self.assertEqual(manager.status()["state"]["current_actor"], "human")
        self.assertTrue((self.run_dir / "report_charter.json").exists())
        self.assertTrue((self.run_dir / "manager_plan.json").exists())

        dispatched = manager.approve()
        self.assertEqual(dispatched["actor"], "worker")
        self.assertEqual(dispatched["task"]["agent_id"], "argument_synthesis")
        task_dir = Path(dispatched["task"]["task_dir"])
        worker_input = read_json(task_dir / "input.json")
        self.assertEqual(worker_input["schema"], "worker_context.v1")
        self.assertIn("report_charter", worker_input)
        self.assertIn("manager_task", worker_input)
        self.assertIn("inputs", worker_input)
        self.assertNotIn("topic", worker_input)
        context_manifest = read_json(task_dir / "context_manifest.json")
        self.assertEqual(context_manifest["mode"], "projected")
        self.assertEqual(context_manifest["worker_id"], "argument_synthesis")
        run_state = read_json(task_dir / "run_state.json")
        self.assertEqual(run_state["context_mode"], "projected")
        state = manager.status()["state"]
        self.assertEqual(
            state["current_task"]["capability_fingerprint"],
            run_state["skill_fingerprint"],
        )
        self.assertIn(
            "audience.exec_office",
            state["current_task"]["selected_capabilities"],
        )
        self.assertTrue(Path(dispatched["instruction"]["instruction_path"]).exists())

    def test_manager_context_exposes_profile_registry_and_route(self) -> None:
        manager = self._manager()
        manager.initialize_run(self.brief)
        manager.approve()  # confirm brief → planning
        state = manager.status()["state"]
        context = manager._manager_context(state)

        self.assertEqual(context["report_profile"]["report_type"], "deep_dive")
        self.assertEqual(context["capability_registry"]["atomic_capability_count"], 11)
        self.assertIn("qa_preparation", context["recommended_routes"]["default"])

    def test_existing_legacy_run_keeps_its_persisted_profile(self) -> None:
        manager = self._manager()
        manager.initialize_run(self.brief)

        resumed = ManagerOrchestrator(
            ROOT,
            self.run_dir,
            data_root=self.data_root,
        )

        self.assertEqual(
            resumed.contract_profile,
            LEGACY_CONTRACT_PROFILE,
        )

    def test_spawn_adapter_persists_and_annotates_first_worker(self) -> None:
        manager = self._manager(spawn_adapter="workbuddy")
        brief_gate = manager.initialize_run(self.brief)
        self.assertEqual(brief_gate["gate"], "brief")
        manager.approve()  # confirm brief → planning
        self.assertEqual(manager.status()["state"]["spawn_adapter"], "workbuddy")

        # Simulate the next CLI process: no override is passed, so it must recover
        # the adapter from this run's manager_state.json.
        manager = self._manager()
        self.assertEqual(manager.workers.spawn_adapter.kind, "workbuddy")
        instruction = manager.prepare()
        write_json(Path(instruction["output_path"]), _planning_decision())
        manager.commit_manager()
        dispatched = manager.approve()

        spawn = dispatched["instruction"]["spawn"]
        self.assertEqual(spawn["adapter"], "workbuddy")
        self.assertEqual(spawn["role"], "worker")
        self.assertEqual(spawn["status"], "dispatched")
        self.assertTrue(
            Path(spawn["detail"]["spawn_request"]).exists()
        )

    def test_worker_completion_returns_to_manager_acceptance(self) -> None:
        manager = self._manager()
        brief_gate = manager.initialize_run(self.brief)
        self.assertEqual(brief_gate["gate"], "brief")
        manager.approve()  # confirm brief → planning
        instruction = manager.prepare()
        write_json(Path(instruction["output_path"]), _planning_decision())
        manager.commit_manager()
        dispatched = manager.approve()
        task_dir = Path(dispatched["task"]["task_dir"])
        artifact_path = task_dir / "artifact.json"
        write_json(artifact_path, {
            "schema": "argument_synthesis.v1",
            "agent_id": "argument_synthesis",
            "core_thesis": "应优先提升高价值场景时长",
        })
        run_state = read_json(task_dir / "run_state.json")
        run_state["current_step"] = "done"
        run_state["status"] = "pending_manager_acceptance"
        write_json(task_dir / "run_state.json", run_state)

        result = manager.record_worker_completed({
            "step": "done",
            "artifact_path": str(artifact_path),
            "review_summary": "P0=0",
            "memory_notes": "",
        })

        self.assertEqual(result["actor"], "manager")
        self.assertEqual(result["step"], "acceptance")
        state = manager.status()["state"]
        self.assertEqual(state["manager_phase"], "acceptance")
        self.assertEqual(state["current_actor"], "manager")

    def test_invalid_manager_plan_is_rejected(self) -> None:
        manager = self._manager()
        brief_gate = manager.initialize_run(self.brief)
        self.assertEqual(brief_gate["gate"], "brief")
        manager.approve()  # confirm brief → planning
        instruction = manager.prepare()
        write_json(Path(instruction["output_path"]), {
            "phase": "planning",
            "action": "dispatch",
            "reason_summary": "missing contracts",
            "user_message": "",
        })
        with self.assertRaises(StepError):
            manager.commit_manager()

    def test_deep_dive_full_catalog_requires_harvester_first(self) -> None:
        manager = self._manager()
        manager.initialize_run(self.brief)
        manager.approve()
        instruction = manager.prepare()
        decision = _planning_decision()
        decision["report_charter"][
            "evidence_inventory_policy"
        ] = "full_catalog_for_deep_dive"
        decision["task_packet"][
            "evidence_inventory_policy"
        ] = "full_catalog_for_deep_dive"
        write_json(Path(instruction["output_path"]), decision)

        with self.assertRaises(StepError):
            manager.commit_manager()

    def test_plan_feedback_returns_to_manager_planning(self) -> None:
        manager = self._manager()
        # Step 1: brief confirmation gate
        brief_gate = manager.initialize_run(self.brief)
        self.assertEqual(brief_gate["gate"], "brief")
        # Step 2: confirm brief → transition to planning
        manager.approve()
        # Step 3: prepare planning instruction
        instruction = manager.prepare()
        write_json(Path(instruction["output_path"]), _planning_decision())
        manager.commit_manager()

        next_instruction = manager.record_human_feedback("先把汇报范围收窄到核心用户")

        self.assertEqual(next_instruction["actor"], "manager")
        self.assertEqual(next_instruction["step"], "planning")
        state = manager.status()["state"]
        self.assertEqual(state["last_event"], "human_feedback")
        self.assertEqual(
            state["human_feedback"][-1]["text"],
            "先把汇报范围收窄到核心用户",
        )

    def test_completion_requires_final_human_gate(self) -> None:
        manager = self._manager()
        # Step 1: brief confirmation
        brief_gate = manager.initialize_run(self.brief)
        self.assertEqual(brief_gate["gate"], "brief")
        # Step 2: confirm brief → planning
        manager.approve()
        # Step 3: prepare planning instruction
        instruction = manager.prepare()
        write_json(Path(instruction["output_path"]), _planning_decision())
        manager.commit_manager()
        dispatched = manager.approve()
        task_dir = Path(dispatched["task"]["task_dir"])
        artifact_path = task_dir / "artifact.json"
        write_json(artifact_path, {
            "schema": "argument_synthesis.v1",
            "agent_id": "argument_synthesis",
            "core_thesis": "应优先提升高价值场景时长",
        })
        run_state = read_json(task_dir / "run_state.json")
        run_state["current_step"] = "done"
        write_json(task_dir / "run_state.json", run_state)
        acceptance_instruction = manager.record_worker_completed({
            "step": "done",
            "artifact_path": str(artifact_path),
            "review_summary": "P0=0",
            "memory_notes": "",
        })
        write_json(
            Path(acceptance_instruction["output_path"]),
            _completion_decision("argument-001"),
        )

        gate = manager.commit_manager()
        self.assertEqual(gate["gate"], "final")
        self.assertEqual(manager.status()["state"]["status"], "awaiting_final_approval")

        completed = manager.approve()
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(manager.status()["state"]["status"], "completed")

    def _make_task_dir(self, step: str) -> Path:
        """Minimal task_dir whose StepRunner status() reports ``step``."""
        task_dir = self.run_dir / "tasks" / "t1_argument_synthesis"
        (task_dir / "handoff").mkdir(parents=True, exist_ok=True)
        write_json(task_dir / "input.json", {"manager_task": {}})
        write_json(task_dir / "run_state.json", {"agent_id": "argument_synthesis"})
        return task_dir

    def test_annotate_spawn_inline_is_noop(self) -> None:
        manager = self._manager()
        self.assertEqual(manager.workers.spawn_adapter.kind, "inline")
        task_dir = self._make_task_dir("awaiting_review_output")
        instruction = {
            "actor": "worker",
            "step": "awaiting_review_output",
            "instruction_path": str(task_dir / "handoff" / "instruction_review.md"),
            "output_path": str(task_dir / "handoff" / "output_review.json"),
        }
        manager._annotate_spawn(task_dir, instruction)
        self.assertNotIn("spawn", instruction)
        self.assertFalse((task_dir / "spawn_request.json").exists())

    def test_annotate_spawn_review_step_emits_readonly_reviewer(self) -> None:
        from presentation_agent.spawn import WorkBuddySpawnAdapter

        manager = self._manager()
        manager.workers.spawn_adapter = WorkBuddySpawnAdapter()
        task_dir = self._make_task_dir("awaiting_review_output")
        instruction = {
            "actor": "worker",
            "step": "awaiting_review_output",
            "instruction_path": str(task_dir / "handoff" / "instruction_review.md"),
            "output_path": str(task_dir / "handoff" / "output_review.json"),
        }
        manager._annotate_spawn(task_dir, instruction)

        self.assertIn("spawn", instruction)
        spawn = instruction["spawn"]
        self.assertEqual(spawn["adapter"], "workbuddy")
        self.assertEqual(spawn["role"], "reviewer")
        # read-only maker-checker isolation must be physically expressed.
        self.assertEqual(spawn["detail"]["subagent_type"], "Explore")
        req = read_json(task_dir / "spawn_request.json")
        self.assertEqual(req["role"], "reviewer")
        self.assertEqual(req["subagent_type"], "Explore")

    def test_annotate_spawn_revise_step_emits_writable_worker(self) -> None:
        from presentation_agent.spawn import WorkBuddySpawnAdapter

        manager = self._manager()
        manager.workers.spawn_adapter = WorkBuddySpawnAdapter()
        task_dir = self._make_task_dir("awaiting_revise_output")
        instruction = {
            "actor": "worker",
            "step": "awaiting_revise_output",
            "instruction_path": str(task_dir / "handoff" / "instruction_revise.md"),
            "output_path": str(task_dir / "handoff" / "output_revise.json"),
        }
        manager._annotate_spawn(task_dir, instruction)

        spawn = instruction["spawn"]
        self.assertEqual(spawn["role"], "worker")
        self.assertEqual(spawn["detail"]["subagent_type"], "general-purpose")


class MemoryRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmpdir.name) / "data"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_routes_process_feedback_to_manager_memory(self) -> None:
        router = MemoryRouter(ROOT, data_root=self.data_root)
        result = router.record_text_feedback_multi(
            text="以后每个阶段先给我摘要，确认后再展开细节",
            trigger_scene="unit",
        )

        self.assertEqual(result["route"]["target_agent_id"], "manager")
        memory = read_json(self.data_root / "agents" / "manager" / "memory.json")
        self.assertEqual(len(memory["items"]), 1)
        self.assertEqual(memory["items"][0]["dimension"], "调度")

    def test_feedback_can_route_to_manager_and_specialist(self) -> None:
        router = MemoryRouter(ROOT, data_root=self.data_root)
        result = router.record_text_feedback_multi(
            text="这个结论太软，Manager 验收时不应该直接通过",
            trigger_scene="unit",
        )

        targets = {route["target_agent_id"] for route in result["routes"]}
        self.assertEqual(targets, {"manager", "argument_synthesis"})
        self.assertTrue(
            (self.data_root / "agents" / "manager" / "memory.json").exists()
        )
        self.assertTrue(
            (self.data_root / "agents" / "argument_synthesis" / "memory.json").exists()
        )

    def test_routes_storyline_feedback_to_storyline_agent(self) -> None:
        route = MemoryRouter(ROOT, data_root=self.data_root).route(
            text="这个标题不够结论化，故事线主线也有点散",
            current_agent_id="format",
        )

        self.assertEqual(route.target_agent_id, "storyline_design")


if __name__ == "__main__":
    unittest.main()
