"""Terminal-agnostic sub-agent spawn adapters.

This module introduces a thin "spawn" layer that decides *how* a Worker step is
executed once the Manager control plane has prepared its task directory and
self-contained instruction package:

- ``inline``    : default. Do NOT spawn anything. The host's main model (the
                  current conversation) reads the instruction package produced by
                  ``StepRunner.prepare`` and writes the handoff output itself.
                  This is byte-for-byte the behaviour the project has today, so
                  enabling the spawn layer with the default config is a no-op.
- ``workbuddy`` : the host (WorkBuddy) spawns an isolated-context sub-agent via
                  its native ``Agent`` tool. Python cannot call that tool itself,
                  so this adapter writes a ``spawn_request.json`` into the task
                  directory; the host SKILL.md dispatch rules read it and perform
                  the real ``Agent`` spawn.
- ``cli``       : Claude Code / Codex headless terminals spawn an isolated
                  process. Implemented in phase two; a placeholder lives here.

Design invariants (kept terminal-agnostic so the framework stays portable):

- ``max_depth = 1`` : Codex restricts sub-agent depth to one. A spawned worker
                      must NOT spawn further sub-agents; the L3 reviewer is
                      spawned by the Manager layer, never by the worker itself.
- write scope       : a worker's write operations are confined to its task_dir.

The Manager state machine (``record_worker_completed`` etc.) is untouched: every
adapter ultimately yields the same handoff/artifact contract the host commits
read today.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from presentation_agent.io import read_json, write_json
from presentation_agent.step import StepError


SpawnRole = Literal["worker", "reviewer"]
SpawnMode = Literal["foreground", "background"]


@dataclass
class SpawnRequest:
    """A self-contained spawn request assembled by the Manager control plane.

    Fields are populated from facts that already exist after
    ``StepRunner.prepare`` runs: the instruction/output handoff paths come from
    the prepared instruction dict, ``agent_id`` from ``run_state.json``.
    """

    task_dir: Path
    agent_id: str
    role: SpawnRole
    instruction_path: Path
    output_path: Path
    input_path: Path
    mode: SpawnMode = "foreground"


@dataclass
class SpawnResult:
    """Outcome of a spawn attempt; the Manager accepts work via its own loop."""

    status: Literal["dispatched", "completed", "failed"]
    artifact_path: Path | None = None
    detail: dict[str, Any] = field(default_factory=dict)


class SpawnAdapter(ABC):
    """Terminal-agnostic sub-agent spawn contract. One implementation per host."""

    kind: str = "base"

    @abstractmethod
    def spawn(self, request: SpawnRequest) -> SpawnResult:
        """Spawn an isolated-context sub-agent to execute ``request``."""
        raise NotImplementedError


class InlineSpawnAdapter(SpawnAdapter):
    """Default adapter = today's behaviour. Spawns nothing.

    ``StepRunner.prepare`` has already written the instruction package; control
    returns to the host, which writes the handoff output and then calls commit.
    Guarantees zero regression risk.
    """

    kind = "inline"

    def spawn(self, request: SpawnRequest) -> SpawnResult:  # noqa: D401
        return SpawnResult(status="dispatched", artifact_path=None, detail={})


class WorkBuddySpawnAdapter(SpawnAdapter):
    """WorkBuddy host: emit a spawn request file for the host Agent tool.

    Python cannot invoke the host's ``Agent`` tool directly, so we persist a
    ``spawn_request.json`` describing exactly what to spawn. The host SKILL.md
    dispatch rules read it and perform the real isolated-context spawn.
    """

    kind = "workbuddy"

    def spawn(self, request: SpawnRequest) -> SpawnResult:
        subagent_type = "general-purpose" if request.role == "worker" else "Explore"
        spec = {
            "host": "workbuddy",
            "subagent_type": subagent_type,
            "agent_id": request.agent_id,
            "role": request.role,
            "mode": request.mode,
            "instruction_path": str(request.instruction_path),
            "input_path": str(request.input_path),
            "output_path": str(request.output_path),
            "invariants": {
                "max_depth": 1,
                "write_scope": str(request.task_dir),
            },
        }
        spawn_file = request.task_dir / "spawn_request.json"
        write_json(spawn_file, spec)
        return SpawnResult(
            status="dispatched",
            artifact_path=None,
            detail={
                "spawn_request": str(spawn_file),
                "executor": "host_agent_tool",
                "subagent_type": subagent_type,
            },
        )


class CLISpawnAdapter(SpawnAdapter):
    """Claude Code / Codex headless terminals: spawn an isolated process.

    Phase-two implementation. The command template (e.g. ``["claude", "-p"]`` or
    ``["codex", "exec"]``) is supplied from configs.
    """

    kind = "cli"

    def __init__(self, command: list[str] | None = None) -> None:
        self.command = command or []

    def spawn(self, request: SpawnRequest) -> SpawnResult:
        raise NotImplementedError("CLISpawnAdapter is implemented in phase two")


def build_spawn_adapter(root: Path) -> SpawnAdapter:
    """Select an adapter from ``configs/agents.json`` orchestration.spawn.

    Defaults to ``inline`` (zero-regression) when the key is absent.
    """

    config = read_json(root / "configs" / "agents.json", default={})
    spawn_cfg = config.get("orchestration", {}).get("spawn", {})
    kind = spawn_cfg.get("adapter", "inline")
    if kind == "inline":
        return InlineSpawnAdapter()
    if kind == "workbuddy":
        return WorkBuddySpawnAdapter()
    if kind == "cli":
        return CLISpawnAdapter(spawn_cfg.get("command", []))
    raise StepError(f"未知 spawn adapter: {kind}")
