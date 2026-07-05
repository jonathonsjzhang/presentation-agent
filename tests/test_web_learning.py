from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from presentation_agent.io import read_json, write_json
from presentation_agent.web import WebApp

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DATA = ROOT / "tests" / "fixtures" / "runtime_data"


class WebLearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        shutil.copytree(ROOT / "configs", self.root / "configs")
        shutil.copytree(RUNTIME_DATA, self.root / "data")
        shutil.copytree(ROOT / "skills", self.root / "skills")
        story_memory_dir = self.root / "data" / "agents" / "storyline_design"
        write_json(story_memory_dir / "memory.json", {"items": []})
        log_path = story_memory_dir / "learning_log.jsonl"
        if log_path.exists():
            log_path.unlink()
        self.run_dir = self.root / "artifacts" / "sample_run"
        self.run_dir.mkdir(parents=True)
        write_json(
            self.run_dir / "run_state.json",
            {
                "run_id": "sample-run",
                "agent_id": "storyline_design",
                "status": "pending_human_review",
                "current_step": "human_review",
                "next_action": "await_human_decision",
                "feedback_logged": [],
                "history": [],
            },
        )
        (self.run_dir / "human_review.md").write_text("# Human Review\n", encoding="utf-8")
        self.app = WebApp(self.root)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_human_review_records_decision_and_updates_memory(self) -> None:
        result = self.app.record_human_review(
            {
                "run_state_path": "artifacts/sample_run/run_state.json",
                "agent_id": "storyline_design",
                "decision": "approve",
                "notes": "标题需要更像结论",
                "feedback": {
                    "dimension": "Leadline",
                    "problem": "标题还是主题词",
                    "reason": "无法通过标题连读测试",
                    "change": "标题写成完整判断句，并带出 so what",
                },
            }
        )

        self.assertTrue(result["ok"])
        run_state = read_json(self.run_dir / "run_state.json")
        self.assertEqual(run_state["status"], "approved_by_human")
        self.assertEqual(run_state["next_action"], "advance_to_next_agent")
        self.assertEqual(run_state["current_step"], "learning_capture")
        self.assertEqual(run_state["human_decision"]["decision"], "approve")
        self.assertEqual(run_state["feedback_logged"], ["L-001"])

        memory = read_json(self.root / "data" / "agents" / "storyline_design" / "memory.json")
        self.assertTrue(
            any(item["suggestion"] == "标题写成完整判断句，并带出 so what" for item in memory["items"])
        )
        learning_log = (self.root / "data" / "agents" / "storyline_design" / "learning_log.jsonl").read_text(
            encoding="utf-8"
        )
        self.assertIn('"source": "human-review"', learning_log)
        self.assertIn("Recorded human review event", (self.run_dir / "human_review.md").read_text(encoding="utf-8"))

    def test_learning_overview_summarizes_memory_and_state(self) -> None:
        self.app.record_success_memory(
            {
                "agent_id": "storyline_design",
                "dimension": "Leadline",
                "pattern": "标题写成完整判断句",
            }
        )
        overview = self.app.learning_overview()
        self.assertIn("global_state", overview)
        self.assertEqual(len(overview["agents"]), 7)
        self.assertIn("memory_items", overview["totals"])
        self.assertIn("learning_events", overview["totals"])
        self.assertGreaterEqual(overview["event_counts"].get("feedback", 0), 1)

    def test_overview_exposes_six_core_and_eleven_atomic_capability_packages(self) -> None:
        overview = self.app.overview()
        packages = overview["capabilities"]["packages"]

        self.assertEqual(len(packages), 17)
        self.assertEqual(
            len([item for item in packages if item["kind"] == "core"]),
            6,
        )
        self.assertTrue(all(agent["implemented"] for agent in overview["agents"]))


if __name__ == "__main__":
    unittest.main()
