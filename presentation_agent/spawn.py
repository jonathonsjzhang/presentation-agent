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
- ``claude``    : emits native Claude Code ``Task`` parameters, including
                  write-tool restrictions for the reviewer.
- ``codex``     : emits native Codex ``spawn_agent`` / ``wait_agent`` parameters,
                  with a read-only reviewer sandbox.
- ``cli``       : Claude Code / Codex headless terminals spawn an isolated
                  process. Builds a concrete argv from a built-in dialect
                  (``claude -p`` / ``codex exec``, with read-only flags for a
                  reviewer) and either emits it into ``spawn_request.json`` for a
                  capable environment to run, or (``execute=True``) runs it via
                  ``subprocess`` when the binary is present.

Design invariants (kept terminal-agnostic so the framework stays portable):

- ``max_depth = 1`` : Codex restricts sub-agent depth to one. A spawned worker
                      must NOT spawn further sub-agents; the L3 reviewer is
                      spawned by the Manager layer, never by the worker itself.
- write scope       : a worker's write operations are confined to its task_dir.
- reviewer delivery : a read-only reviewer returns JSON to the host; the host
                      relays it into the designated review output file.

The Manager state machine (``record_worker_completed`` etc.) is untouched: every
adapter ultimately yields the same handoff/artifact contract the host commits
read today.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from presentation_agent.io import read_json, write_json
from presentation_agent.llm.schema import extract_json
from presentation_agent.step import StepError


SpawnRole = Literal["worker", "reviewer"]
SpawnMode = Literal["foreground", "background"]


def prepare_evidence_subtask(
    *,
    root: Path,
    analysis_dir: Path,
    data_root: Path,
    raw_materials: list[Any],
    analysis_input: dict[str, Any],
) -> dict[str, Any]:
    """Create the real Evidence worker package below an Analysis task.

    This deliberately does not use Manager or PipelineStepper.  Evidence stays
    an auditable internal subtask while reusing its existing skill and schema.
    """

    from presentation_agent.models import now_iso
    from presentation_agent.step import StepRunner

    subtask_dir = analysis_dir / "subtasks" / "evidence_harvester"
    subtask_dir.mkdir(parents=True, exist_ok=True)
    input_path = subtask_dir / "input.json"
    if not input_path.exists():
        write_json(
            input_path,
            {
                "schema": "manager_task.v1",
                "raw_materials": raw_materials,
                "report_charter": analysis_input.get("report_charter", analysis_input),
                "evidence_scope": analysis_input.get("analysis_objective", ""),
            },
        )
    run_state_path = subtask_dir / "run_state.json"
    if not run_state_path.exists():
        write_json(
            run_state_path,
            {
                "run_id": f"evidence-{now_iso().replace(':', '')}",
                "contract_profile": "v0_3",
                "agent_id": "evidence_harvester",
                "agent_name": "证据完整盘点",
                "stage": 0,
                "status": "init",
                "current_step": "init",
                "round_index": 0,
                "input_path": str(input_path),
                "output_dir": str(subtask_dir),
                "p0_open": [],
                "p1_open": [],
                "produced_artifacts": [],
                "history": [],
                "created_at": now_iso(),
                "updated_at": now_iso(),
            },
        )
    runner = StepRunner(
        root, subtask_dir, data_root=data_root, contract_profile="v0_3"
    )
    state = read_json(run_state_path, default={})
    if state.get("current_step") == "init":
        prepared = runner.prepare()
    elif state.get("current_step") == "awaiting_gen_output":
        prepared = {
            "step": "evidence",
            "instruction_path": str(subtask_dir / "handoff" / "instruction_gen.md"),
            "output_path": str(subtask_dir / "handoff" / "output_gen.json"),
        }
    else:
        raise StepError(
            f"Evidence 子任务处于不可恢复状态: {state.get('current_step')}"
        )
    prepared.update(
        {
            "step": "evidence",
            "agent_id": "evidence_harvester",
            "subtask": True,
            "subtask_dir": str(subtask_dir),
            "input_path": str(input_path),
        }
    )
    return prepared


