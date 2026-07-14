from __future__ import annotations

import json
import unittest
from pathlib import Path

from presentation_agent.agent_profiles import load_agent_profile
from presentation_agent.capabilities.profile import normalize_report_profile
from presentation_agent.cli import _current_instruction, _report_response
from presentation_agent.manager import ManagerOrchestrator
from presentation_agent.skills.base import SkillContext
from presentation_agent.skills.generic import GenericSkill


ROOT = Path(__file__).resolve().parents[1]


class _SummaryManager:
    def status_summary(self) -> dict[str, object]:
        return {"status": "running", "state_path": "/tmp/manager_state.json"}


class RuntimePayloadBudgetTests(unittest.TestCase):
    def test_cli_uses_one_current_instruction_without_full_result(self) -> None:
        result = {
            "actor": "human",
            "gate": "brief",
            "brief": {"evidence_catalog": {"items": ["large"] * 100}},
            "present_to_user": "请确认",
            "ask_user_question_payload": {"questions": []},
            "next_action": "human_feedback",
        }
        response = _report_response(
            run_dir=Path("/tmp/run"),
            result=result,
            manager=_SummaryManager(),  # type: ignore[arg-type]
        )
        self.assertNotIn("result", response)
        self.assertNotIn("instruction", response)
        instruction = response["current_instruction"]
        self.assertIsInstance(instruction, dict)
        self.assertNotIn("brief", instruction)
        self.assertEqual(instruction["present_to_user"], "请确认")

    def test_nested_worker_instruction_inherits_outer_next_action(self) -> None:
        instruction = {"actor": "worker", "spawn": {"status": "dispatched"}}
        normalized = _current_instruction(
            {"instruction": instruction, "next_action": "host_spawn_then_submit"}
        )
        self.assertEqual(normalized["next_action"], "host_spawn_then_submit")

    def test_external_worker_input_is_referenced_not_duplicated(self) -> None:
        catalog = {
            "schema": "evidence_catalog.v1",
            "items": [{"evidence_id": f"EV-{i}", "content": "证据" * 200} for i in range(89)],
        }
        input_data = {
            "schema": "worker_context.v1",
            "report_charter": {"topic": "测试"},
            "manager_task": {"task_id": "analysis-1"},
            "raw_brief": {"research_purpose": "解释增长"},
            "input_readiness": {"status": "ready"},
            "evidence_catalog": catalog,
            "inputs": {"evidence": {"inline_fields": catalog}},
        }
        package = {
            "instructions": "按证据形成观点。",
            "schemas": {"analysis.v1": {"type": "object"}},
        }
        spec = load_agent_profile(ROOT, "v0_3").specs["analysis"]
        request = GenericSkill("analysis")._build_request(
            spec,
            input_data,
            SkillContext(
                skill_package=package,
                external_input_path="/tmp/task/input.json",
            ),
            round_index=0,
            objections=None,
        )
        self.assertIn("/tmp/task/input.json", request.user)
        self.assertNotIn("EV-88", request.user)
        self.assertLess(len(request.user), 5000)

    def test_manager_brief_projection_keeps_catalog_summary_only(self) -> None:
        manager = object.__new__(ManagerOrchestrator)
        brief = {
            "topic": "测试",
            "evidence_catalog_ref": "/tmp/evidence_catalog.json",
            "evidence_catalog": {
                "schema": "evidence_catalog.v1",
                "items": [{"evidence_id": f"EV-{i}", "content": "大段原文"} for i in range(89)],
                "source_manifest": [{"material_id": "M1", "source_name": "问卷"}],
                "unresolved": [],
            },
        }
        projected = manager._manager_brief_projection(brief)
        self.assertNotIn("evidence_catalog", projected)
        self.assertEqual(projected["evidence_catalog_summary"]["item_count"], 89)
        self.assertLess(len(json.dumps(projected, ensure_ascii=False)), 5000)

    def test_v03_requested_delivery_target_drives_upstream_capability(self) -> None:
        profile = normalize_report_profile(
            {
                "report_charter": {
                    "audience": "exec_office",
                    "report_type": "deep_dive",
                    "requested_delivery_targets": ["document"],
                }
            },
            root=ROOT,
        )
        self.assertEqual(profile.output_format, "document")


if __name__ == "__main__":
    unittest.main()
