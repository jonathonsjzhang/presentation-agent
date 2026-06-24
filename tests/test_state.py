from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from presentation_agent.loop import LoopRunner

ROOT = Path(__file__).resolve().parents[1]

# A complete task_positioning artifact that also carries the global_writes keys.
_TP_ARTIFACT = {
    "schema": "task_positioning.v1",
    "agent_id": "task_positioning",
    "topic": "t",
    "report_brief": "b",
    "audience": "strategy_lead",
    "report_type": "deep_dive",
    "output_format": "ppt",
    "input_inventory": {},
    "template_requirements": {},
    "historical_reference_materials": [],
    "reference_patterns": [],
    "decision_goal": "g",
    "scope": ["a", "b"],
    "out_of_scope": ["x"],
    "constraints": [],
    "success_criteria": [],
    "open_questions": [],
    "downstream_guidance": {},
    "audience_profile": {"level": "strategy_lead"},
    "presentation_preferences": {"format": "ppt"},
    "target_action": "invest",
    "page_limit": 10,
}


class GlobalStateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        for name in ("configs", "data", "examples", "skills"):
            shutil.copytree(ROOT / name, self.root / name)
        fixtures = self.root / "tests" / "fixtures" / "llm"
        fixtures.mkdir(parents=True, exist_ok=True)
        (fixtures / "generate__task_positioning.json").write_text(
            json.dumps(_TP_ARTIFACT, ensure_ascii=False), encoding="utf-8"
        )
        cfg_path = self.root / "configs" / "llm.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["providers"]["mock"]["fixtures_dir"] = "tests/fixtures/llm"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_global_writes_are_applied_after_clean_stop(self) -> None:
        runner = LoopRunner(self.root, provider_override="mock")
        runner.run("task_positioning", self.root / "examples" / "raw_brief.json", self.root / "art" / "tp")

        # State is now per-run, not global singleton — scoped to the output dir.
        state_path = self.root / "art" / "tp" / "state.json"
        self.assertTrue(state_path.exists(), f"Expected per-run state at {state_path}")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["audience_profile"], {"level": "strategy_lead"})
        self.assertEqual(state["target_action"], "invest")
        self.assertEqual(state["page_limit"], 10)

    def test_agent_only_reads_declared_global_keys(self) -> None:
        # Seed a key that task_positioning does NOT read; it must not appear in
        # the scoped context handed to generation.
        state_path = self.root / "data" / "global" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["secret_unrelated_key"] = "should_not_leak"
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        runner = LoopRunner(self.root, provider_override="mock")
        spec = runner.specs["task_positioning"]
        full = json.loads(state_path.read_text(encoding="utf-8"))
        scoped = runner._scoped_global_reads(spec, full)
        # task_positioning declares no global_reads, so it should see nothing.
        self.assertNotIn("secret_unrelated_key", scoped)
        self.assertEqual(scoped, {})


if __name__ == "__main__":
    unittest.main()