def commit_evidence_subtask(
    *,
    root: Path,
    subtask_dir: Path,
    data_root: Path,
) -> dict[str, Any]:
    """Schema-gate one Evidence generation without an internal retry."""

    from presentation_agent.agent_profiles import load_agent_profile
    from presentation_agent.capabilities.compiler import compile_skill_package
    from presentation_agent.review import ArtifactReviewer

    output_path = subtask_dir / "handoff" / "output_gen.json"
    if not output_path.exists():
        raise StepError(f"Evidence 输出不存在: {output_path}")
    try:
        catalog = extract_json(output_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise StepError(f"Evidence 输出不是合法 JSON: {exc}") from exc
    profile = load_agent_profile(root, "v0_3")
    spec = profile.support_specs["evidence_harvester"]
    input_data = read_json(subtask_dir / "input.json", default={})
    package = compile_skill_package(root, spec, input_data)
    objections = ArtifactReviewer(llm=None)._schema_gate(
        spec, catalog, package.to_dict()
    )
    review = {"reviewer": "schema_gate", "objections": [o.to_dict() for o in objections]}
    write_json(subtask_dir / "review.json", review)
    if any(o.severity == "P0" for o in objections):
        raise StepError("Evidence Catalog schema gate 未通过；本轮不会自动重试")
    write_json(subtask_dir / "evidence_catalog.json", catalog)
    state_path = subtask_dir / "run_state.json"
    state = read_json(state_path, default={})
    state["status"] = "completed"
    state["current_step"] = "done"
    state["produced_artifacts"] = [
        str(subtask_dir / "evidence_catalog.json"),
        str(subtask_dir / "review.json"),
    ]
    write_json(state_path, state)
    return catalog


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

    def __post_init__(self) -> None:
        """Keep Analysis' internal Evidence spawn confined to its subtask."""

        evidence_dir = next(
            (
                parent
                for parent in (self.instruction_path, *self.instruction_path.parents)
                if parent.name == "evidence_harvester"
                and parent.parent.name == "subtasks"
            ),
            None,
        )
        if evidence_dir is None:
            return
        self.task_dir = evidence_dir
        self.agent_id = "evidence_harvester"
        self.input_path = evidence_dir / "input.json"


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
        result_delivery = "direct_file" if request.role == "worker" else "host_relay"
        spec = {
            "host": "workbuddy",
            "subagent_type": subagent_type,
            "agent_id": request.agent_id,
            "role": request.role,
            "mode": request.mode,
            "instruction_path": str(request.instruction_path),
            "input_path": str(request.input_path),
            "output_path": str(request.output_path),
            "result_delivery": result_delivery,
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
                "host": "workbuddy",
                "tool": "Agent",
                "subagent_type": subagent_type,
                "result_delivery": result_delivery,
                "invariants": spec["invariants"],
            },
        )


class ClaudeCodeSpawnAdapter(SpawnAdapter):
    """Emit a request for Claude Code's native Task sub-agent tool."""

    kind = "claude"

    def spawn(self, request: SpawnRequest) -> SpawnResult:
        subagent_type = "general-purpose" if request.role == "worker" else "Explore"
        result_delivery = "direct_file" if request.role == "worker" else "host_relay"
        spec = {
            "host": "claude_code",
            "tool": "Task",
            "subagent_type": subagent_type,
            "agent_id": request.agent_id,
            "role": request.role,
            "mode": request.mode,
            "instruction_path": str(request.instruction_path),
            "input_path": str(request.input_path),
            "output_path": str(request.output_path),
            "result_delivery": result_delivery,
            "disallowed_tools": (
                [] if request.role == "worker" else ["Write", "Edit", "Bash", "NotebookEdit"]
            ),
            "invariants": {
                "max_depth": 1,
                "write_scope": str(request.task_dir),
                "read_only": request.role == "reviewer",
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
                "host": "claude_code",
                "tool": "Task",
                "subagent_type": subagent_type,
                "disallowed_tools": spec["disallowed_tools"],
                "result_delivery": result_delivery,
                "invariants": spec["invariants"],
            },
        )


class CodexSpawnAdapter(SpawnAdapter):
    """Emit a request for Codex's native spawn_agent/wait_agent tools."""

    kind = "codex"

    def spawn(self, request: SpawnRequest) -> SpawnResult:
        native_role = "worker" if request.role == "worker" else "explorer"
        sandbox_mode = "workspace-write" if request.role == "worker" else "read-only"
        result_delivery = "direct_file" if request.role == "worker" else "host_relay"
        spec = {
            "host": "codex",
            "tool": "spawn_agent",
            "wait_tool": "wait_agent",
            "native_role": native_role,
            "sandbox_mode": sandbox_mode,
            "agent_id": request.agent_id,
            "role": request.role,
            "mode": request.mode,
            "instruction_path": str(request.instruction_path),
            "input_path": str(request.input_path),
            "output_path": str(request.output_path),
            "result_delivery": result_delivery,
            "invariants": {
                "max_depth": 1,
                "write_scope": str(request.task_dir),
                "read_only": request.role == "reviewer",
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
                "host": "codex",
                "tool": "spawn_agent",
                "wait_tool": "wait_agent",
                "native_role": native_role,
                "sandbox_mode": sandbox_mode,
                "result_delivery": result_delivery,
                "invariants": spec["invariants"],
            },
        )


