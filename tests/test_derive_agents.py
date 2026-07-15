from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from presentation_agent.derive_agents import (
    AUTOGEN_BANNER,
    derive_all,
    write_derived,
)
from presentation_agent.io import write_json


def _config_with_two_stages() -> dict:
    return {
        "version": "agent-definition.v2",
        "active_contract_profile": "v0_3",
        "contract_profiles": {
            "v0_3": {
                "canonical_stages": ["analysis", "format"],
                "workers": [
                    {
                        "id": "analysis",
                        "name": "分析",
                        "skill": "analysis",
                        "output_schema": "analysis.v1",
                    },
                    {
                        "id": "format",
                        "name": "可视化",
                        "skill": "format",
                        "output_schema": "formatted_material.v2",
                    },
                    {"id": "unused", "name": "unused", "skill": "unused"},
                ],
            }
        },
    }


def _root() -> Path:
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    (root / "configs").mkdir(parents=True, exist_ok=True)
    write_json(root / "configs" / "agents.json", _config_with_two_stages())
    return root


class DeriveAgentsTests(unittest.TestCase):
    def test_count_is_stages_times_hosts(self) -> None:
        derived = derive_all(_root())
        # 2 stages * 1 Worker role * 3 hosts = 6
        self.assertEqual(len(derived), 6)

    def test_agent_not_in_stages_is_excluded(self) -> None:
        derived = derive_all(_root())
        ids = {d.agent_id for d in derived}
        self.assertNotIn("unused", ids)
        self.assertEqual(ids, {"analysis", "format"})

    def test_only_writable_claude_workers_are_derived(self) -> None:
        derived = derive_all(_root())
        claude = [d for d in derived if d.host == "claude" and d.agent_id == "format"]
        self.assertEqual([d.role for d in claude], ["worker"])
        self.assertIn("Write", claude[0].content)

    def test_codex_worker_uses_workspace_write(self) -> None:
        derived = derive_all(_root())
        worker = next(
            d for d in derived
            if d.host == "codex" and d.role == "worker" and d.agent_id == "format"
        )
        self.assertIn("sandbox: workspace-write", worker.content)
        self.assertIn("read_only: false", worker.content)

    def test_workbuddy_subagent_types(self) -> None:
        derived = derive_all(_root())
        wb = {
            d.role: json.loads(d.content)
            for d in derived
            if d.host == "workbuddy" and d.agent_id == "analysis"
        }
        self.assertEqual(wb["worker"]["subagent_type"], "general-purpose")
        self.assertEqual(set(wb), {"worker"})
        self.assertEqual(wb["worker"]["invariants"]["max_depth"], 1)

    def test_all_files_carry_autogen_banner(self) -> None:
        derived = derive_all(_root())
        for d in derived:
            self.assertIn("AUTO-GENERATED", d.content)

    def test_write_creates_files_under_dedicated_paths(self) -> None:
        root = _root()
        derived = derive_all(root)
        written = write_derived(root, derived)
        self.assertEqual(len(written), 6)
        for p in written:
            self.assertTrue(p.exists())
        # Stage sub-agents must live under dedicated subdirs, never colliding
        # with a hand-written orchestrator at .claude/agents/report-builder.md.
        rels = {str(p.relative_to(root)) for p in written}
        self.assertTrue(any("claude/agents/pipeline/" in r for r in rels))
        self.assertTrue(any("codex/agents/" in r for r in rels))
        self.assertTrue(any("agents.workbuddy/" in r for r in rels))
        self.assertFalse(any(r.endswith("agents/report-builder.md") for r in rels))

    def test_write_removes_only_stale_auto_generated_agents(self) -> None:
        root = _root()
        stale = root / ".codex/agents/legacy_worker.md"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text(
            f"<!-- {AUTOGEN_BANNER} -->\nlegacy",
            encoding="utf-8",
        )
        hand_written = root / ".codex/agents/custom.md"
        hand_written.write_text("hand-written", encoding="utf-8")

        write_derived(root, derive_all(root))

        self.assertFalse(stale.exists())
        self.assertTrue(hand_written.exists())


if __name__ == "__main__":
    unittest.main()
