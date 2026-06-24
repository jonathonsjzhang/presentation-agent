from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from presentation_agent.loop import LoopRunner

ROOT = Path(__file__).resolve().parents[1]


class MultiCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        for name in ("configs", "data", "examples", "skills"):
            shutil.copytree(ROOT / name, self.root / name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _enable_multi(self, max_candidates: int = 3) -> None:
        cfg_path = self.root / "configs" / "agents.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        for agent in cfg["agents"]:
            if agent["id"] == "storyline_design":
                agent["optional_features"]["multi_candidate"] = {
                    "enabled_by_default": True,
                    "max_candidates": max_candidates,
                    "selection_owner": "review_sub_agent_then_human",
                }
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_disabled_by_default_no_candidates_dir(self) -> None:
        runner = LoopRunner(self.root, provider_override="mock")
        runner.run("storyline_design", self.root / "examples" / "storyline_input.json", self.root / "art")
        self.assertFalse((self.root / "art" / "candidates").exists())
        run_state = json.loads((self.root / "art" / "run_state.json").read_text(encoding="utf-8"))
        self.assertNotIn("multi_candidate", run_state)

    def test_enabled_generates_and_selects(self) -> None:
        self._enable_multi(max_candidates=3)
        runner = LoopRunner(self.root, provider_override="mock")
        result = runner.run(
            "storyline_design", self.root / "examples" / "storyline_input.json", self.root / "art"
        )
        self.assertEqual(result["status"], "pending_human_review")

        candidates_dir = self.root / "art" / "candidates"
        self.assertTrue(candidates_dir.exists())
        self.assertEqual(len(list(candidates_dir.glob("candidate_*.json"))), 3 * 2)  # artifact + review each

        run_state = json.loads((self.root / "art" / "run_state.json").read_text(encoding="utf-8"))
        mc = run_state["multi_candidate"]
        self.assertTrue(mc["enabled"])
        self.assertEqual(mc["count"], 3)
        self.assertEqual(len(mc["candidates"]), 3)
        self.assertIn(mc["selected_index"], [c["index"] for c in mc["candidates"]])

    def test_selection_prefers_fewest_objections(self) -> None:
        # The selected candidate must have the minimal (p0, p1) among all.
        self._enable_multi(max_candidates=3)
        runner = LoopRunner(self.root, provider_override="mock")
        runner.run("storyline_design", self.root / "examples" / "storyline_input.json", self.root / "art")
        run_state = json.loads((self.root / "art" / "run_state.json").read_text(encoding="utf-8"))
        mc = run_state["multi_candidate"]
        selected = next(c for c in mc["candidates"] if c["index"] == mc["selected_index"])
        best = min((c["p0"], c["p1"]) for c in mc["candidates"])
        self.assertEqual((selected["p0"], selected["p1"]), best)


if __name__ == "__main__":
    unittest.main()