# Built-in dialects for the two headless terminals we target. Each entry is a
# command *template*: tokens are substituted per-spawn. ``{prompt}`` becomes a
# self-contained instruction that tells the headless agent which files to read
# and where to write its handoff output; the read-only flags below are what give
# a reviewer its physical maker-checker isolation (it cannot mutate artifacts).
CLI_DIALECTS: dict[str, dict[str, list[str]]] = {
    # Claude Code headless: `claude -p "<prompt>"`. A reviewer is constrained to
    # read-only by disallowing every write/exec tool.
    "claude": {
        "worker": ["claude", "-p", "{prompt}"],
        "reviewer": [
            "claude",
            "-p",
            "{prompt}",
            "--disallowedTools",
            "Write,Edit,Bash,NotebookEdit",
        ],
    },
    # Codex headless: `codex exec "<prompt>"`. A reviewer runs in a read-only
    # sandbox so it physically cannot write the artifact back.
    "codex": {
        "worker": ["codex", "exec", "{prompt}"],
        "reviewer": ["codex", "exec", "--sandbox", "read-only", "{prompt}"],
    },
}


def _detect_dialect(command: list[str]) -> str | None:
    """Infer the dialect (claude/codex) from the configured command's binary."""

    if not command:
        return None
    binary = Path(command[0]).name.lower()
    for name in CLI_DIALECTS:
        if name in binary:
            return name
    return None


def _build_cli_prompt(request: SpawnRequest) -> str:
    """A self-contained prompt for a headless CLI sub-agent.

    The headless agent has no host conversation history, so the prompt must point
    it at the instruction package (which embeds the full SKILL.md), the task
    input, and the exact handoff file it must write back.
    """

    if request.role == "reviewer":
        return (
            "You are an isolated read-only reviewer sub-agent (the checker in a "
            "maker-checker loop). Read the review instruction package at "
            f"{request.instruction_path} (it embeds the rubrics and the artifact "
            "under review) and the task input at "
            f"{request.input_path}. Audit the artifact strictly against the P0/P1 "
            "rubrics and return ONLY a JSON object on stdout of the exact form "
            '{"objections": [{"rubric_id","severity","dimension","message",'
            '"evidence","suggestion"}]} (empty list if it passes). '
            "Do not modify any file."
        )
    return (
        "You are an isolated worker sub-agent with no host conversation history. "
        f"Read your self-contained instruction package at {request.instruction_path} "
        f"(it embeds the full SKILL.md role, workflow and output contract) and the "
        f"task input at {request.input_path}. Produce the contract-compliant JSON "
        f"and write it (a single valid JSON object, no markdown fences) to "
        f"{request.output_path}. Confine all writes to {request.task_dir}."
    )


