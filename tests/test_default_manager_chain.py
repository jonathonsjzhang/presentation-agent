from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from presentation_agent.io import read_json, write_json
from presentation_agent.manager import ManagerOrchestrator
from presentation_agent.renderers.base import RenderResult
from presentation_agent.step import StepRunner


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v0_3"
STAGES = ("analysis", "storyline", "report", "qa_preparation", "format")
ARTIFACTS = {
    "analysis": "analysis.v1.valid.json",
    "storyline": "storyline.v3.valid.json",
    "report": "report.v1.valid.json",
    "qa_preparation": "report_with_questions.v1.valid.json",
    "format": "formatted_material.v2.valid.json",
}


class DefaultManagerChainTests(unittest.TestCase):
    def _packet(
        self,
        index: int,
        input_path: Path,
        charter: dict,
    ) -> dict:
        agent_id = STAGES[index]
        packet = {
            "schema": "task_packet.v2",
            "task_id": f"t{index + 1}",
            "agent_id": agent_id,
            "objective": f"complete {agent_id}",
            "input_artifacts": [str(input_path)],
            "context": {},
            "constraints": [],
            "deliverables": {
                "schema": read_json(FIXTURES / ARTIFACTS[agent_id])["schema"]
            },
            "acceptance_criteria": ["schema valid"],
            "dependencies": [] if index == 0 else [f"t{index}"],
            "memory_dimensions": [],
            "recommendation_granularity": charter["recommendation_granularity"],
            "unsupported_specificity_policy": charter[
                "unsupported_specificity_policy"
            ],
        }
        if agent_id == "format":
            packet["delivery_target"] = "document"
        return packet

    def test_manager_reaches_qa_and_delivery_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            run_dir = temp / "run"
            brief_path = temp / "brief.json"
            charter = read_json(FIXTURES / "report_charter.v2.valid.json")
            write_json(brief_path, charter)

            plan = {
                "plan_id": "default-chain",
                "tasks": [
                    {
                        "task_id": f"t{index + 1}",
                        "agent_id": agent_id,
                        "objective": f"complete {agent_id}",
                        "dependencies": [] if index == 0 else [f"t{index}"],
                        "status": "planned",
                    }
                    for index, agent_id in enumerate(STAGES)
                ],
                "human_gates": ["plan", "delivery_options"],
                "completion_criteria": ["format complete"],
            }

            manager = ManagerOrchestrator(
                ROOT,
                run_dir,
                data_root=temp / "data",
                spawn_adapter="inline",
                contract_profile="v0_3",
            )
            manager.initialize_run(brief_path)
            manager.approve(run_mode="full_auto", review_mode="schema_only")
            planning = manager.prepare()
            write_json(
                Path(planning["output_path"]),
                {
                    "schema": "manager_decision.v1",
                    "phase": "planning",
                    "action": "dispatch",
                    "reason_summary": "canonical plan",
                    "report_charter": charter,
                    "execution_plan": plan,
                    "task_packet": self._packet(
                        0, manager.raw_brief_path, charter
                    ),
                    "user_message": "plan ready",
                },
            )
            manager.commit_manager()
            dispatched = manager.approve()

            for index, agent_id in enumerate(STAGES):
                task_dir = Path(dispatched["task"]["task_dir"])
                instruction = dispatched["instruction"]
                artifact = read_json(FIXTURES / ARTIFACTS[agent_id])
                if agent_id == "qa_preparation":
                    artifact = read_json(FIXTURES / "report.v1.valid.json")
                    artifact["report_markdown"] = (
                        artifact["report_markdown"].rstrip()
                        + "\n\n## 听众可能追问的问题\n\n"
                        + "1. 如果成果保存组本身就是高意愿用户，当前证据如何区分意愿和机制？\n"
                        + "2. 哪些证据一旦相反，会推翻优先验证成果复用闭环的判断？\n"
                    )
                    artifact["qa_question_list"] = [
                        "如果成果保存组本身就是高意愿用户，当前证据如何区分意愿和机制？",
                        "哪些证据一旦相反，会推翻优先验证成果复用闭环的判断？",
                    ]
                write_json(
                    Path(instruction["output_path"]),
                    artifact,
                )
                runner = StepRunner(
                    ROOT,
                    task_dir,
                    data_root=temp / "data",
                    contract_profile="v0_3",
                )
                if agent_id == "format":
                    rendered_path = task_dir / "report_formatted.docx"
                    rendered_path.write_bytes(b"docx")
                    result = RenderResult(
                        status="rendered",
                        fmt="document",
                        fidelity="formatted",
                        output_path=str(rendered_path),
                        file_bytes=rendered_path.stat().st_size,
                        unit_count=2,
                    )
                    with patch(
                        "presentation_agent.renderers.render_material",
                        return_value=result,
                    ):
                        worker_result = runner.commit()
                else:
                    worker_result = runner.commit()

                self.assertEqual(worker_result["step"], "done")
                self.assertEqual(
                    worker_result["status"], "pending_human_review"
                )
                acceptance = manager.record_worker_completed(worker_result)
                if agent_id == "format":
                    # Legacy stuck runs did not persist these top-level fields;
                    # recovery must fall back to artifact.render_result.
                    legacy_state = manager.status()["state"]
                    legacy_state["worker_result"].pop("render_result", None)
                    legacy_state["worker_result"].pop("rendered_files", None)
                    legacy_state["current_task"].pop("render_result", None)
                    legacy_state["current_task"].pop("rendered_files", None)
                    manager._save_state(legacy_state)
                decision = {
                    "schema": "manager_decision.v1",
                    "phase": "acceptance",
                    "action": "complete" if agent_id == "format" else "dispatch",
                    "reason_summary": f"accept {agent_id}",
                    "acceptance_report": {
                        "verdict": "accept",
                        "criteria_results": [],
                        "cross_stage_findings": [],
                        "reason": "passed",
                    },
                    "user_message": "accepted",
                }
                if index < len(STAGES) - 1:
                    decision["task_packet"] = self._packet(
                        index + 1,
                        Path(worker_result["artifact_path"]),
                        charter,
                    )
                elif agent_id == "format":
                    # Reproduces a stale bookkeeping value left by an earlier
                    # Storyline feedback/revise cycle. Runtime owns this ID and
                    # must bind acceptance to the current Format task.
                    decision["acceptance_report"]["task_id"] = "stale-storyline-task"
                write_json(Path(acceptance["output_path"]), decision)
                dispatched = manager.commit_manager()

            state = manager.status()["state"]
            self.assertEqual(state["human_gate"], "delivery_options")
            self.assertEqual(dispatched["rendered_files"], [str(rendered_path)])
            self.assertEqual(
                state["last_manager_decision"]["acceptance_report"]["task_id"],
                "t5",
            )
            self.assertEqual(
                state["last_manager_decision"]["runtime_normalizations"][0]["submitted"],
                "stale-storyline-task",
            )
            self.assertEqual(
                [item["agent_id"] for item in state["accepted_artifacts"]],
                list(STAGES),
            )
            completed = manager.approve(delivery_option="skip")
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["rendered_files"], [str(rendered_path)])

    def test_planning_without_materials_asks_human_instead_of_dispatching(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            run_dir = temp / "run"
            brief_path = temp / "brief.json"
            charter = read_json(FIXTURES / "report_charter.v2.valid.json")
            charter["material_inventory"] = []
            charter["blocking_questions"] = ["请提供至少一份可分析的材料。"]
            write_json(brief_path, charter)

            manager = ManagerOrchestrator(
                ROOT,
                run_dir,
                data_root=temp / "data",
                spawn_adapter="inline",
                contract_profile="v0_3",
            )
            manager.initialize_run(brief_path)
            manager.approve(run_mode="full_auto", review_mode="schema_only")
            planning = manager.prepare()
            write_json(
                Path(planning["output_path"]),
                {
                    "schema": "manager_decision.v1",
                    "phase": "planning",
                    "action": "ask_human",
                    "reason_summary": "缺少可分析素材",
                    "report_charter": charter,
                    "questions_for_human": ["请提供至少一份可分析的材料。"],
                    "user_message": "需要素材后才能开始 Analysis。",
                },
            )

            result = manager.commit_manager()

            self.assertEqual(result["actor"], "human")
            self.assertEqual(result["gate"], "decision")
            self.assertEqual(
                manager.status()["state"]["status"],
                "awaiting_human_decision",
            )


if __name__ == "__main__":
    unittest.main()
