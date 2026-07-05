from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from presentation_agent.io import read_json, write_json
from presentation_agent.spawn import (
    CLISpawnAdapter,
    ClaudeCodeSpawnAdapter,
    CodexSpawnAdapter,
    InlineSpawnAdapter,
    SpawnRequest,
    WorkBuddySpawnAdapter,
    build_spawn_adapter,
)
from presentation_agent.step import StepError


def _request(task_dir: Path, role: str = "worker") -> SpawnRequest:
    return SpawnRequest(
        task_dir=task_dir,
        agent_id="analysis",
        role=role,  # type: ignore[arg-type]
        instruction_path=task_dir / "handoff" / "instruction_gen.md",
        output_path=task_dir / "handoff" / "output_gen.json",
        input_path=task_dir / "input.json",
        mode="foreground",
    )


class InlineSpawnAdapterTests(unittest.TestCase):
    def test_inline_spawns_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            adapter = InlineSpawnAdapter()
            self.assertEqual(adapter.kind, "inline")
            result = adapter.spawn(_request(task_dir))
            self.assertEqual(result.status, "dispatched")
            self.assertIsNone(result.artifact_path)
            self.assertEqual(result.detail, {})
            # Inline must never write a spawn_request.json (zero side effects).
            self.assertFalse((task_dir / "spawn_request.json").exists())


class WorkBuddySpawnAdapterTests(unittest.TestCase):
    def test_worker_emits_spawn_request_with_general_purpose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            adapter = WorkBuddySpawnAdapter()
            self.assertEqual(adapter.kind, "workbuddy")
            result = adapter.spawn(_request(task_dir, role="worker"))

            spawn_file = task_dir / "spawn_request.json"
            self.assertTrue(spawn_file.exists())
            self.assertEqual(result.status, "dispatched")
            self.assertEqual(result.detail["executor"], "host_agent_tool")

            spec = read_json(spawn_file)
            self.assertEqual(spec["host"], "workbuddy")
            self.assertEqual(spec["subagent_type"], "general-purpose")
            self.assertEqual(spec["agent_id"], "analysis")
            self.assertEqual(spec["role"], "worker")
            self.assertEqual(spec["invariants"]["max_depth"], 1)
            self.assertEqual(spec["invariants"]["write_scope"], str(task_dir))

    def test_reviewer_uses_readonly_explore_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            result = WorkBuddySpawnAdapter().spawn(_request(task_dir, role="reviewer"))
            spec = read_json(task_dir / "spawn_request.json")
            # Reviewer must be a read-only agent type (maker-checker isolation).
            self.assertEqual(spec["subagent_type"], "Explore")
            self.assertEqual(spec["role"], "reviewer")
            self.assertEqual(result.detail["subagent_type"], "Explore")
            self.assertEqual(result.detail["result_delivery"], "host_relay")


class NativeTerminalSpawnAdapterTests(unittest.TestCase):
    def test_claude_reviewer_uses_task_with_write_tools_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            result = ClaudeCodeSpawnAdapter().spawn(
                _request(task_dir, role="reviewer")
            )

            spec = read_json(task_dir / "spawn_request.json")
            self.assertEqual(result.detail["tool"], "Task")
            self.assertEqual(spec["host"], "claude_code")
            self.assertEqual(spec["subagent_type"], "Explore")
            self.assertIn("Write", spec["disallowed_tools"])
            self.assertTrue(spec["invariants"]["read_only"])
            self.assertEqual(spec["result_delivery"], "host_relay")

    def test_codex_worker_uses_spawn_agent_with_workspace_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            result = CodexSpawnAdapter().spawn(_request(task_dir, role="worker"))

            spec = read_json(task_dir / "spawn_request.json")
            self.assertEqual(result.detail["tool"], "spawn_agent")
            self.assertEqual(result.detail["wait_tool"], "wait_agent")
            self.assertEqual(spec["native_role"], "worker")
            self.assertEqual(spec["sandbox_mode"], "workspace-write")
            self.assertFalse(spec["invariants"]["read_only"])
            self.assertEqual(spec["result_delivery"], "direct_file")

    def test_codex_reviewer_is_read_only_explorer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            CodexSpawnAdapter().spawn(_request(task_dir, role="reviewer"))

            spec = read_json(task_dir / "spawn_request.json")
            self.assertEqual(spec["native_role"], "explorer")
            self.assertEqual(spec["sandbox_mode"], "read-only")
            self.assertTrue(spec["invariants"]["read_only"])


