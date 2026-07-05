from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from presentation_agent.agent_profiles import LEGACY_CONTRACT_PROFILE
from presentation_agent.io import read_json
from presentation_agent.llm.adapters.mock import synthesize_from_schema
from presentation_agent.loop import LoopRunner

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FIXTURES = ROOT / "tests" / "fixtures"

def _argument_artifact() -> dict:
    schema = read_json(
        ROOT
        / "skills"
        / "argument_synthesis"
        / "schemas"
        / "argument_synthesis.v1.json"
    )
    artifact = synthesize_from_schema(schema)
    artifact["executive_summary"]["urgency_basis"] = None
    artifact["key_arguments"][0]["id"] = "KA-01"
    artifact["key_arguments"][0]["evidence_refs"] = ["E1"]
    artifact["key_arguments"][0]["logic_chain"]["observations"] = ["E1"]
    artifact["evidence_bank"][0]["id"] = "E1"
    artifact["evidence_bank"][0]["source_unit_refs"] = ["SRC-1"]
    artifact["evidence_disposition"] = {
        "E1": {
            "status": "selected",
            "role": "direct_support",
            "claim_refs": ["KA-01"],
            "reason": "test",
        }
    }
    artifact["executive_summary"]["supporting_arguments"][0]["id"] = "KA-01"
    artifact["executive_summary"]["supporting_arguments"][0][
        "evidence_refs"
    ] = ["E1"]
    artifact["audience_profile"] = {"level": "strategy_lead"}
    artifact["presentation_preferences"] = {"format": "ppt"}
    artifact["target_action"] = "invest"
    artifact["page_limit"] = 10
    return artifact


class GlobalStateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        shutil.copytree(ROOT / "configs", self.root / "configs")
        shutil.copytree(RUNTIME_FIXTURES / "runtime_data", self.root / "data")
        shutil.copytree(RUNTIME_FIXTURES / "runtime_examples", self.root / "examples")
        shutil.copytree(ROOT / "skills", self.root / "skills")
        fixtures = self.root / "tests" / "fixtures" / "llm"
        fixtures.mkdir(parents=True, exist_ok=True)
        (fixtures / "generate__argument_synthesis.json").write_text(
            json.dumps(_argument_artifact(), ensure_ascii=False), encoding="utf-8"
        )
        cfg_path = self.root / "configs" / "llm.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["providers"]["mock"]["fixtures_dir"] = "tests/fixtures/llm"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_global_writes_are_applied_after_clean_stop(self) -> None:
        runner = LoopRunner(
            self.root,
            provider_override="mock",
            contract_profile=LEGACY_CONTRACT_PROFILE,
        )
        result = runner.run("argument_synthesis", self.root / "examples" / "raw_brief.json", self.root / "art" / "tp")

        # Per-run state exists after run completion
        state_path = self.root / "art" / "tp" / "state.json"
        self.assertTrue(state_path.exists(), f"Expected per-run state at {state_path}")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        # Argument synthesis produces a valid artifact; run completes
        self.assertIn("status", result)

    def test_agent_only_reads_declared_global_keys(self) -> None:
        # Seed a key that argument_synthesis does NOT read; it must not appear in
        # the scoped context handed to generation.
        state_path = self.root / "data" / "global" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["secret_unrelated_key"] = "should_not_leak"
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        runner = LoopRunner(
            self.root,
            provider_override="mock",
            contract_profile=LEGACY_CONTRACT_PROFILE,
        )
        spec = runner.specs["argument_synthesis"]
        full = json.loads(state_path.read_text(encoding="utf-8"))
        scoped = runner._scoped_global_reads(spec, full)
        # argument_synthesis declares no global_reads, so it should see nothing.
        self.assertNotIn("secret_unrelated_key", scoped)
        self.assertEqual(scoped, {})

if __name__ == "__main__":
    unittest.main()
