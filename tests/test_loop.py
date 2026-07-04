from __future__ import annotations

import unittest
import shutil
import tempfile
from pathlib import Path

from presentation_agent.loop import LoopRunner
from presentation_agent.memory import MemoryStore


ROOT = Path(__file__).resolve().parents[1]


class LoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        shutil.copytree(ROOT / "configs", self.root / "configs")
        shutil.copytree(ROOT / "data", self.root / "data")
        shutil.copytree(ROOT / "examples", self.root / "examples")
        shutil.copytree(ROOT / "skills", self.root / "skills")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_storyline_loop_reaches_human_review(self) -> None:
        runner = LoopRunner(self.root, provider_override="mock")
        result = runner.run(
            "storyline_design",
            self.root / "examples" / "storyline_input.json",
            self.root / "artifacts" / "run",
        )

        self.assertEqual(result["status"], "pending_human_review")
        self.assertTrue(Path(result["artifact_path"]).exists())
        self.assertTrue(Path(result["run_state_path"]).exists())
        self.assertTrue(Path(result["human_review_path"]).exists())

        run_state = __import__("json").loads(Path(result["run_state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(run_state["current_step"], "human_review")
        self.assertEqual(run_state["next_action"], "await_human_decision")

    def test_feedback_updates_memory(self) -> None:
        store = MemoryStore(self.root, "new_agent")
        log_id = store.record_feedback(
            scope="agent",
            dimension="Wording",
            trigger_scene="unit_test",
            problem="标题用了唯一",
            reason="绝对化表述容易被反例击穿",
            change="改成少数之一",
        )

        self.assertEqual(log_id, "L-001")
        items = store.load_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].case_anchors, ["L-001"])

    def test_agent_specs_include_design_contracts(self) -> None:
        runner = LoopRunner(self.root)
        agents = runner.list_agents()

        self.assertEqual([agent.id for agent in agents], [
            "evidence_harvester",
            "argument_synthesis",
            "storyline_design",
            "page_filling",
            "format",
            "qa_preparation",
            "speaker_script",
        ])
        self.assertEqual(agents[0].previous_agent_id, "manager")
        self.assertEqual(agents[0].next_agent_id, "argument_synthesis")
        self.assertEqual(agents[-1].previous_agent_id, "qa_preparation")
        self.assertIsNone(agents[-1].next_agent_id)
        for agent in agents:
            self.assertTrue(agent.description)
            self.assertTrue(agent.input_contract.get("required_inputs"))
            self.assertTrue(agent.output_contract.get("required_handoff_fields"))
            self.assertTrue(agent.loop_policy.get("human_review_required"))
            self.assertEqual(agent.loop_policy.get("p0_revision_policy"), "auto_revise_until_clear_or_max_rounds")
            self.assertTrue(agent.state_contract.get("agent_memory_scope"))
            self.assertTrue(agent.harness.get("skill_package"))


if __name__ == "__main__":
    unittest.main()
