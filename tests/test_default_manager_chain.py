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
STAGES = ("analysis", "storyline", "report", "format")
ARTIFACTS = {
    "analysis": "analysis.v1.valid.json",
    "storyline": "storyline.v3.valid.json",
    "report": "report.v1.valid.json",
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

    def test_manager_reaches_format_and_document_delivery_gate(self) -> None:
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
                write_json(
                    Path(instruction["output_path"]),
                    read_json(FIXTURES / ARTIFACTS[agent_id]),
                )
                runner = StepRunner(
                    ROOT,
                    task_dir,
                    data_root=temp / "data",
                    contract_profile="v0_3",
                )
                if agent_id == "report":
                    result = RenderResult(
                        status="rendered",
                        fmt="document",
                        fidelity="content",
                        output_path=str(task_dir / "report.docx"),
                        file_bytes=1,
                    )
                    with patch(
                        "presentation_agent.renderers.report_docx.render_report_docx",
                        return_value=result,
                    ):
                        worker_result = runner.commit()
                elif agent_id == "format":
                    result = RenderResult(
                        status="rendered",
                        fmt="document",
                        fidelity="formatted",
                        output_path=str(task_dir / "report_formatted.docx"),
                        file_bytes=1,
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
                decision = {
                    "schema": "manager_decision.v1",
                    "phase": "acceptance",
                    "action": "complete" if agent_id == "format" else "dispatch",
                    "reason_summary": f"accept {agent_id}",
                    "acceptance_report": {
                        "task_id": f"t{index + 1}",
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
                write_json(Path(acceptance["output_path"]), decision)
                dispatched = manager.commit_manager()

            state = manager.status()["state"]
            self.assertEqual(state["human_gate"], "delivery_options")
            self.assertEqual(
                [item["agent_id"] for item in state["accepted_artifacts"]],
                list(STAGES),
            )
            self.assertEqual(
                manager.approve(delivery_option="skip")["status"],
                "completed",
            )


if __name__ == "__main__":
    unittest.main()
