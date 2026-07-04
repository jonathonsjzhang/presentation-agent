from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from presentation_agent.derive_agents import derive_all, write_derived
from presentation_agent.io import write_json


def _config_with_two_stages() -> dict:
    return {
        "version": "agent-definition.v2",
        "pipeline": {"stages": ["argument_synthesis", "format"]},
        "agents": [
            {
                "id": "argument_synthesis",
                "name": "核心论点提炼",
                "skill": "argument_synthesis",
                "output_schema": "argument_synthesis.v1",
                "rubrics": ["r1", "r2"],
            },
            {
                "id": "format",
                "name": "format",
                "skill": "format",
                "output_schema": "formatted_material.v1",
                "rubrics": ["fr1"],
            },
            # An agent NOT in stages must be ignored.
            {"id": "legacy_agent", "name": "legacy", "skill": "legacy"},
        ],
    }


def _root() -> Path:
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    (root / "configs").mkdir(parents=True, exist_ok=True)
    write_json(root / "configs" / "agents.json", _config_with_two_stages())
    return root


class DeriveAgentsTests(unittest.TestCase):
    def test_count_is_stages_times_roles_times_hosts(self) -> None:
        derived = derive_all(_root())
        # 2 stages * 2 roles (worker/reviewer) * 3 hosts = 12
        self.assertEqual(len(derived), 12)

    def test_legacy_agent_not_in_stages_excluded(self) -> None:
        derived = derive_all(_root())
        ids = {d.agent_id for d in derived}
        self.assertNotIn("legacy_agent", ids)
        self.assertEqual(ids, {"argument_synthesis", "format"})

    def test_claude_worker_is_writable_reviewer_is_read_only(self) -> None:
        derived = derive_all(_root())
        claude = {(d.role): d for d in derived if d.host == "claude" and d.agent_id == "format"}
        self.assertIn("Write", claude["worker"].content)
        # Reviewer must NOT be granted Write/Edit/Bash.
        self.assertNotIn("Write", claude["reviewer"].content.split("---")[1])
        self.assertIn("tools: Read", claude["reviewer"].content)

    def test_codex_reviewer_sandbox_read_only(self) -> None:
        derived = derive_all(_root())
        rev = next(
            d for d in derived
            if d.host == "codex" and d.role == "reviewer" and d.agent_id == "format"
        )
        self.assertIn("sandbox: read-only", rev.content)
        self.assertIn("read_only: true", rev.content)

    def test_workbuddy_subagent_types(self) -> None:
        derived = derive_all(_root())
        wb = {
            d.role: json.loads(d.content)
            for d in derived
            if d.host == "workbuddy" and d.agent_id == "argument_synthesis"
        }
        self.assertEqual(wb["worker"]["subagent_type"], "general-purpose")
        self.assertEqual(wb["reviewer"]["subagent_type"], "Explore")
        self.assertTrue(wb["reviewer"]["read_only"])
        self.assertEqual(wb["worker"]["invariants"]["max_depth"], 1)

    def test_all_files_carry_autogen_banner(self) -> None:
        derived = derive_all(_root())
        for d in derived:
            self.assertIn("AUTO-GENERATED", d.content)

    def test_write_creates_files_under_dedicated_paths(self) -> None:
        root = _root()
        derived = derive_all(root)
        written = write_derived(root, derived)
        self.assertEqual(len(written), 12)
        for p in written:
            self.assertTrue(p.exists())
        # Stage sub-agents must live under dedicated subdirs, never colliding
        # with a hand-written orchestrator at .claude/agents/report-builder.md.
        rels = {str(p.relative_to(root)) for p in written}
        self.assertTrue(any("claude/agents/pipeline/" in r for r in rels))
        self.assertTrue(any("codex/agents/" in r for r in rels))
        self.assertTrue(any("agents.workbuddy/" in r for r in rels))
        self.assertFalse(any(r.endswith("agents/report-builder.md") for r in rels))


if __name__ == "__main__":
    unittest.main()