class CLISpawnAdapterTests(unittest.TestCase):
    def test_emit_only_worker_builds_claude_argv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            (task_dir / "handoff").mkdir(parents=True, exist_ok=True)
            adapter = CLISpawnAdapter(["claude"])  # dialect inferred from binary
            self.assertEqual(adapter.kind, "cli")
            self.assertEqual(adapter.dialect, "claude")
            result = adapter.spawn(_request(task_dir, role="worker"))

            self.assertEqual(result.status, "dispatched")
            self.assertEqual(result.detail["executor"], "cli_command_emitted")
            argv = result.detail["argv"]
            self.assertEqual(argv[0], "claude")
            self.assertIn("-p", argv)
            # Worker is NOT read-only: no disallowedTools flag.
            self.assertNotIn("--disallowedTools", argv)

            spec = read_json(task_dir / "spawn_request.json")
            self.assertEqual(spec["host"], "cli")
            self.assertEqual(spec["dialect"], "claude")
            self.assertEqual(spec["role"], "worker")
            self.assertFalse(spec["invariants"]["read_only"])
            self.assertEqual(spec["invariants"]["max_depth"], 1)
            self.assertEqual(spec["invariants"]["write_scope"], str(task_dir))

    def test_reviewer_codex_argv_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            adapter = CLISpawnAdapter(["codex", "exec"])
            self.assertEqual(adapter.dialect, "codex")
            result = adapter.spawn(_request(task_dir, role="reviewer"))
            argv = result.detail["argv"]
            self.assertEqual(argv[0], "codex")
            self.assertIn("--sandbox", argv)
            self.assertIn("read-only", argv)
            spec = read_json(task_dir / "spawn_request.json")
            self.assertTrue(spec["invariants"]["read_only"])
            self.assertEqual(spec["role"], "reviewer")

    def test_custom_template_placeholders_substituted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            adapter = CLISpawnAdapter(
                ["mytool", "--in", "{instruction_path}", "--out", "{output_path}"]
            )
            result = adapter.spawn(_request(task_dir, role="worker"))
            argv = result.detail["argv"]
            self.assertEqual(argv[0], "mytool")
            self.assertIn(str(task_dir / "handoff" / "instruction_gen.md"), argv)
            self.assertIn(str(task_dir / "handoff" / "output_gen.json"), argv)

    def test_execute_missing_binary_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            adapter = CLISpawnAdapter(
                ["definitely_not_a_real_binary_xyz"], execute=True
            )
            with self.assertRaises(StepError):
                adapter.spawn(_request(task_dir))


class BuildSpawnAdapterTests(unittest.TestCase):
    def _root_with_spawn(self, spawn_cfg: dict | None) -> Path:
        tmp = tempfile.mkdtemp()
        root = Path(tmp)
        (root / "configs").mkdir(parents=True, exist_ok=True)
        config: dict = {"version": "agent-definition.v2", "agents": []}
        if spawn_cfg is not None:
            config["orchestration"] = {"spawn": spawn_cfg}
        write_json(root / "configs" / "agents.json", config)
        return root

    def test_default_is_inline_when_missing(self) -> None:
        root = self._root_with_spawn(None)
        self.assertIsInstance(build_spawn_adapter(root), InlineSpawnAdapter)

    def test_explicit_inline(self) -> None:
        root = self._root_with_spawn({"adapter": "inline"})
        self.assertIsInstance(build_spawn_adapter(root), InlineSpawnAdapter)

    def test_workbuddy_selected(self) -> None:
        root = self._root_with_spawn({"adapter": "workbuddy"})
        self.assertIsInstance(build_spawn_adapter(root), WorkBuddySpawnAdapter)

    def test_native_terminal_adapters_selected(self) -> None:
        root = self._root_with_spawn({"adapter": "inline"})
        self.assertIsInstance(
            build_spawn_adapter(root, override="claude"), ClaudeCodeSpawnAdapter
        )
        self.assertIsInstance(
            build_spawn_adapter(root, override="codex"), CodexSpawnAdapter
        )

    def test_run_override_beats_repository_default(self) -> None:
        root = self._root_with_spawn({"adapter": "inline"})
        adapter = build_spawn_adapter(root, override="workbuddy")
        self.assertIsInstance(adapter, WorkBuddySpawnAdapter)

    def test_environment_beats_repository_default(self) -> None:
        root = self._root_with_spawn({"adapter": "inline"})
        with patch.dict(
            "os.environ",
            {"PRESENTATION_AGENT_SPAWN_ADAPTER": "codex"},
            clear=False,
        ):
            self.assertIsInstance(build_spawn_adapter(root), CodexSpawnAdapter)

    def test_cli_selected_with_command(self) -> None:
        root = self._root_with_spawn({"adapter": "cli", "command": ["codex", "exec"]})
        adapter = build_spawn_adapter(root)
        self.assertIsInstance(adapter, CLISpawnAdapter)
        self.assertEqual(adapter.command, ["codex", "exec"])  # type: ignore[attr-defined]
        self.assertEqual(adapter.dialect, "codex")  # type: ignore[attr-defined]
        self.assertFalse(adapter.execute)  # type: ignore[attr-defined]

    def test_cli_execute_flag_from_config(self) -> None:
        root = self._root_with_spawn(
            {"adapter": "cli", "command": ["claude"], "execute": True}
        )
        adapter = build_spawn_adapter(root)
        self.assertIsInstance(adapter, CLISpawnAdapter)
        self.assertTrue(adapter.execute)  # type: ignore[attr-defined]

    def test_unknown_adapter_raises(self) -> None:
        root = self._root_with_spawn({"adapter": "nope"})
        with self.assertRaises(StepError):
            build_spawn_adapter(root)


if __name__ == "__main__":
    unittest.main()
