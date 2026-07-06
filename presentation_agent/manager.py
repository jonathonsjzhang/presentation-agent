from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional

from presentation_agent.capabilities.profile import normalize_report_profile
from presentation_agent.agent_profiles import (
    DEFAULT_CONTRACT_PROFILE,
    load_agent_profile,
)
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

    def __init__(
        self,
        root: Path,
        run_dir: Path,
        data_root: Path,
        contract_profile: Optional[str] = None,
    ) -> None:
        self.root = root
        self.run_dir = run_dir
        self.data_root = data_root
        self.contract_profile = load_agent_profile(
            root, contract_profile
        ).contract_profile
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
        lines.extend(self._required_fields_reference())
        lines.extend([
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
        ])
        lines.extend(self._nested_schema_reference(phase))
        lines.extend([
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

    def _nested_schema_reference(self, phase: str) -> list[str]:
        """Expose the same nested contracts that read_decision validates.

        manager_decision.v1 intentionally keeps nested payloads as generic
        objects because their required shape depends on phase/action. Without
        this reference the model sees a looser contract than the runtime
        applies at commit time.
        """
        names = (
            ("report_charter.v2", "execution_plan.v1", "task_packet.v2")
            if phase == "planning"
            else ("acceptance_report.v1", "task_packet.v2")
        )
        lines = [
            "",
            "## 嵌套对象 Schema（runtime 提交时使用同一份定义校验）",
            "",
            "版本号属于各 artifact 自身，不表示流水线 profile 混用："
            "`report_charter.v2 → analysis.v1 → storyline.v3 → report.v1 "
            "→ formatted_material.v2` 是 v0.3 的固定契约组合。",
        ]
        for name in names:
            lines.extend(
                [
                    "",
                    f"### {name}",
                    "",
                    "```json",
                    json.dumps(self._schema(name), ensure_ascii=False, indent=2),
                    "```",
                ]
            )
        return lines

    def _required_fields_reference(self) -> list[str]:
        return [
            "",
            "## v0.3 planning 契约速查",
            "",
            "- report_charter 使用 report_charter.v2；不得添加 run_mode 或 output_format。",
            "- delivery_targets 固定为 [\"document\"]。",
            "- execution_plan 的主链严格为 analysis → storyline → report → format。",
            "- 首个 task_packet 必须派发 analysis。",
            "- task_packet 使用 task_packet.v2，并继承 recommendation_granularity 与 unsupported_specificity_policy。",
            "- evidence_harvester 是 Analysis 的内部子任务，不得进入 execution_plan。",
            "- 如 material_inventory 中无任何素材 → 使用 ask_human，不要 dispatch。",
            "- PPT、HTML、QA 和逐字稿只允许在 document 完成后的 delivery options gate 追加。",
            "",
            "### acceptance_report 必填字段（acceptance 阶段）",
            "- task_id: 必须等于当前 task_id",
            "- verdict: accept / revise / blocked",
            "- criteria_results: array",
            "- cross_stage_findings: array",
            "- reason: string",
        ]

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
            charter_schema = "report_charter.v2"
            planning_contracts = [("report_charter", charter_schema)]
            if action == "dispatch":
                planning_contracts.extend(
                    [
                        ("execution_plan", "execution_plan.v1"),
                        ("task_packet", "task_packet.v2"),
                    ]
                )
            for key, schema_name in planning_contracts:
                value = decision.get(key)
                if not isinstance(value, dict):
                    errors.append(f"$: planning decision missing object '{key}'")
                else:
                    errors.extend(validate(value, self._schema(schema_name), f"$.{key}"))
            charter = decision.get("report_charter")
            plan = decision.get("execution_plan")
            packet = decision.get("task_packet")
            if action not in ("dispatch", "ask_human"):
                errors.append(
                    "$.action: planning must dispatch a runnable plan or ask_human "
                    "for blocking input"
                )
            if action == "ask_human":
                questions = decision.get("questions_for_human")
                if not isinstance(questions, list) or not any(
                    str(item).strip() for item in questions
                ):
                    errors.append(
                        "$.questions_for_human: planning ask_human requires at "
                        "least one concrete question"
                    )
                if isinstance(charter, dict) and charter.get("material_inventory"):
                    errors.append(
                        "$.action: planning ask_human is reserved for missing "
                        "blocking input; material_inventory is not empty"
                    )
            if action == "dispatch" and (
                isinstance(charter, dict)
                and charter.get("delivery_targets") != ["document"]
            ):
                errors.append(
                    "$.report_charter.delivery_targets: v0.3 initial plan must be "
                    "['document']; PPT/HTML are offered after document delivery"
                )
            if action == "dispatch" and (
                isinstance(charter, dict)
                and isinstance(plan, dict)
                and isinstance(packet, dict)
            ):
                errors.extend(self._v03_plan_errors(charter, plan, packet))
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
                    packet_schema = "task_packet.v2"
                    errors.extend(validate(packet, self._schema(packet_schema), "$.task_packet"))
            if action == "complete" and phase != "acceptance":
                errors.append("$.action: complete is only valid during acceptance")
            state = read_json(
                self.run_dir / "manager_state.json", default={}
            )
            errors.extend(
                self._v03_acceptance_route_errors(
                    action,
                    state,
                    decision.get("task_packet"),
                )
            )

        if errors:
            raise StepError("Manager decision 校验失败:\n- " + "\n- ".join(errors))
        return decision

    @staticmethod
    def _v03_plan_errors(
        charter: dict[str, Any],
        plan: dict[str, Any],
        packet: dict[str, Any],
    ) -> list[str]:
        errors: list[str] = []
        expected = ["analysis", "storyline", "report", "format"]
        actual = [
            str(item.get("agent_id") or "")
            for item in plan.get("tasks", [])
            if isinstance(item, dict)
        ]
        if actual != expected:
            errors.append(
                "$.execution_plan.tasks: v0.3 canonical stages must be exactly "
                f"{expected}, got {actual}"
            )
        if packet.get("agent_id") != "analysis":
            errors.append(
                "$.task_packet.agent_id: v0.3 initial task must be 'analysis'"
            )
        for key in (
            "recommendation_granularity",
            "unsupported_specificity_policy",
        ):
            if packet.get(key) != charter.get(key):
                errors.append(
                    f"$.task_packet.{key}: expected inherited value "
                    f"{charter.get(key)!r}, got {packet.get(key)!r}"
                )
        return errors

    @staticmethod
    def _v03_acceptance_route_errors(
        action: Any,
        state: dict[str, Any],
        packet: Any,
    ) -> list[str]:
        current = state.get("current_task") or {}
        current_agent = str(current.get("agent_id") or "")
        next_agent = (
            str(packet.get("agent_id") or "")
            if isinstance(packet, dict)
            else ""
        )
        expected_next = {
            "analysis": "storyline",
            "storyline": "report",
            "report": "format",
        }
        if action == "dispatch" and current_agent in expected_next:
            expected = expected_next[current_agent]
            if next_agent != expected:
                return [
                    "$.task_packet.agent_id: canonical next worker after "
                    f"{current_agent} is {expected}, got {next_agent!r}"
                ]
        if action == "complete" and current_agent in expected_next:
            return [
                f"$.action: cannot complete v0.3 after {current_agent}; "
                f"must dispatch {expected_next[current_agent]}"
            ]
        if (
            action == "dispatch"
            and current_agent == "format"
            and state.get("last_event") != "human_feedback"
        ):
            return [
                "$.action: initial document Format must complete into the "
                "delivery options gate before optional dispatch"
            ]
        return []

    @staticmethod
    def _policy_inheritance_errors(
        charter: dict[str, Any], packet: dict[str, Any]
    ) -> list[str]:
        errors: list[str] = []
        for key in (
            "recommendation_granularity",
            "unsupported_specificity_policy",
            "evidence_inventory_policy",
        ):
            expected = charter.get(key)
            actual = packet.get(key)
            if actual != expected:
                errors.append(
                    f"$.task_packet.{key}: expected inherited value "
                    f"{expected!r}, got {actual!r}"
                )
        return errors

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
        contract_profile: Optional[str] = None,
    ) -> None:
        self.root = root
        self.run_dir = run_dir
        self.data_root = data_root
        self.spawn_adapter = build_spawn_adapter(root, override=spawn_adapter)
        profile = load_agent_profile(root, contract_profile)
        self.contract_profile = profile.contract_profile
        self.context_assembler = ContextAssembler(
            root, contract_profile=self.contract_profile
        )
        self.specs = dict(profile.specs)

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
        review_subagents_enabled: bool = True,
    ) -> dict[str, Any]:
        agent_id = str(packet.get("agent_id") or "")
        if agent_id not in self.specs:
            raise StepError(
                f"Manager 派发了未知或非活动 Worker: {agent_id}; "
                f"可用 Worker: {sorted(self.specs)}"
            )
        spec = self.specs[agent_id]

        resolved_inputs: list[str] = []
        resolved_artifacts: list[tuple[Path, dict[str, Any]]] = []
        unresolved_inputs: list[str] = []
        for reference in packet.get("input_artifacts", []):
            path = self._resolve_artifact(str(reference))
            if path is None:
                unresolved_inputs.append(str(reference))
                continue
            resolved_inputs.append(str(path))
            data = read_json(path, default={})
            if isinstance(data, dict) and path.resolve() != raw_brief_path.resolve():
                resolved_artifacts.append((path, data))
        if unresolved_inputs:
            raise StepError(
                "Manager task_packet 包含无法解析的 input_artifacts: "
                + ", ".join(unresolved_inputs)
            )
        if self.contract_profile == "v0_3":
            required_schema = {
                "storyline": "analysis.v1",
                "report": "storyline.v3",
                "format": "report.v1",
                "qa_preparation": "formatted_material.v2",
                "speaker_script": "formatted_material.v2",
            }.get(agent_id)
            available_schemas = {
                str(data.get("schema") or "")
                for _, data in resolved_artifacts
                if isinstance(data, dict)
            }
            if required_schema and required_schema not in available_schemas:
                raise StepError(
                    f"v0.3 Worker {agent_id} 缺少必需上游 {required_schema}; "
                    f"已解析 schemas={sorted(available_schemas)}"
                )

        task_id = self._safe_id(str(packet.get("task_id") or f"task-{agent_id}"))
        task_dir = self._unique_task_dir(task_id, agent_id)
        task_dir.mkdir(parents=True, exist_ok=False)
        (task_dir / "handoff").mkdir(parents=True, exist_ok=True)

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
                "input_readiness": worker_input.get("input_readiness", {}),
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
            "contract_profile": self.contract_profile,
            "review_subagents_enabled": review_subagents_enabled,
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
            self.root,
            task_dir,
            data_root=self.data_root,
            contract_profile=self.contract_profile,
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
        request_task_dir = (
            Path(str(instruction["subtask_dir"]))
            if instruction.get("subtask") and instruction.get("subtask_dir")
            else task_dir
        )
        agent_id = str(
            instruction.get("agent_id")
            or run_state.get("agent_id")
            or ""
        )
        step = str(instruction.get("step") or "")
        role = "reviewer" if step.startswith("review") else "worker"
        return SpawnRequest(
            task_dir=request_task_dir,
            agent_id=agent_id,
            role=role,
            instruction_path=Path(instruction.get("instruction_path") or ""),
            output_path=Path(instruction.get("output_path") or ""),
            input_path=Path(
                str(instruction.get("input_path") or request_task_dir / "input.json")
            ),
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
        contract_profile: Optional[str] = None,
    ) -> None:
        self.root = root
        self.run_dir = run_dir
        self.data_root = data_root or (root / "data")
        self.state_path = run_dir / "manager_state.json"
        self.plan_path = run_dir / "manager_plan.json"
        self.charter_path = run_dir / "report_charter.json"
        self.decisions_path = run_dir / "manager_decisions.jsonl"
        self.raw_brief_path = run_dir / "raw_brief.json"
        persisted_state = read_json(self.state_path, default={}) if self.state_path.exists() else {}
        requested_profile = contract_profile or persisted_state.get(
            "contract_profile"
        )
        if requested_profile is None and persisted_state:
            requested_profile = DEFAULT_CONTRACT_PROFILE
        self.contract_profile = load_agent_profile(
            root, requested_profile
        ).contract_profile
        self.agent = ManagerAgentRuntime(
            root, run_dir, self.data_root, contract_profile=self.contract_profile
        )
        persisted_adapter = None
        if self.state_path.exists():
            persisted_adapter = read_json(self.state_path, default={}).get("spawn_adapter")
        self.workers = WorkerExecutor(
            root,
            run_dir,
            self.data_root,
            spawn_adapter=spawn_adapter or persisted_adapter,
            contract_profile=self.contract_profile,
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
            "contract_profile": self.contract_profile,
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
            "review_mode": "independent",
            "review_subagents_enabled": True,
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
            available_workers = ["analysis", "storyline", "report", "format"]
            selected_workers = brief.get("selected_workers")
            if not selected_workers:
                selected_workers = available_workers
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
            runner = StepRunner(
                self.root,
                task_dir,
                data_root=self.data_root,
                contract_profile=self.contract_profile,
            )
            status = runner.status()

            # Evidence Harvester subtask routing: when Analysis is in
            # awaiting_evidence_output, the actual instruction files live under
            # the Evidence subtask's own StepRunner at subtasks/evidence_harvester/.
            # Switch to it so instruction_path/output_path resolve correctly.
            if status.get("current_step") == "awaiting_evidence_output":
                evidence_dir = task_dir / "subtasks" / "evidence_harvester"
                if evidence_dir.exists():
                    evidence_runner = StepRunner(
                        self.root,
                        evidence_dir,
                        data_root=self.data_root,
                        contract_profile=self.contract_profile,
                    )
                    status = evidence_runner.status()
                    task_dir = evidence_dir

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
            worker_result = state.get("worker_result") or {}
            artifact = worker_result.get("artifact") or {}
            revision_requests = artifact.get("upstream_revision_requests", [])
            blocking_requests = [
                item
                for item in revision_requests
                if isinstance(item, dict)
                and item.get("blocking_level") == "blocking"
            ]
            # Not every blocking request should actually block the pipeline.
            # Storyline may have narrowed scope to work around a gap: if the
            # affected findings are all in editorial_decisions with disposition
            # "omitted" or "appendix", the gap has been handled and the request
            # is no longer blocking.
            editorial_decisions = artifact.get("editorial_decisions", [])
            main_story_fids: set[str] = set()
            for ed in editorial_decisions:
                if isinstance(ed, dict) and ed.get("disposition") == "main_story":
                    fid = ed.get("finding_id")
                    if isinstance(fid, str):
                        main_story_fids.add(fid)
            truly_blocking = [
                req
                for req in blocking_requests
                if any(
                    fid in main_story_fids
                    for fid in (req.get("finding_refs") or [])
                )
            ] or (
                # If there is no editorial_decisions at all (edge case:
                # zero-finding analysis), *all* blocking requests are real.
                blocking_requests
                if not editorial_decisions
                else []
            )
            cross_issues = (
                worker_result.get("cross_stage_review", {}).get("issues", [])
            )
            blocking_cross_issues = [
                item
                for item in cross_issues
                if isinstance(item, dict) and item.get("severity") == "P0"
            ]
            if action in ("dispatch", "complete") and (
                truly_blocking or blocking_cross_issues
            ):
                raise StepError(
                    "当前 Worker 存在真正阻断性的上游返工请求或跨阶段 P0 "
                    "（已排除通过 editorial_decisions 缩窄范围的 gap），"
                    "Manager 必须 action=revise 并派发相应上游 Worker"
                )
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

    def approve(
        self,
        *,
        run_mode: Optional[str] = None,
        review_mode: Optional[str] = None,
        delivery_option: Optional[str] = None,
    ) -> dict[str, Any]:
        state = self._load_state()
        if state.get("current_actor") != "human":
            raise StepError("当前没有等待人工确认的 Manager gate")
        gate = state.get("human_gate")
        decision = state.get("pending_decision") or {}
        if gate == "brief":
            brief_data = decision.get("brief", {})
            # run_mode: "full_auto" | "step_by_step" | ["agent_id", ...]
            raw_run_mode = (
                run_mode
                or decision.get("run_mode")
                or brief_data.get("run_mode")
            )
            if isinstance(raw_run_mode, list):
                state["run_mode"] = raw_run_mode  # custom pause points
                state["custom_pause_agents"] = raw_run_mode
            elif raw_run_mode == "full_auto":
                state["run_mode"] = "full_auto"
            else:
                state["run_mode"] = "step_by_step"  # default
            selected_review_mode = (
                review_mode
                or decision.get("review_mode")
                or brief_data.get("review_mode")
                or "independent"
            )
            if selected_review_mode not in ("independent", "schema_only"):
                raise StepError(f"未知 review_mode: {selected_review_mode}")
            state["review_mode"] = selected_review_mode
            state["review_subagents_enabled"] = (
                selected_review_mode == "independent"
            )
            state["human_gate"] = None
            state["pending_decision"] = None
            state["current_actor"] = "manager"
            state["manager_phase"] = "planning"
            state["manager_step"] = "init"
            state["last_event"] = "brief_confirmed"
            state["status"] = "planning"
            self._save_state(state)
            self._append_decision("brief_confirmed",
                "用户确认了 brief，"
                f"run_mode={state['run_mode']}，review_mode={selected_review_mode}",
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
        if gate == "delivery_options":
            if delivery_option and delivery_option != "skip":
                return self.record_human_feedback(
                    f"用户选择追加交付：{delivery_option}"
                )
            state["status"] = "completed"
            state["current_actor"] = "human"
            state["human_gate"] = None
            state["pending_decision"] = None
            state["completed_at"] = now_iso()
            self._save_state(state)
            self._append_decision(
                "complete",
                "Document delivery completed; user skipped optional translations and extensions",
                {},
            )
            return {
                "actor": "manager",
                "step": "completed",
                "status": "completed",
                "run_dir": str(self.run_dir),
                "accepted_artifacts": state.get("accepted_artifacts", []),
                "present_to_user": "文档交付已完成；本次未继续转译 PPT/HTML，也未生成 QA list 或逐字稿。",
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
            "delivery_options": "acceptance",
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
                self.root,
                task_dir,
                data_root=self.data_root,
                contract_profile=self.contract_profile,
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
        # Guard: spawn is meaningless without resolved instruction/output paths
        inst_path = str(instruction.get("instruction_path") or "")
        out_path = str(instruction.get("output_path") or "")
        if not inst_path or not out_path:
            return
        previous = (
            read_json(self.state_path, default={}).get("last_instruction")
            if self.state_path.exists()
            else None
        )
        if isinstance(previous, dict):
            previous_spawn = previous.get("spawn")
            if (
                previous.get("step") == instruction.get("step")
                and previous.get("instruction_path")
                == instruction.get("instruction_path")
                and previous.get("output_path") == instruction.get("output_path")
                and isinstance(previous_spawn, dict)
                and previous_spawn.get("status") == "dispatched"
                and previous_spawn.get("adapter") == adapter.kind
            ):
                instruction["spawn"] = previous_spawn
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

    def record_spawn_completed(self) -> dict[str, Any]:
        """Record an auditable host attestation before non-inline Worker commit."""

        state = self._load_state()
        if state.get("current_actor") != "worker":
            raise StepError("当前没有等待提交的 Worker sub-agent")
        if state.get("spawn_adapter") == "inline":
            return {"required": False, "adapter": "inline"}

        instruction = state.get("last_instruction")
        if not isinstance(instruction, dict):
            raise StepError("缺少当前 Worker instruction，无法确认 sub-agent 执行")
        spawn = instruction.get("spawn")
        if not isinstance(spawn, dict) or spawn.get("status") != "dispatched":
            raise StepError("当前 instruction 没有已派发的 spawn request")
        detail = spawn.get("detail")
        request_path = Path(str((detail or {}).get("spawn_request") or ""))
        output_path = Path(str(instruction.get("output_path") or ""))
        if not request_path.is_file():
            raise StepError(f"spawn request 不存在: {request_path}")
        if not output_path.is_file():
            raise StepError(f"sub-agent 输出不存在: {output_path}")
        if output_path.stat().st_mtime_ns < request_path.stat().st_mtime_ns:
            raise StepError(
                "sub-agent 输出早于当前 spawn request，疑似复用了旧输出"
            )
        output_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
        task_dir = self.current_worker_dir(state)
        if task_dir is None:
            raise StepError("Manager state 缺少当前 Worker task_dir")
        worker_state = read_json(task_dir / "run_state.json", default={})
        round_index = int(worker_state.get("round_index", 0))

        receipt = {
            "schema": "spawn_receipt.v1",
            "adapter": spawn.get("adapter"),
            "role": spawn.get("role"),
            "spawn_request": str(request_path),
            "instruction_path": instruction.get("instruction_path"),
            "output_path": str(output_path),
            "output_sha256": output_sha256,
            "round_index": round_index,
            "attested_at": now_iso(),
            "attestation": "host_confirms_native_subagent_completed",
        }
        receipt_path = request_path.with_name(
            f"spawn_receipt_{output_path.stem}_round_{round_index}.json"
        )
        write_json(receipt_path, receipt)
        state["last_spawn_receipt"] = str(receipt_path)
        self._save_state(state)
        self._append_decision(
            "spawn_completed",
            "Host attested native sub-agent completion",
            receipt,
        )
        return receipt

    def _commit_plan(self, state: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        charter = decision["report_charter"]
        write_json(self.charter_path, charter)
        global_state = dict(charter.get("global_state_seed") or {})
        global_state.update({
            "report_charter": charter,
            "updated_at": now_iso(),
        })
        write_json(self.run_dir / "state.json", global_state)
        state["report_charter"] = charter
        if decision.get("action") == "ask_human":
            state["current_actor"] = "human"
            state["human_gate"] = "decision"
            state["pending_decision"] = decision
            state["status"] = "awaiting_human_decision"
            self._save_state(state)
            return self._human_gate_result(state)

        plan = decision["execution_plan"]
        write_json(self.plan_path, plan)
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
        if (
            action == "complete"
            and self.contract_profile == "v0_3"
            and isinstance(task, dict)
            and task.get("agent_id") == "format"
        ):
            state["human_gate"] = "delivery_options"
            state["status"] = "awaiting_delivery_option_selection"
            decision["user_message"] = (
                "文档已完成。是否继续转译为 PPT 或 HTML，或生成 QA list / 逐字稿？"
                "直接批准表示不追加其他产物并完成本次任务。"
            )
        else:
            state["human_gate"] = "final" if action == "complete" else "decision"
            state["status"] = (
                "awaiting_final_approval"
                if action == "complete"
                else "awaiting_human_decision"
            )
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
            review_subagents_enabled=bool(
                state.get("review_subagents_enabled", True)
            ),
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
        if self.contract_profile == "v0_3":
            profile["version"] = "v0_3"
            profile["delivery_target"] = profile["output_format"]
        registry = CapabilityRegistry(self.root)
        return {
            "schema": "manager_context.v1",
            "contract_profile": self.contract_profile,
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
                profile.get("report_type", "deep_dive"),
                contract_profile=self.contract_profile,
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
    def _recommended_routes(
        report_type: str,
        contract_profile: str,
    ) -> dict[str, Any]:
        return {
            "default": ["analysis", "storyline", "report", "format"],
            "optional_after_document": [
                "format(ppt)",
                "format(html)",
                "qa_preparation",
                "speaker_script",
            ],
            "internal_subagents": {"analysis": ["evidence_harvester"]},
        }

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
        delivery_targets = brief.get("delivery_targets") or []
        constraints = brief.get("constraints") or []
        page_limit = next(
            (c for c in constraints if "页" in str(c)), ""
        )
        materials = brief.get("materials") or []

        # ---- Worker pipeline label ----
        worker_labels = {
            "format": "可视化",
            "qa_preparation": "QA 梳理",
            "speaker_script": "逐字稿生成",
            "analysis": "分析",
            "storyline": "故事线",
            "report": "报告产出",
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
            f"| **输出格式** | {', '.join(delivery_targets) if delivery_targets else output_format} |",
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
        lines.append("请通过下方选项确认 Brief，并选择运行模式和 Review 模式。")

        return "\n".join(lines)

    def _human_gate_result(self, state: dict[str, Any]) -> dict[str, Any]:
        decision = state.get("pending_decision") or {}
        gate = state.get("human_gate")

        present_to_user = decision.get("user_message") or {
            "brief": "请确认以下 brief 信息是否完整、准确。可补充 topic、audience、output_format，并选择 run_mode（full_auto 一次性跑完 / step_by_step 每步确认）。",
            "plan": "请确认 Manager 的任务定义和执行计划。",
            "worker_result": "当前步骤已完成，请查看中间产物。如需继续，确认后进入下一步。",
            "final": "所有任务已完成，请确认最终交付物。",
            "delivery_options": "文档已完成。请选择是否转译 PPT/HTML 或生成 QA list/逐字稿；直接批准表示结束。",
            "decision": "请确认 Manager 的决策。",
        }.get(gate, "请确认。")

        result: dict[str, Any] = {
            "actor": "human",
            "step": "manager_gate",
            "gate": gate,
            "status": state.get("status"),
            "present_to_user": present_to_user,
            "run_mode": state.get("run_mode"),
            "review_mode": state.get("review_mode"),
        }

        if gate == "brief":
            result["brief"] = decision.get("brief", {})
            result["missing_fields"] = decision.get("missing_fields", [])
            result["available_workers"] = decision.get("available_workers", [])
            result["selected_workers"] = decision.get("selected_workers", [])
            result["run_mode_options"] = {
                "full_auto": "全程自动，不中断",
                "step_by_step": "每个 Worker 完成后暂停确认",
                "custom": "指定暂停的 Worker 列表，如 [\"analysis\", \"format\"]",
            }
            result["review_mode_options"] = {
                "independent": "独立 Review sub-agent（质量优先）",
                "schema_only": "仅 Schema/P0 门禁（速度优先）",
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
                        {"label": "custom", "description": "只在指定环节暂停，如 [\"analysis\", \"format\"]"},
                    ],
                },
                {
                    "header": "Review模式",
                    "question": "是否启用独立 Review sub-agent？",
                    "multiSelect": False,
                    "options": [
                        {
                            "label": "启用（推荐）",
                            "description": "启用独立 Reviewer，质量更稳但耗时更长",
                        },
                        {
                            "label": "不启用（快速）",
                            "description": "跳过 LLM Reviewer，仅保留确定性 Schema/P0 门禁",
                        },
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

        elif gate == "delivery_options":
            result["accepted_artifacts"] = state.get("accepted_artifacts", [])
            raw_brief = read_json(self.raw_brief_path, default={})
            result["requested_followup_targets"] = (
                raw_brief.get("requested_followup_targets", [])
                if isinstance(raw_brief, dict)
                else []
            )
            result["delivery_options"] = [
                "format:ppt",
                "format:html",
                "qa_preparation",
                "speaker_script",
                "skip",
            ]
            result["questions"] = [
                {
                    "header": "追加交付",
                    "question": "文档已完成，是否追加其他交付物？",
                    "multiSelect": False,
                    "options": [
                        {
                            "label": "PPT",
                            "description": "基于已批准报告转译 PPT",
                            "value": "format:ppt",
                        },
                        {
                            "label": "HTML",
                            "description": "基于已批准报告转译 HTML",
                            "value": "format:html",
                        },
                        {
                            "label": "Q&A",
                            "description": "生成管理层追问与回答策略",
                            "value": "qa_preparation",
                        },
                        {
                            "label": "逐字稿",
                            "description": "生成汇报讲稿与时间节奏",
                            "value": "speaker_script",
                        },
                        {
                            "label": "结束",
                            "description": "不追加其他交付物",
                            "value": "skip",
                        },
                    ],
                }
            ]
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