class CLISpawnAdapter(SpawnAdapter):
    """Claude Code / Codex headless terminals: spawn an isolated process.

    Two execution modes, matching the WorkBuddy adapter's philosophy of emitting
    a portable spawn intent that the capable environment fulfils:

    - ``execute=False`` (default): build the concrete argv and persist a
      ``spawn_request.json`` (cli variant) recording the full command. The host
      orchestration script (or CI) runs it. This keeps the Python side free of a
      hard dependency on the CLI binary being installed.
    - ``execute=True``: actually ``subprocess.run`` the headless agent. Used when
      the binary is present (verified via ``shutil.which``); otherwise it raises.

    The command can be a built-in dialect (inferred from the binary name, e.g.
    ``["claude"]`` / ``["codex"]``) or a fully custom template containing the
    placeholders ``{prompt} {instruction_path} {input_path} {output_path}
    {task_dir}``.
    """

    kind = "cli"

    def __init__(
        self,
        command: list[str] | None = None,
        *,
        execute: bool = False,
        dialect: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.command = command or []
        self.execute = execute
        self.dialect = dialect or _detect_dialect(self.command)
        self.timeout = timeout

    def _resolve_template(self, role: SpawnRole) -> list[str]:
        """Return the argv template for this role.

        A custom command (containing placeholders) wins; otherwise fall back to
        the built-in dialect's worker/reviewer template.
        """

        if self.command and any("{" in tok for tok in self.command):
            return list(self.command)
        if self.dialect and self.dialect in CLI_DIALECTS:
            return list(CLI_DIALECTS[self.dialect][role])
        if self.command:
            # Bare binary like ["claude"] with no recognised dialect: append the
            # prompt so the command is still runnable.
            return list(self.command) + ["{prompt}"]
        raise StepError("CLISpawnAdapter 需要 command 或可识别的 dialect")

    def _render_argv(self, request: SpawnRequest) -> list[str]:
        template = self._resolve_template(request.role)
        prompt = _build_cli_prompt(request)
        subs = {
            "prompt": prompt,
            "instruction_path": str(request.instruction_path),
            "input_path": str(request.input_path),
            "output_path": str(request.output_path),
            "task_dir": str(request.task_dir),
        }
        return [tok.format(**subs) for tok in template]

    def spawn(self, request: SpawnRequest) -> SpawnResult:
        argv = self._render_argv(request)
        result_delivery = "direct_file" if request.role == "worker" else "host_relay"
        spec = {
            "host": "cli",
            "dialect": self.dialect,
            "agent_id": request.agent_id,
            "role": request.role,
            "mode": request.mode,
            "argv": argv,
            "instruction_path": str(request.instruction_path),
            "input_path": str(request.input_path),
            "output_path": str(request.output_path),
            "result_delivery": result_delivery,
            "invariants": {
                "max_depth": 1,
                "write_scope": str(request.task_dir),
                "read_only": request.role == "reviewer",
            },
        }
        spawn_file = request.task_dir / "spawn_request.json"
        write_json(spawn_file, spec)

        if not self.execute:
            # Emit-only: a capable environment runs argv later.
            return SpawnResult(
                status="dispatched",
                artifact_path=None,
                detail={
                    "spawn_request": str(spawn_file),
                    "executor": "cli_command_emitted",
                    "dialect": self.dialect,
                    "argv": argv,
                    "result_delivery": result_delivery,
                },
            )

        binary = argv[0]
        if shutil.which(binary) is None:
            raise StepError(f"CLI 二进制不存在，无法 execute: {binary}")
        proc = subprocess.run(  # noqa: S603 - argv is built from a controlled template
            argv,
            cwd=str(request.task_dir),
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        if proc.returncode != 0:
            return SpawnResult(
                status="failed",
                artifact_path=None,
                detail={
                    "spawn_request": str(spawn_file),
                    "executor": "cli_subprocess",
                    "returncode": proc.returncode,
                    "stderr": proc.stderr[-2000:],
                },
            )
        if request.role == "reviewer":
            try:
                write_json(request.output_path, extract_json(proc.stdout))
            except ValueError as exc:
                return SpawnResult(
                    status="failed",
                    artifact_path=None,
                    detail={
                        "spawn_request": str(spawn_file),
                        "executor": "cli_subprocess",
                        "returncode": 0,
                        "error": f"reviewer stdout is not valid JSON: {exc}",
                        "stdout": proc.stdout[-2000:],
                        "result_delivery": result_delivery,
                    },
                )
        return SpawnResult(
            status="completed",
            artifact_path=request.output_path,
            detail={
                "spawn_request": str(spawn_file),
                "executor": "cli_subprocess",
                "returncode": 0,
                "stdout": proc.stdout[-2000:],
                "result_delivery": result_delivery,
            },
        )


def build_spawn_adapter(root: Path, override: str | None = None) -> SpawnAdapter:
    """Select an adapter from ``configs/agents.json`` orchestration.spawn.

    Selection precedence:
    1. Per-run/CLI override.
    2. ``PRESENTATION_AGENT_SPAWN_ADAPTER``.
    3. Repository config.
    4. ``inline`` compatibility fallback.
    """

    config = read_json(root / "configs" / "agents.json", default={})
    spawn_cfg = config.get("orchestration", {}).get("spawn", {})
    kind = (
        override
        or os.environ.get("PRESENTATION_AGENT_SPAWN_ADAPTER")
        or spawn_cfg.get("adapter")
        or "inline"
    )
    aliases = {
        "wb": "workbuddy",
        "work-buddy": "workbuddy",
        "claude-code": "claude",
        "claude_code": "claude",
        "cc": "claude",
    }
    kind = aliases.get(str(kind).lower(), str(kind).lower())
    if kind == "inline":
        return InlineSpawnAdapter()
    if kind == "workbuddy":
        return WorkBuddySpawnAdapter()
    if kind == "claude":
        return ClaudeCodeSpawnAdapter()
    if kind == "codex":
        return CodexSpawnAdapter()
    if kind == "cli":
        return CLISpawnAdapter(
            spawn_cfg.get("command", []),
            execute=bool(spawn_cfg.get("execute", False)),
            dialect=spawn_cfg.get("dialect"),
            timeout=spawn_cfg.get("timeout"),
        )
    raise StepError(f"未知 spawn adapter: {kind}")
