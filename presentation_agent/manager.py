from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from presentation_agent.capabilities.profile import normalize_report_profile
from presentation_agent.capabilities.registry import CapabilityRegistry
from presentation_agent.context import ContextAssembler
from presentation_agent.cross_review import CrossStageReviewer
from presentation_agent.io import append_jsonl, read_json, write_json
from presentation_agent.llm.schema import validate
from presentation_agent.memory import MemoryStore
from presentation_agent.models import AgentSpec, now_iso
from presentation_agent.skill_package import load_skill_package
from presentation_agent.spawn import SpawnRequest, build_spawn_adapter
from presentation_agent.step import StepError, StepRunner


MANAGER_MEMORY_DIMENSIONS = [
    "任务定义",
    "任务拆解",
    "调度",
    "验收",
    "返工",
    "人审偏好",
    "跨阶段一致性",
]


class ManagerAgentRuntime:
    """Build and validate host-executed Manager Agent turns."""

    def __init__(self, root: Path, run_dir: Path, data_root: Path) -> None:
        self.root = root
        self.run_dir = run_dir
        self.data_root = data_root
        self.manager_dir = run_dir / "manager"
        self.handoff_dir = self.manager_dir / "handoff"
        self.handoff_dir.mkdir(parents=True, exist_ok=True)
        self.package = load_skill_package(root, "manager")
        self.memory = MemoryStore(root, "manager", data_root=data_root)

    def prepare(self, context: dict[str, Any], phase: str) -> dict[str, Any]:
        instruction_path = self.handoff_dir / f"instruction_{phase}.md"
        output_path = self.handoff_dir / f"output_{phase}.json"
        memory_guidance = self.memory.generation_guidance(MANAGER_MEMORY_DIMENSIONS, limit=6)
        schema = self._schema("manager_decision.v1")
        rubrics = self.package.rubrics

        lines = [
            f"# 汇报项目 Manager · {phase}",
            "",
            "## Manager Skill",
            "",
            self.package.instructions.strip(),
            "",
            "## 本轮 Manager Context",
            "",
            "```json",
            json.dumps(context, ensure_ascii=False, indent=2),
            "```",
        ]
        if memory_guidance:
            lines.extend([
                "",
                "## 本轮召回的 Manager Memory",
                "",
                *[f"- {item}" for item in memory_guidance],
            ])
        lines.extend([
            "",
            "## 必填字段速查（planning 阶段须写入以下所有嵌套字段）",
            "",
            "### report_charter 必填字段（除 material_inventory/assumptions 外全部 required）",
            "- topic: string",
            "- audience: string (board / exec_office / strategy_lead / business_team / external)",
            "- report_type: string (deep_dive / business_progress / quick_sync)",
            "- output_format: string (document / ppt / html)",
            "- decision_goal: string",
            "- expected_action: string",
            "- scope: string[]  ← 字符串数组，不是 {included,excluded} 对象",
            "- out_of_scope: string[]",
            "- constraints: string[]",
            "- success_criteria: string[]",
            "- global_state_seed: object",
            "- blocking_questions: string[]",
            "",
            "### execution_plan 每项 task 必填字段",
            "- plan_id: string",
            "- tasks: object[]  每项必填: task_id, agent_id, objective, dependencies, status",
            "  - task_id: string  (如 t1, t2, task-argument_synthesis)",
            "  - agent_id: string  (argument_synthesis / storyline_design / page_filling / format / qa_preparation / speaker_script)",
            "  - objective: string  单句描述本任务要产出什么",
            "  - dependencies: string[]  依赖的 task_id 列表, 无依赖则为 []",
            "  - status: string  枚举值 planned / dispatched / completed / accepted / revision_required / skipped",
            "- human_gates: array",
            "- completion_criteria: string[]",
            "",
            "### acceptance_report 必填字段（acceptance 阶段）",
            "- task_id: string  ← 必须精确等于当前验收的 task_id, 不能为 null",
            "- verdict: string  (accept / revise / blocked)",
            "- criteria_results: array",
            "- cross_stage_findings: array",
            "- reason: string",
            "",
            "## Manager Rubrics",
            "",
            "```json",
            json.dumps(rubrics, ensure_ascii=False, indent=2),
            "```",
            "",
            "## 输出 Schema（完整 JSON Schema）",
            "",
            "```json",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "```",
            "",
            "## 输出操作",
            "",
            f"只写一个严格符合 manager_decision.v1 的 JSON 对象到 `{output_path}`。",
            f"`phase` 必须为 `{phase}`。不要输出 Markdown、解释或思考过程。",
        ])
        instruction_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {
            "actor": "manager",
            "step": phase,
            "instruction_path": str(instruction_path),
            "output_path": str(output_path),
        }

    def read_decision(self, phase: str) -> dict[str, Any]:
        output_path = self.handoff_dir / f"output_{phase}.json"
        if not output_path.exists():
            raise StepError(f"Manager 输出不存在: {output_path}")
        try:
            decision = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StepError(f"Manager 输出不是合法 JSON: {exc}") from exc
        if not isinstance(decision, dict):
            raise StepError("Manager 输出必须是 JSON 对象")

        errors = validate(decision, self._schema("manager_decision.v1"))
        if decision.get("phase") != phase:
            errors.append(f"$.phase: expected {phase!r}, got {decision.get('phase')!r}")

        action = decision.get("action")
        if phase == "planning":
            for key, schema_name in (
                ("report_charter", "report_charter.v1"),
                ("execution_plan", "execution_plan.v1"),
                ("task_packet", "task_packet.v1"),
            ):
                value = decision.get(key)
                if not isinstance(value, dict):
                    errors.append(f"$: planning decision missing object '{key}'")
                else:
                    errors.extend(validate(value, self._schema(schema_name), f"$.{key}"))
            if action != "dispatch":
                errors.append("$.action: planning must produce dispatch; runtime applies the plan human gate")
        else:
            report = decision.get("acceptance_report")
            if not isinstance(report, dict):
                errors.append("$: acceptance decision missing object 'acceptance_report'")
            else:
                errors.extend(
                    validate(report, self._schema("acceptance_report.v1"), "$.acceptance_report")
                )
            if action in ("dispatch", "revise"):
                packet = decision.get("task_packet")
                if not isinstance(packet, dict):
                    errors.append(f"$: {action} decision missing object 'task_packet'")
                else:
                    errors.extend(validate(packet, self._schema("task_packet.v1"), "$.task_packet"))
            if action == "complete" and phase != "acceptance":
                errors.append("$.action: complete is only valid during acceptance")

        if errors:
            raise StepError("Manager decision 校验失败:\n- " + "\n- ".join(errors))
        return decision

    def output_path(self, phase: str) -> Path:
        return self.handoff_dir / f"output_{phase}.json"

    def _schema(self, name: str) -> dict[str, Any]:
        schema = self.package.schemas.get(name)
        if not isinstance(schema, dict):
            raise StepError(f"Manager skill 缺少 schema: {name}")
        return schema


