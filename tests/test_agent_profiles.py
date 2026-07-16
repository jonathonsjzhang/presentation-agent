from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from presentation_agent.agent_profiles import load_agent_profile
from presentation_agent.cli import _current_instruction, build_parser
from presentation_agent.launch import normalize_brief
from presentation_agent.manager import ManagerOrchestrator, _should_pause


ROOT = Path(__file__).resolve().parents[1]


class AgentProfileLoaderTests(unittest.TestCase):
    def test_default_profile_is_the_single_v04_protocol(self) -> None:
        profile = load_agent_profile(ROOT)
        self.assertEqual(profile.contract_profile, "v0_4")
        self.assertEqual(
            list(profile.specs),
            ["analysis", "storyline", "report", "qa_preparation", "format"],
        )
        for agent_id in ("analysis", "storyline", "report", "qa_preparation"):
            self.assertEqual(
                profile.specs[agent_id].output_contract["artifact_format"],
                "markdown",
            )

    def test_report_builder_requires_question_tool_call(self) -> None:
        instructions = (ROOT / "skills/report_builder/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("下一步唯一合法动作是实际调用 `AskUserQuestion` 工具", instructions)
        self.assertIn("ask_user_question_payload", instructions)
        self.assertIn("禁止只把问题写成普通文本", instructions)

    def test_public_start_has_no_protocol_switch(self) -> None:
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
        self.assertFalse(hasattr(args, "contract_profile"))
        self.assertEqual(args.spawn_adapter, "codex")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(
                [
                    "report",
                    "start",
                    "--brief-file",
                    "brief.json",
                    "--spawn-adapter",
                    "codex",
                    "--contract-profile",
                    "v0_4",
                ]
            )

    def test_user_facing_start_requires_worker_spawn_adapter(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(
                ["report", "start", "--brief-file", "brief.json"]
            )

    def test_worker_spawn_is_exposed_as_current_instruction(self) -> None:
        instruction = {
            "actor": "worker",
            "step": "gen",
            "spawn": {"status": "dispatched", "adapter": "workbuddy"},
        }
        for result in (instruction, {"instruction": instruction}):
            self.assertEqual(_current_instruction(result), instruction)

    def test_default_run_mode_pauses_at_human_judgment_stages(self) -> None:
        self.assertTrue(_should_pause(None, "analysis"))
        self.assertTrue(_should_pause(None, "storyline"))
        self.assertFalse(_should_pause(None, "report"))
        self.assertFalse(_should_pause(None, "qa_preparation"))
        self.assertFalse(_should_pause(None, "format"))

    def test_manager_starts_the_v04_five_stage_chain(self) -> None:
        brief = normalize_brief(
            {
                "topic": "测试主题",
                "audience": "strategy_lead",
                "decision_goal": "决定下一步",
            },
            ROOT,
            "v0_4",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            brief_path = run_dir / "raw_brief.json"
            brief_path.write_text(
                json.dumps(brief, ensure_ascii=False), encoding="utf-8"
            )
            manager = ManagerOrchestrator(ROOT, run_dir, contract_profile="v0_4")
            prepared = manager.initialize_run(brief_path)
            self.assertIn(
                "analysis（分析） → storyline（故事线） → report（报告产出） → qa_preparation（追问清单） → format（可视化排版）",
                prepared["present_to_user"],
            )
            self.assertEqual(
                manager.status()["state"]["contract_profile"], "v0_4"
            )
            self.assertEqual(prepared["brief_stage"], "collection_and_confirmation")
            self.assertTrue(prepared["interaction_required"])
            self.assertEqual(prepared["preferred_tool"], "AskUserQuestion")


if __name__ == "__main__":
    unittest.main()