class WorkerExecutor:
    """Create isolated specialist task runs under Manager control."""

    def __init__(
        self,
        root: Path,
        run_dir: Path,
        data_root: Path,
        spawn_adapter: Optional[str] = None,
    ) -> None:
        self.root = root
        self.run_dir = run_dir
        self.data_root = data_root
        self.spawn_adapter = build_spawn_adapter(root, override=spawn_adapter)
        config = read_json(root / "configs" / "agents.json", default={})
        self.context_assembler = ContextAssembler(root)
        active = set(config.get("pipeline", {}).get("stages", []))
        self.specs = {
            item["id"]: AgentSpec.from_dict(item)
            for item in config.get("agents", [])
            if item.get("id") in active
        }

    def capabilities(self) -> list[dict[str, Any]]:
        return [
            {
                "agent_id": spec.id,
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "output_schema": spec.output_schema,
                "memory_dimensions": spec.memory_dimensions,
            }
            for spec in sorted(self.specs.values(), key=lambda item: item.stage)
        ]

    def create_task(
        self,
        packet: dict[str, Any],
        report_charter: dict[str, Any],
        raw_brief_path: Path,
    ) -> dict[str, Any]:
        agent_id = str(packet.get("agent_id") or "")
        if agent_id not in self.specs:
            raise StepError(
                f"Manager 派发了未知或非活动 Worker: {agent_id}; "
                f"可用 Worker: {sorted(self.specs)}"
            )
        spec = self.specs[agent_id]
        task_id = self._safe_id(str(packet.get("task_id") or f"task-{agent_id}"))
        task_dir = self._unique_task_dir(task_id, agent_id)
        task_dir.mkdir(parents=True, exist_ok=False)
        (task_dir / "handoff").mkdir(parents=True, exist_ok=True)

        resolved_inputs: list[str] = []
        resolved_artifacts: list[tuple[Path, dict[str, Any]]] = []
        for reference in packet.get("input_artifacts", []):
            path = self._resolve_artifact(str(reference))
            if path is None:
                continue
            resolved_inputs.append(str(path))
            data = read_json(path, default={})
            if isinstance(data, dict) and path.resolve() != raw_brief_path.resolve():
                resolved_artifacts.append((path, data))

        raw_brief = read_json(raw_brief_path, default={})
        worker_input = self.context_assembler.assemble(
            worker_id=agent_id,
            report_charter=report_charter,
            manager_task=packet,
            raw_brief=raw_brief if isinstance(raw_brief, dict) else {},
            raw_brief_path=raw_brief_path,
            artifacts=resolved_artifacts,
        )

        input_path = task_dir / "input.json"
        write_json(input_path, worker_input)
        context_manifest_path = task_dir / "context_manifest.json"
        write_json(
            context_manifest_path,
            {
                "schema": "context_manifest.v1",
                "mode": "projected",
                "worker_id": agent_id,
                "input_path": str(input_path),
                "resolved_input_artifacts": resolved_inputs,
                "inline_sources": {
                    source_id: sorted(source.get("inline_fields", {}).keys())
                    for source_id, source in worker_input.get("inputs", {}).items()
                },
                "material_refs": worker_input.get("material_refs", []),
            },
        )
        run_state = {
            "run_id": f"{task_id}-{now_iso().replace(':', '').replace('+', 'Z')}",
            "task_id": packet.get("task_id"),
            "agent_id": spec.id,
            "agent_name": spec.name,
            "stage": spec.stage,
            "status": "init",
            "current_step": "init",
            "round_index": 0,
            "max_revision_rounds": spec.max_revision_rounds or 2,
            "input_path": str(input_path),
            "manager_task": packet,
            "resolved_input_artifacts": resolved_inputs,
            "context_mode": "projected",
            "context_manifest_path": str(context_manifest_path),
            "output_dir": str(task_dir),
            "p0_open": [],
            "p1_open": [],
            "produced_artifacts": [],
            "history": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        write_json(task_dir / "run_state.json", run_state)
        return {
            "task_id": packet.get("task_id"),
            "agent_id": agent_id,
            "agent_name": spec.name,
            "task_dir": str(task_dir),
            "input_path": str(input_path),
            "packet": packet,
            "status": "dispatched",
            "created_at": now_iso(),
        }

    def prepare(self, task_dir: Path) -> dict[str, Any]:
        instruction = StepRunner(
            self.root, task_dir, data_root=self.data_root
        ).prepare()
        instruction["actor"] = "worker"

        # Spawn split: inline behaves exactly like today; native adapters emit a
        # self-contained spawn request and annotate the instruction. The Manager
        # state machine is unaffected — it still accepts work via artifact_path.
        if self.spawn_adapter.kind != "inline":
            request = self._build_spawn_request(task_dir, instruction)
            result = self.spawn_adapter.spawn(request)
            instruction["spawn"] = {
                "adapter": self.spawn_adapter.kind,
                "role": request.role,
                "status": result.status,
                "detail": result.detail,
            }
        return instruction

    def _build_spawn_request(
        self, task_dir: Path, instruction: dict[str, Any]
    ) -> SpawnRequest:
        run_state = read_json(task_dir / "run_state.json", default={})
        agent_id = str(run_state.get("agent_id") or "")
        step = str(instruction.get("step") or "")
        role = "reviewer" if step.startswith("review") else "worker"
        return SpawnRequest(
            task_dir=task_dir,
            agent_id=agent_id,
            role=role,
            instruction_path=Path(instruction.get("instruction_path", "")),
            output_path=Path(instruction.get("output_path", "")),
            input_path=task_dir / "input.json",
            mode="foreground",
        )

    def _resolve_artifact(self, reference: str) -> Optional[Path]:
        candidate = Path(reference).expanduser()
        candidates = [candidate] if candidate.is_absolute() else [
            self.run_dir / candidate,
            self.run_dir / "tasks" / candidate,
        ]
        for path in candidates:
            if path.exists() and path.is_file() and path.suffix.lower() == ".json":
                return path.resolve()
        return None

    def _unique_task_dir(self, task_id: str, agent_id: str) -> Path:
        base = self.run_dir / "tasks" / f"{task_id}_{agent_id}"
        candidate = base
        index = 2
        while candidate.exists():
            candidate = base.with_name(f"{base.name}_{index}")
            index += 1
        return candidate

    @staticmethod
    def _safe_id(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")
        return (safe or "task")[:80]


class ManagerOrchestrator:
    """Control-plane state machine around Manager Agent and specialist Workers."""

    def __init__(
        self,
        root: Path,
        run_dir: Path,
        data_root: Optional[Path] = None,
        spawn_adapter: Optional[str] = None,
    ) -> None:
        self.root = root
        self.run_dir = run_dir
        self.data_root = data_root or (root / "data")
        self.state_path = run_dir / "manager_state.json"
        self.plan_path = run_dir / "manager_plan.json"
        self.charter_path = run_dir / "report_charter.json"
        self.decisions_path = run_dir / "manager_decisions.jsonl"
        self.raw_brief_path = run_dir / "raw_brief.json"
        self.agent = ManagerAgentRuntime(root, run_dir, self.data_root)
        persisted_adapter = None
        if self.state_path.exists():
            persisted_adapter = read_json(self.state_path, default={}).get("spawn_adapter")
        self.workers = WorkerExecutor(
            root,
            run_dir,
            self.data_root,
            spawn_adapter=spawn_adapter or persisted_adapter,
        )
        if self.state_path.exists() and spawn_adapter:
            state = read_json(self.state_path, default={})
            state["spawn_adapter"] = self.workers.spawn_adapter.kind
            state["updated_at"] = now_iso()
            write_json(self.state_path, state)
        self.cross_reviewer = CrossStageReviewer(root, run_dir)

    def initialize_run(self, brief_path: Path) -> dict[str, Any]:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if brief_path.resolve() != self.raw_brief_path.resolve():
            write_json(self.raw_brief_path, read_json(brief_path, default={}))
        state = {
            "version": "manager_state.v2",
            "run_id": self.run_dir.name,
            "mode": "manager_controlled",
            "status": "running",
            "current_actor": "manager",
            "manager_phase": "brief_confirmation",
            "manager_step": "init",
            "last_event": "start",
            "spawn_adapter": self.workers.spawn_adapter.kind,
            "human_gate": None,
            "current_task": None,
            "tasks": [],
            "accepted_artifacts": [],
            "project_state": {},
            "run_mode": None,  # set during brief confirmation: "full_auto" | "step_by_step"
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        self._save_state(state)
        self._append_decision("start", "Manager run initialized", {"brief_path": str(brief_path)})
        return self.prepare()

    def prepare(self) -> dict[str, Any]:
        state = self._load_state()
        actor = state.get("current_actor")
        if actor == "human":
            return self._human_gate_result(state)
        phase = str(state.get("manager_phase") or "planning")

        # --- brief confirmation: show the brief and ask user to confirm ---
        if phase == "brief_confirmation":
            brief = read_json(self.raw_brief_path, default={})
            missing = []
            if not brief.get("topic"):
                missing.append("topic（汇报主题）")
            if not brief.get("audience"):
                missing.append("audience（汇报对象）")
            if not brief.get("output_format"):
                missing.append("output_format（交付格式，如 ppt/html/docx）")
            # Available workers for user to choose from
            available_workers = [
                "argument_synthesis", "storyline_design", "page_filling",
                "format", "qa_preparation", "speaker_script"
            ]
            selected_workers = brief.get("selected_workers") or available_workers
            user_message = self._format_brief_confirmation(brief, selected_workers)
            state["current_actor"] = "human"
            state["human_gate"] = "brief"
            state["pending_decision"] = {
                "brief": brief,
                "missing_fields": missing,
                "available_workers": available_workers,
                "selected_workers": selected_workers,
                "user_message": user_message,
            }
            state["status"] = "awaiting_brief_confirmation"
            self._save_state(state)
            return self._human_gate_result(state)

        if actor == "worker":
            task_dir = self.current_worker_dir(state)
            if task_dir is None:
                raise StepError("Manager state 缺少当前 Worker task_dir")
            runner = StepRunner(self.root, task_dir, data_root=self.data_root)
            status = runner.status()
            if str(status.get("current_step", "")).startswith("awaiting_"):
                instruction = {
                    "actor": "worker",
                    "step": status.get("current_step"),
                    "instruction_path": status.get("instruction_path"),
                    "output_path": status.get("output_path"),
                }
                # Spawn split on the awaiting_* read path. The StepRunner already
                # advanced into a sub-step (e.g. review/revise) whose handoff files
                # exist on disk; prepare() short-circuits here without going through
                # WorkerExecutor.prepare(), so native adapters would otherwise never
                # (re-)emit a spawn_request for this sub-step. Annotate it here so the
                # read-only reviewer / revise worker is physically dispatched with the
                # correct capability contract instead of leaving a stale request.
                self._annotate_spawn(task_dir, instruction)
                has_spawn = bool(instruction.get("spawn"))
                instruction["next_action"] = (
                    "host_spawn_then_submit" if has_spawn
                    else "host_write_output_then_report_submit"
                )
                state["last_instruction"] = instruction
                self._save_state(state)
                return instruction
            return self.workers.prepare(task_dir)
        if actor != "manager":
            raise StepError(f"未知 current_actor: {actor}")

        phase = str(state.get("manager_phase") or "planning")
        if state.get("manager_step") == "awaiting_output":
            instruction = state.get("last_instruction")
            if isinstance(instruction, dict):
                return instruction
        context = self._manager_context(state)
        instruction = self.agent.prepare(context, phase)
        state["manager_step"] = "awaiting_output"
        state["last_instruction"] = instruction
        self._save_state(state)
        self._append_decision("prepare_manager", f"Manager {phase} instruction prepared", {})
        return instruction

    def commit_manager(self) -> dict[str, Any]:
        state = self._load_state()
        if state.get("current_actor") != "manager" or state.get("manager_step") != "awaiting_output":
            raise StepError("当前没有等待提交的 Manager 输出")
        phase = str(state.get("manager_phase") or "planning")
        decision = self.agent.read_decision(phase)
        if phase == "acceptance":
            current_task = state.get("current_task") or {}
            report = decision.get("acceptance_report") or {}
            if report.get("task_id") != current_task.get("task_id"):
                raise StepError(
                    "acceptance_report.task_id 与当前任务不一致: "
                    f"你写的={report.get('task_id')!r}, 系统期望={current_task.get('task_id')!r}。"
                    " 是否忘记将 acceptance_report.task_id 从上一环节改为当前环节？"
                )
            verdict = report.get("verdict")
            action = decision.get("action")
            if action in ("dispatch", "complete") and verdict != "accept":
                raise StepError(f"Manager action={action} 要求 acceptance verdict=accept")
            if action == "revise" and verdict != "revise":
                raise StepError("Manager action=revise 要求 acceptance verdict=revise")
        self._archive_decision(decision)
        self._append_decision(
            str(decision.get("action")),
            str(decision.get("reason_summary")),
            {"phase": phase, "decision": decision},
        )
        state["last_manager_decision"] = decision
        state["manager_step"] = "decision_committed"
        state["project_state"].update(decision.get("state_updates") or {})

        if phase == "planning":
            return self._commit_plan(state, decision)
        return self._commit_acceptance(state, decision)

    def record_worker_completed(self, result: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state()
        task = state.get("current_task")
        if state.get("current_actor") != "worker" or not isinstance(task, dict):
            raise StepError("当前没有可交给 Manager 验收的 Worker")
        task["status"] = "worker_completed"
        task["artifact_path"] = result.get("artifact_path")
        task["review_summary"] = result.get("review_summary")
        task["completed_at"] = now_iso()
        self._replace_task(state, task)
        self._set_plan_task_status(str(task.get("task_id") or ""), "completed")
        state["execution_plan"] = read_json(self.plan_path, default={})

        task_dir = Path(str(task["task_dir"]))
        cross_review = self.cross_reviewer.review_stage(task_dir)
        state["worker_result"] = {
            "task_id": task.get("task_id"),
            "agent_id": task.get("agent_id"),
            "artifact_path": result.get("artifact_path"),
            "artifact": read_json(Path(str(result.get("artifact_path"))), default={}),
            "worker_review_summary": result.get("review_summary"),
            "worker_memory_notes": result.get("memory_notes"),
            "cross_stage_review": cross_review,
            "profile_inheritance": self._profile_inheritance(
                state.get("report_charter", {}),
                read_json(Path(str(result.get("artifact_path"))), default={}),
            ),
        }
        state["current_actor"] = "manager"
        state["manager_phase"] = "acceptance"
        state["manager_step"] = "init"
        state["last_event"] = "worker_completed"
        self._save_state(state)
        self._append_decision(
            "worker_completed",
            "Worker result handed to Manager for acceptance",
            {"task_id": task.get("task_id"), "agent_id": task.get("agent_id")},
        )
        return self.prepare()

    def approve(self) -> dict[str, Any]:
        state = self._load_state()
        if state.get("current_actor") != "human":
            raise StepError("当前没有等待人工确认的 Manager gate")
        gate = state.get("human_gate")
        decision = state.get("pending_decision") or {}
        if gate == "brief":
            brief_data = decision.get("brief", {})
            # run_mode: "full_auto" | "step_by_step" | ["agent_id", ...]
            raw_run_mode = decision.get("run_mode") or brief_data.get("run_mode")
            if isinstance(raw_run_mode, list):
                state["run_mode"] = raw_run_mode  # custom pause points
                state["custom_pause_agents"] = raw_run_mode
            elif raw_run_mode == "full_auto":
                state["run_mode"] = "full_auto"
            else:
                state["run_mode"] = "step_by_step"  # default
            state["human_gate"] = None
            state["pending_decision"] = None
            state["current_actor"] = "manager"
            state["manager_phase"] = "planning"
            state["manager_step"] = "init"
            state["last_event"] = "brief_confirmed"
            state["status"] = "planning"
            self._save_state(state)
            self._append_decision("brief_confirmed",
                f"用户确认了 brief，run_mode={state['run_mode']}",
                {"brief": brief_data})
            return {"actor": "manager", "step": "planning",
                    "message": "Brief 已确认，开始规划。"}
        if gate == "plan":
            packet = decision.get("task_packet")
            if not isinstance(packet, dict):
                raise StepError("已批准计划，但 Manager decision 中没有首个 task_packet")
            state["human_gate"] = None
            state["pending_decision"] = None
            return self._dispatch(state, packet, reason="human approved Manager plan")
        if gate == "worker_result":
            # In step_by_step mode: user reviewed intermediate output, proceed to next worker
            state["human_gate"] = None
            state["pending_decision"] = None
            packet = decision.get("task_packet")
            if not isinstance(packet, dict):
                raise StepError("已确认中间产物，但 Manager decision 中没有 task_packet")
            state["current_actor"] = "manager"
            self._save_state(state)
            return self._dispatch(state, packet, reason="user reviewed intermediate result")
        if gate == "final":
            state["status"] = "completed"
            state["current_actor"] = "human"
            state["human_gate"] = None
            state["pending_decision"] = None
            state["completed_at"] = now_iso()
            self._save_state(state)
            self._append_decision("complete", "User approved final Manager delivery", {})
            return {
                "actor": "manager",
                "step": "completed",
                "status": "completed",
                "run_dir": str(self.run_dir),
                "accepted_artifacts": state.get("accepted_artifacts", []),
                "present_to_user": decision.get("user_message") or "汇报项目已完成并通过最终确认。",
            }
        if gate == "decision":
            packet = decision.get("task_packet")
            if isinstance(packet, dict):
                state["human_gate"] = None
                state["pending_decision"] = None
                return self._dispatch(state, packet, reason="human approved Manager escalation")
            raise StepError("该 Manager 决策需要用户补充反馈，不能直接 approve")
        raise StepError(f"未知 human gate: {gate}")

    def record_human_feedback(self, text: str) -> dict[str, Any]:
        state = self._load_state()
        if state.get("current_actor") != "human":
            raise StepError("当前不在人工决策节点，不能提交 Manager feedback")
        feedback = str(text or "").strip()
        if not feedback:
            raise StepError("Manager feedback 不能为空")
        gate = state.get("human_gate")
        state.setdefault("human_feedback", []).append({
            "at": now_iso(),
            "gate": gate,
            "text": feedback,
        })
        state["current_actor"] = "manager"
        _phase_after_feedback = {
            "brief": "brief_confirmation",
            "plan": "planning",
            "worker_result": "acceptance",
            "decision": "acceptance",
            "final": "acceptance",
        }
        state["manager_phase"] = _phase_after_feedback.get(gate, "acceptance")
        state["manager_step"] = "init"
        state["last_event"] = "human_feedback"
        state["human_gate"] = None
        state["status"] = "running"
        state["previous_pending_decision"] = state.get("pending_decision")
        state["pending_decision"] = None
        self._save_state(state)
        self._append_decision(
            "human_feedback",
            "Human feedback returned to Manager",
            {"gate": gate, "text": feedback},
        )
        return self.prepare()

    def status(self) -> dict[str, Any]:
        state = self._load_state()
        worker_status = None
        task_dir = self.current_worker_dir(state)
        if task_dir and (task_dir / "run_state.json").exists():
            worker_status = StepRunner(
                self.root, task_dir, data_root=self.data_root
            ).status()
        return {
            "state": state,
            "charter": read_json(self.charter_path, default={}),
            "plan": read_json(self.plan_path, default={}),
            "worker": worker_status,
            "decisions_path": str(self.decisions_path),
        }

    def current_worker_dir(self, state: Optional[dict[str, Any]] = None) -> Optional[Path]:
        current = (state or self._load_state()).get("current_task")
        if not isinstance(current, dict) or not current.get("task_dir"):
            return None
        return Path(str(current["task_dir"]))

    def _annotate_spawn(self, task_dir: Path, instruction: dict[str, Any]) -> None:
        """Emit a spawn_request for an awaiting_* sub-step and annotate the
        instruction. No-op for the inline adapter (preserves today's behaviour).

        The sub-step's role is derived from the step name via the same rule as
        WorkerExecutor: review/revise-review steps spawn a read-only reviewer,
        everything else a writable worker. This keeps the maker-checker capability
        contract physically enforced on the awaiting_* read path too, not only on
        the dispatch/prepare transition path.
        """
        adapter = self.workers.spawn_adapter
        if adapter.kind == "inline":
            return
        # _build_spawn_request keys off instruction["step"]; the awaiting_* short
        # circuit only has current_step, which already carries the sub-step name
        # (e.g. "awaiting_review_output" / "awaiting_revise_output").
        step = str(instruction.get("step") or "")
        sub = step[len("awaiting_"):] if step.startswith("awaiting_") else step
        request = self.workers._build_spawn_request(
            task_dir, {**instruction, "step": sub}
        )
        result = adapter.spawn(request)
        instruction["spawn"] = {
            "adapter": adapter.kind,
            "role": request.role,
            "status": result.status,
            "detail": result.detail,
        }

    def copy_manager_output(self, output_file: Path) -> None:
        state = self._load_state()
        if state.get("current_actor") != "manager" or state.get("manager_step") != "awaiting_output":
            raise StepError("当前没有等待外部文件的 Manager 输出")
        phase = str(state.get("manager_phase") or "planning")
        self.agent.output_path(phase).write_text(
            output_file.read_text(encoding="utf-8"), encoding="utf-8"
        )

    def _commit_plan(self, state: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        charter = decision["report_charter"]
        plan = decision["execution_plan"]
        write_json(self.charter_path, charter)
        write_json(self.plan_path, plan)
        global_state = dict(charter.get("global_state_seed") or {})
        global_state.update({
            "report_charter": charter,
            "updated_at": now_iso(),
        })
        write_json(self.run_dir / "state.json", global_state)
        state["report_charter"] = charter
        state["execution_plan"] = plan
        state["current_actor"] = "human"
        state["human_gate"] = "plan"
        state["pending_decision"] = decision
        state["status"] = "awaiting_plan_approval"
        self._save_state(state)
        return self._human_gate_result(state)

    def _scan_acceptance_memory(
        self, state: dict[str, Any], decision: dict[str, Any]
    ) -> list[str]:
        """Scan Manager memory for acceptance-stage insights.

        Looks at historical memory tagged with dimensions relevant to
        acceptance: 验收, 返工, 跨阶段一致性.  Returns human-readable
        reminders that the Manager can factor into its acceptance decision.
        """
        alerts: list[str] = []
        report = decision.get("acceptance_report") or {}
        verdict = report.get("verdict", "")
        try:
            memory_items = self.agent.memory.scan()
        except Exception:
            return alerts

        acceptance_dims = {"验收", "返工", "跨阶段一致性"}
        for item in memory_items:
            dims = set(str(item.get("dimension", "")).split(","))
            if not acceptance_dims & dims:
                continue
            trigger = str(item.get("trigger", ""))
            suggestion = str(item.get("suggestion", ""))
            hit_count = int(item.get("hit_count", 0))
            # Only surface items with enough history to be trustworthy
            if hit_count < 2:
                continue
            # Check if trigger matches the current acceptance context
            agent_id = state.get("current_task", {}).get("agent_id", "")
            if trigger and agent_id and trigger not in agent_id and trigger not in verdict:
                continue
            alerts.append(suggestion or trigger)
        return alerts

    def _commit_acceptance(self, state: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        action = decision["action"]
        task = state.get("current_task")

        # --- Manager memory scan for acceptance insights ---
        memory_alerts = self._scan_acceptance_memory(state, decision)
        if memory_alerts:
            decision.setdefault("memory_alerts", []).extend(memory_alerts)

        if isinstance(task, dict):
            task["manager_acceptance"] = decision.get("acceptance_report")
            task["status"] = "accepted" if action in ("dispatch", "complete") else "revision_required"
            task["accepted_at"] = now_iso() if task["status"] == "accepted" else None
            self._replace_task(state, task)
            self._set_plan_task_status(str(task.get("task_id") or ""), task["status"])
            state["execution_plan"] = read_json(self.plan_path, default={})
            if task["status"] == "accepted" and task.get("artifact_path"):
                state.setdefault("accepted_artifacts", []).append({
                    "task_id": task.get("task_id"),
                    "agent_id": task.get("agent_id"),
                    "artifact_path": task.get("artifact_path"),
                })

        if action in ("dispatch", "revise"):
            # -- check if we should pause for human review --
            if action == "dispatch" and _should_pause(
                state.get("run_mode"), str(task.get("agent_id") or "")
            ):
                state["current_actor"] = "human"
                state["human_gate"] = "worker_result"
                state["pending_decision"] = decision
                state["status"] = "awaiting_intermediate_review"
                self._save_state(state)
                return self._human_gate_result(state)
            return self._dispatch(
                state,
                decision["task_packet"],
                reason=f"Manager acceptance action={action}",
            )
        state["current_actor"] = "human"
        state["pending_decision"] = decision
        state["human_gate"] = "final" if action == "complete" else "decision"
        state["status"] = "awaiting_final_approval" if action == "complete" else "awaiting_human_decision"
        self._save_state(state)
        return self._human_gate_result(state)

    def _dispatch(
        self,
        state: dict[str, Any],
        packet: dict[str, Any],
        *,
        reason: str,
    ) -> dict[str, Any]:
        task = self.workers.create_task(
            packet,
            state.get("report_charter") or read_json(self.charter_path, default={}),
            self.raw_brief_path,
        )
        state.setdefault("tasks", []).append(task)
        self._set_plan_task_status(str(task.get("task_id") or ""), "dispatched", task)
        state["execution_plan"] = read_json(self.plan_path, default={})
        state["current_task"] = task
        state["current_actor"] = "worker"
        state["manager_step"] = "idle"
        state["status"] = "running"
        state["worker_result"] = None
        state["last_event"] = "dispatch"
        self._save_state(state)
        self._append_decision(
            "dispatch",
            reason,
            {"task_id": task.get("task_id"), "agent_id": task.get("agent_id")},
        )
        instruction = self.workers.prepare(Path(task["task_dir"]))
        state = self._load_state()
        worker_state = read_json(
            Path(task["task_dir"]) / "run_state.json", default={}
        )
        task.update({
            "selected_capabilities": worker_state.get("selected_capabilities", []),
            "capability_fingerprint": worker_state.get("skill_fingerprint", ""),
            "prompt_budget": worker_state.get("skill_budget", {}),
            "context_mode": worker_state.get("context_mode", ""),
        })
        self._replace_task(state, task)
        state["current_task"] = task
        state["last_instruction"] = instruction
        self._save_state(state)
        has_spawn = bool(instruction.get("spawn"))
        return {
            "actor": "worker",
            "step": "dispatch",
            "task": task,
            "instruction": instruction,
            "next_action": "host_spawn_then_submit" if has_spawn else "host_write_output_then_report_submit",
        }

    def _manager_context(self, state: dict[str, Any]) -> dict[str, Any]:
        phase = str(state.get("manager_phase") or "planning")
        feedback = state.get("human_feedback", [])
        event = state.get("last_event") or (
            "start" if phase == "planning" else "worker_completed"
        )
        raw_brief = read_json(self.raw_brief_path, default={})
        charter = state.get("report_charter") or read_json(
            self.charter_path, default={}
        )
        profile_source = charter or raw_brief
        profile = normalize_report_profile(
            profile_source, root=self.root, strict=False
        ).to_dict()
        registry = CapabilityRegistry(self.root)
        return {
            "schema": "manager_context.v1",
            "phase": phase,
            "event": event,
            "run_id": state.get("run_id"),
            "raw_brief": raw_brief,
            "report_charter": charter,
            "report_profile": profile,
            "capability_registry": {
                "runtime": registry.runtime,
                "dimensions": registry.config.get("dimensions", {}),
                "atomic_capability_count": len(registry.inventory()),
            },
            "recommended_routes": self._recommended_routes(
                profile.get("report_type", "deep_dive")
            ),
            "compiled_manifests": [
                {
                    "task_id": task.get("task_id"),
                    "agent_id": task.get("agent_id"),
                    "selected_capabilities": task.get("selected_capabilities", []),
                    "fingerprint": task.get("capability_fingerprint", ""),
                    "prompt_budget": task.get("prompt_budget", {}),
                    "context_mode": task.get("context_mode", ""),
                }
                for task in state.get("tasks", [])
                if task.get("selected_capabilities")
            ],
            "execution_plan": read_json(
                self.plan_path, default=state.get("execution_plan") or {}
            ),
            "task_statuses": state.get("tasks", []),
            "current_task": state.get("current_task") or {},
            "worker_result": state.get("worker_result") or {},
            "human_feedback": feedback[-5:],
            "previous_manager_decision": state.get("previous_pending_decision") or {},
            "artifact_catalog": self._artifact_catalog(state),
            "manager_memory": self.agent.memory.generation_guidance(
                MANAGER_MEMORY_DIMENSIONS, limit=6
            ),
            "available_workers": self.workers.capabilities(),
        }

    @staticmethod
    def _recommended_routes(report_type: str) -> dict[str, Any]:
        routes = {
            "deep_dive": {
                "default": [
                    "argument_synthesis",
                    "storyline_design",
                    "page_filling",
                    "format",
                    "qa_preparation",
                    "speaker_script",
                ],
                "optional": [],
            },
            "business_progress": {
                "default": [
                    "argument_synthesis",
                    "storyline_design",
                    "page_filling",
                    "format",
                ],
                "optional": ["qa_preparation", "speaker_script"],
            },
            "quick_sync": {
                "default": [
                    "argument_synthesis",
                    "storyline_design",
                    "page_filling",
                    "format",
                ],
                "optional": [],
                "skip_by_default": ["qa_preparation", "speaker_script"],
            },
        }
        return routes.get(report_type, routes["deep_dive"])

    @staticmethod
    def _profile_inheritance(
        charter: dict[str, Any], artifact: dict[str, Any]
    ) -> dict[str, Any]:
        aliases = {"format": "output_format"}
        mismatches = []
        inherited = []
        for artifact_key, charter_key in aliases.items():
            expected = charter.get(charter_key)
            actual = artifact.get(artifact_key) or artifact.get(charter_key)
            if actual in (None, ""):
                continue
            if actual == expected:
                inherited.append(charter_key)
            else:
                mismatches.append(
                    {
                        "field": charter_key,
                        "expected": expected,
                        "actual": actual,
                    }
                )
        for key in ("audience", "report_type"):
            expected = charter.get(key)
            actual = artifact.get(key)
            if actual in (None, ""):
                continue
            if actual == expected:
                inherited.append(key)
            else:
                mismatches.append(
                    {"field": key, "expected": expected, "actual": actual}
                )
        return {
            "passed": not mismatches,
            "inherited_fields": inherited,
            "mismatches": mismatches,
        }

    def _artifact_catalog(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        raw_brief = read_json(self.raw_brief_path, default={})
        catalog = [{
            "kind": "raw_brief",
            "path": str(self.raw_brief_path),
            "schema": raw_brief.get("schema", "") if isinstance(raw_brief, dict) else "",
            "size_bytes": self.raw_brief_path.stat().st_size
            if self.raw_brief_path.exists()
            else 0,
        }]
        for task in state.get("tasks", []):
            if task.get("artifact_path"):
                artifact_path = Path(str(task["artifact_path"]))
                artifact = read_json(artifact_path, default={})
                catalog.append({
                    "kind": "worker_artifact",
                    "task_id": task.get("task_id"),
                    "agent_id": task.get("agent_id"),
                    "status": task.get("status"),
                    "path": str(artifact_path),
                    "schema": artifact.get("schema", "")
                    if isinstance(artifact, dict)
                    else "",
                    "size_bytes": artifact_path.stat().st_size
                    if artifact_path.exists()
                    else 0,
                })
        return catalog

    @staticmethod
    def _format_brief_confirmation(
        brief: dict[str, Any], selected_workers: list[str]
    ) -> str:
        """Build a structured Markdown brief confirmation for the user.

        The host agent simply echo this string to the user verbatim.
        Structured so the user can scan it in one glance and confirm
        accuracy, missing info, or run_mode preference.
        """
        topic = str(brief.get("topic", "（未指定）"))
        audience = str(brief.get("audience", "（未指定）"))
        decision_goal = str(brief.get("decision_goal", "（未指定）"))
        report_type = str(brief.get("report_type", "deep_dive"))
        output_format = str(brief.get("output_format", "ppt"))
        constraints = brief.get("constraints") or []
        page_limit = next(
            (c for c in constraints if "页" in str(c)), ""
        )
        materials = brief.get("materials") or []

        # ---- Worker pipeline label ----
        worker_labels = {
            "argument_synthesis": "核心论点提炼",
            "storyline_design": "故事线设计",
            "page_filling": "草稿填充",
            "format": "材料可视化",
            "qa_preparation": "QA 梳理",
            "speaker_script": "逐字稿生成",
        }
        pipeline = " → ".join(
            f"`{w}` {worker_labels.get(w, w)}" for w in selected_workers
        )

        lines = [
            "## Brief 确认",
            "",
            "| 项目 | 内容 |",
            "|------|------|",
            f"| **汇报主题** | {topic} |",
            f"| **汇报对象** | {audience} |",
            f"| **决策目标** | {decision_goal} |",
            f"| **报告类型** | {report_type} |",
            f"| **输出格式** | {output_format} |",
        ]
        if page_limit:
            lines.append(f"| **页数约束** | {page_limit} |")

        lines.append("")
        lines.append(f"**选定的 Worker 管线**（{len(selected_workers)} 个环节）：")
        lines.append(pipeline)

        if materials:
            lines.append("")
            lines.append(f"**挂载素材**（{len(materials)} 份）：")
            for i, m in enumerate(materials, 1):
                if isinstance(m, dict):
                    name = m.get("claim") or m.get("path") or m.get("file") or str(m)
                else:
                    name = str(m)
                lines.append(f"{i}. {name}")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("请通过下方选项确认 Brief 信息并选择运行模式。")

        return "\n".join(lines)

    def _human_gate_result(self, state: dict[str, Any]) -> dict[str, Any]:
        decision = state.get("pending_decision") or {}
        gate = state.get("human_gate")

        present_to_user = decision.get("user_message") or {
            "brief": "请确认以下 brief 信息是否完整、准确。可补充 topic、audience、output_format，并选择 run_mode（full_auto 一次性跑完 / step_by_step 每步确认）。",
            "plan": "请确认 Manager 的任务定义和执行计划。",
            "worker_result": "当前步骤已完成，请查看中间产物。如需继续，确认后进入下一步。",
            "final": "所有任务已完成，请确认最终交付物。",
            "decision": "请确认 Manager 的决策。",
        }.get(gate, "请确认。")

        result: dict[str, Any] = {
            "actor": "human",
            "step": "manager_gate",
            "gate": gate,
            "status": state.get("status"),
            "present_to_user": present_to_user,
            "run_mode": state.get("run_mode"),
        }

        if gate == "brief":
            result["brief"] = decision.get("brief", {})
            result["missing_fields"] = decision.get("missing_fields", [])
            result["available_workers"] = decision.get("available_workers", [])
            result["selected_workers"] = decision.get("selected_workers", [])
            result["run_mode_options"] = {
                "full_auto": "全程自动，不中断",
                "step_by_step": "每个 Worker 完成后暂停确认",
                "custom": "指定暂停的 Worker 列表，如 [\"argument_synthesis\", \"format\"]",
            }
            result["next_action"] = "human_feedback"
            # Structured questions for host AskUserQuestion
            result["questions"] = [
                {
                    "header": "Brief确认",
                    "question": "Brief 信息是否准确？有无需要补充或修改的地方？",
                    "multiSelect": False,
                    "options": [
                        {"label": "准确，继续", "description": "信息完整，直接进入 Manager 规划阶段"},
                        {"label": "需要修改", "description": "稍后通过 report feedback 提交修改意见"},
                    ],
                },
                {
                    "header": "运行模式",
                    "question": "选择运行模式",
                    "multiSelect": False,
                    "options": [
                        {"label": "full_auto", "description": "全程自动，一口气跑完，不中断"},
                        {"label": "step_by_step", "description": "每个 Worker 完成后暂停，逐环节确认"},
                        {"label": "custom", "description": "只在指定环节暂停，如 [\"argument_synthesis\", \"format\"]"},
                    ],
                },
            ]

        elif gate == "plan":
            result["report_charter"] = state.get("report_charter")
            result["execution_plan"] = state.get("execution_plan")
            result["next_action"] = "report_approve"

        elif gate == "worker_result":
            result["acceptance_report"] = decision.get("acceptance_report")
            result["next_task"] = decision.get("task_packet", {}).get("agent_id")
            result["accepted_artifacts"] = state.get("accepted_artifacts", [])
            result["next_action"] = "report_approve"

        elif gate in ("final", "decision"):
            result["acceptance_report"] = decision.get("acceptance_report")
            result["questions_for_human"] = decision.get("questions_for_human", [])
            result["next_action"] = "report_approve" if gate == "final" else "human_feedback"

        else:
            result["next_action"] = "human_feedback"

        return result

    def _replace_task(self, state: dict[str, Any], current: dict[str, Any]) -> None:
        tasks = state.get("tasks", [])
        for index, item in enumerate(tasks):
            if item.get("task_dir") == current.get("task_dir"):
                tasks[index] = current
                break
        state["tasks"] = tasks
        state["current_task"] = current

    def _set_plan_task_status(
        self,
        task_id: str,
        status: str,
        task_record: Optional[dict[str, Any]] = None,
    ) -> None:
        if not task_id or not self.plan_path.exists():
            return
        plan = read_json(self.plan_path, default={})
        tasks = plan.get("tasks", [])
        found = False
        for task in tasks:
            if task.get("task_id") == task_id:
                task["status"] = status
                found = True
                break
        if not found and task_record:
            packet = task_record.get("packet") or {}
            tasks.append({
                "task_id": task_id,
                "agent_id": task_record.get("agent_id"),
                "objective": packet.get("objective", ""),
                "dependencies": packet.get("dependencies", []),
                "status": status,
            })
        plan["tasks"] = tasks
        plan["updated_at"] = now_iso()
        write_json(self.plan_path, plan)

    def _archive_decision(self, decision: dict[str, Any]) -> None:
        decisions_dir = self.run_dir / "manager" / "decisions"
        decisions_dir.mkdir(parents=True, exist_ok=True)
        count = len(list(decisions_dir.glob("decision_*.json"))) + 1
        write_json(decisions_dir / f"decision_{count:03d}.json", decision)

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            raise StepError(f"Manager run 尚未初始化: {self.state_path}")
        return read_json(self.state_path, default={})

    def _save_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = now_iso()
        write_json(self.state_path, state)

    def _append_decision(self, decision: str, reason: str, payload: dict[str, Any]) -> None:
        append_jsonl(self.decisions_path, {
            "at": now_iso(),
            "run_id": self.run_dir.name,
            "decision": decision,
            "reason": reason,
            "payload": payload,
        })


# Temporary import compatibility for callers of the first Manager MVP.
ManagerController = ManagerOrchestrator


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _should_pause(run_mode: Any, agent_id: str) -> bool:
    """Determine whether to pause for human review after a worker completes.

    - ``"full_auto"`` → never pause
    - ``"step_by_step"`` → pause after every worker
    - ``list[str]`` → pause only if ``agent_id`` is in the list
    """
    if run_mode == "full_auto":
        return False
    if run_mode == "step_by_step":
        return True
    if isinstance(run_mode, list):
        return agent_id in run_mode
    return False
