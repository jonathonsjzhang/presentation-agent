from __future__ import annotations

import copy
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
from presentation_agent.page_budget import derive_delivery_budget
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

DEFAULT_CHECKPOINT_PAUSE_AGENTS = ["analysis", "storyline"]


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
            "Context 中的大型 brief、Evidence Catalog 与 Worker artifact 以摘要和文件路径引用。",
            "planning 默认使用摘要；只有某个任务定义事实缺失时才按字段读取 raw_brief_path/catalog_ref。",
            "acceptance 必须读取 worker_result.artifact_path 后再判断。不要根据 preview 补写事实，",
            "也不要把完整文件复制进输出或宿主对话。",
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
            "phase、schema、task_id 和固定执行链由 runtime 管理。不要输出 Markdown、解释或思考过程。",
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
            ("report_charter.v2", "task_packet.v2")
            if phase == "planning"
            else ("acceptance_report.v1", "task_packet.v2")
        )
        lines = [
            "",
            "## 嵌套对象 Schema（runtime 提交时使用同一份定义校验）",
            "",
            "这些 schema 只描述本轮需要作出的专业判断；固定流程、ID 和状态由 runtime 生成。",
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
            "- report_charter 只定义任务，不重复固定流程、质量检查或运行状态。",
            "- runtime 固定执行 analysis → storyline → report → qa_preparation → format，不输出 execution_plan。",
            "- 首个 task_packet 派发 analysis，只写目标、输入引用和必要返工意见。",
            "- evidence_harvester 在 Brief 确认前作为 run-level 输入处理任务运行；Analysis 复用其 Catalog。",
            "- 如 material_inventory 中无任何素材 → 使用 ask_human，不要 dispatch。",
            "- high_confidence_evidence 表示用户填写的重要/高可信论据，只影响分析优先级，不提升证据因果强度。",
            "- PPT、HTML 只允许在默认五阶段完成后的 delivery options gate 追加。",
            "",
            "### acceptance_report（acceptance 阶段）",
            "- acceptance 只需输出 action + acceptance_report；v0.3 runtime 自动生成/规范化 dispatch 或 revise 的 task_packet。",
            "- 不要引用 handoff/output_*.json；正式上游路径由 runtime 绑定到当前 task 的 artifact.json。",
            "- verdict: accept / revise / blocked",
            "- reason: 一句话说明决定",
            "- revision_requirements: 仅在确需返工时填写",
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
        action = decision.get("action")
        if phase == "planning":
            charter_schema = "report_charter.v2"
            planning_contracts = [("report_charter", charter_schema)]
            if action == "dispatch":
                planning_contracts.append(("task_packet", "task_packet.v2"))
            for key, schema_name in planning_contracts:
                value = decision.get(key)
                if not isinstance(value, dict):
                    errors.append(f"$: planning decision missing object '{key}'")
                else:
                    errors.extend(validate(value, self._schema(schema_name), f"$.{key}"))
            charter = decision.get("report_charter")
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
                and isinstance(packet, dict)
            ):
                errors.extend(self._v03_plan_errors(charter, packet))
        else:
            state = read_json(
                self.run_dir / "manager_state.json", default={}
            )
            if self.contract_profile == "v0_3":
                self._normalize_v03_acceptance_packet(decision, state)
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
            errors.extend(
                self._v03_acceptance_route_errors(
                    action,
                    state,
                    decision.get("task_packet"),
                )
            )

        if errors:
            raise StepError("Manager decision 校验失败:\n- " + "\n- ".join(errors))
        decision["phase"] = phase
        decision["schema"] = "manager_decision.v1"
        if phase == "acceptance":
            # task_id is runtime bookkeeping, not a judgement the Manager model
            # should have to reproduce. Always bind acceptance to the task that
            # is currently under review so stale IDs cannot deadlock the loop.
            current_task_id = (
                read_json(self.run_dir / "manager_state.json", default={})
                .get("current_task", {})
                .get("task_id")
            )
            report = decision.get("acceptance_report")
            if isinstance(report, dict) and current_task_id:
                submitted_task_id = report.get("task_id")
                if submitted_task_id not in (None, "", current_task_id):
                    decision.setdefault("runtime_normalizations", []).append(
                        {
                            "field": "acceptance_report.task_id",
                            "submitted": submitted_task_id,
                            "effective": current_task_id,
                            "reason": "acceptance is bound to current runtime task",
                        }
                    )
                report["task_id"] = current_task_id
        packet = decision.get("task_packet")
        if isinstance(packet, dict):
            packet.setdefault("task_id", f"{phase}-{packet.get('agent_id', 'worker')}")
        if phase == "planning" and "execution_plan" in decision:
            # The production chain is a runtime invariant. Older Manager
            # prompts sometimes still return a bespoke execution_plan; ignore
            # it so model output cannot change the chain or reintroduce a plan
            # approval step.
            decision.pop("execution_plan", None)
            decision.setdefault("runtime_normalizations", []).append(
                {
                    "field": "execution_plan",
                    "submitted": "manager-provided",
                    "effective": "runtime-canonical-chain",
                    "reason": "fixed execution chain is owned by runtime",
                }
            )
        return decision

    def _normalize_v03_acceptance_packet(
        self,
        decision: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        """Keep fixed-chain routing and artifact bookkeeping out of model output.

        The Manager still decides whether to accept, revise, or stop.  For v0.3,
        however, the runtime already owns the worker order and knows the formal
        artifact registered for the task under review.  Reconstructing those
        fields here prevents a missing task packet or a handoff/output_gen.json
        reference from stranding an otherwise valid acceptance decision.
        """

        action = decision.get("action")
        if action not in ("dispatch", "revise"):
            return
        current = state.get("current_task") or {}
        current_agent = str(current.get("agent_id") or "")
        expected_next = {
            "analysis": "storyline",
            "storyline": "report",
            "report": "qa_preparation",
            "qa_preparation": "format",
        }
        upstream_requests: list[dict[str, Any]] = []
        if action == "revise":
            artifact = (state.get("worker_result") or {}).get("artifact") or {}
            upstream_requests = [
                item
                for item in artifact.get("upstream_revision_requests") or []
                if isinstance(item, dict)
                and item.get("blocking_level") == "blocking"
            ]
        upstream_targets = [
            "analysis"
            if item.get("target_agent") == "evidence_harvester"
            else str(item.get("target_agent") or "")
            for item in upstream_requests
        ]
        upstream_target = next(
            (
                agent_id
                for agent_id in ("analysis", "storyline", "report", "qa_preparation")
                if agent_id in upstream_targets
            ),
            "",
        )
        target_agent = (
            expected_next.get(current_agent, "")
            if action == "dispatch"
            else upstream_target or current_agent
        )
        if not target_agent:
            return

        submitted = decision.get("task_packet")
        submitted_packet = submitted if isinstance(submitted, dict) else {}
        if action == "revise":
            upstream_task = next(
                (
                    item
                    for item in reversed(state.get("tasks") or [])
                    if isinstance(item, dict)
                    and item.get("agent_id") == target_agent
                    and isinstance(item.get("packet"), dict)
                ),
                None,
            )
            current_packet = (
                upstream_task.get("packet")
                if isinstance(upstream_task, dict)
                else current.get("packet")
            )
            packet = copy.deepcopy(
                current_packet if isinstance(current_packet, dict) else {}
            )
            packet.update(copy.deepcopy(submitted_packet))
        else:
            packet = copy.deepcopy(submitted_packet)

        artifact_path = str(
            current.get("artifact_path")
            or (state.get("worker_result") or {}).get("artifact_path")
            or ""
        ).strip()
        effective_inputs = list(packet.get("input_artifacts") or [])
        if action == "dispatch" and artifact_path:
            effective_inputs = [artifact_path]

        objectives = {
            "storyline": "基于已批准的 Analysis 产物收敛唯一故事线。",
            "report": "基于已批准的 Storyline 写作完整报告。",
            "qa_preparation": "基于完整报告追加听众深度追问清单。",
            "format": "基于追加追问后的完整报告生成正式文档。",
        }
        packet["agent_id"] = target_agent
        packet["input_artifacts"] = effective_inputs
        packet.setdefault(
            "objective",
            objectives.get(target_agent, f"修订当前 {target_agent} 产物。"),
        )
        packet.setdefault("task_id", f"acceptance-{target_agent}")
        if action == "revise":
            report = decision.get("acceptance_report") or {}
            requirements = report.get("revision_requirements") or []
            if requirements:
                packet["revision_feedback"] = [
                    str(item) for item in requirements if str(item).strip()
                ]
            elif "revision_feedback" not in submitted_packet:
                # The current acceptance decision owns the revision round.
                # Never silently carry feedback from an earlier packet.
                packet.pop("revision_feedback", None)
        if action == "revise" and upstream_requests:
            reasons = [
                str(item.get("reason") or "可视化论据不完整")
                for item in upstream_requests
                if (
                    "analysis"
                    if item.get("target_agent") == "evidence_harvester"
                    else item.get("target_agent")
                )
                == target_agent
            ]
            if reasons:
                packet["revision_feedback"] = reasons
        decision["task_packet"] = packet

        changes = []
        if not isinstance(submitted, dict):
            changes.append("missing task_packet synthesized by runtime")
        if submitted_packet.get("agent_id") != target_agent:
            changes.append(
                f"agent_id normalized to canonical {target_agent}"
            )
        if action == "dispatch" and artifact_path and list(
            submitted_packet.get("input_artifacts") or []
        ) != [artifact_path]:
            changes.append("input_artifacts bound to current artifact.json")
        if changes:
            decision.setdefault("runtime_normalizations", []).append(
                {
                    "field": "task_packet",
                    "submitted": submitted if isinstance(submitted, dict) else None,
                    "effective": copy.deepcopy(packet),
                    "reason": "; ".join(changes),
                }
            )

    @staticmethod
    def _v03_plan_errors(
        charter: dict[str, Any],
        plan_or_packet: dict[str, Any],
        packet: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        # Accept the former (charter, execution_plan, packet) call shape while
        # deliberately ignoring the fixed execution plan.
        packet = packet or plan_or_packet
        errors: list[str] = []
        if packet.get("agent_id") != "analysis":
            errors.append(
                "$.task_packet.agent_id: v0.3 initial task must be 'analysis'"
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
            "report": "qa_preparation",
            "qa_preparation": "format",
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
                "qa_preparation": "report.v1",
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
            "manager_run_dir": str(self.run_dir),
            "global_state_path": str(self.run_dir / "state.json"),
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
        instruction.setdefault("input_path", str(task_dir / "input.json"))

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
            # Older Manager outputs sometimes referenced the worker's transient
            # handoff JSON.  Prefer the formal artifact registered at the task
            # root when it is available.
            if path.parent.name == "handoff" and path.name.startswith("output_"):
                artifact_path = path.parent.parent / "artifact.json"
                if artifact_path.is_file():
                    return artifact_path.resolve()
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
            "manager_phase": "evidence_intake",
            "manager_step": "init",
            "last_event": "start",
            "spawn_adapter": self.workers.spawn_adapter.kind,
            "human_gate": None,
            "current_task": None,
            "tasks": [],
            "accepted_artifacts": [],
            "project_state": {},
            "brief_interaction_stage": "collection_and_confirmation",
            "brief_explicitly_confirmed": False,
            "run_mode": None,  # set during brief confirmation; default pauses after analysis/storyline
            "review_mode": "schema_only",
            "review_subagents_enabled": False,
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

        if phase == "evidence_intake" and actor == "manager":
            evidence_instruction = self._prepare_evidence_intake(state)
            if evidence_instruction is not None:
                return evidence_instruction
            state = self._load_state()
            actor = state.get("current_actor")
            phase = str(state.get("manager_phase") or "brief_confirmation")

        # --- brief confirmation: show the brief and ask user to confirm ---
        if phase == "brief_confirmation":
            brief = read_json(self.raw_brief_path, default={})
            brief_stage = str(
                state.get("brief_interaction_stage")
                or "collection_and_confirmation"
            )
            confirmation_ready = bool(
                state.get("brief_explicitly_confirmed")
            )
            if brief_stage == "collection_and_confirmation":
                questions = [
                    *self._brief_collection_questions(brief, always_ask=True),
                    self._brief_confirmation_question(),
                ]
            elif confirmation_ready:
                questions = []
            else:
                questions = [self._brief_confirmation_question()]
            missing = [item["header"] for item in questions]
            user_message = self._format_brief_confirmation(
                brief,
                confirmation_ready=confirmation_ready,
            )
            state["current_actor"] = "human"
            state["human_gate"] = "brief"
            state["pending_decision"] = {
                "brief": brief,
                "missing_fields": missing,
                "brief_stage": brief_stage,
                "confirmation_ready": confirmation_ready,
                "questions": questions,
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
                    "input_path": str(task_dir / "input.json"),
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
        state_before_commit = copy.deepcopy(state)
        plan_before_commit = (
            read_json(self.plan_path, default={})
            if self.plan_path.is_file()
            else None
        )
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
            delivery_budget = (
                state.get("project_state", {}).get("delivery_budget", {})
                if isinstance(state.get("project_state"), dict)
                else {}
            )
            budget_required = bool(delivery_budget.get("body_page_limit"))
            budget_audit = self._body_budget_audit(worker_result)
            requires_budget_pass = (
                budget_required
                and (
                    action == "dispatch"
                    and current_task.get("agent_id") == "report"
                    or action == "complete"
                    and current_task.get("agent_id") == "format"
                )
            )
            # For Format completion, report the renderer/preflight failure
            # before interpreting the resulting absence of a page audit as a
            # page-budget failure. This keeps the corrective route attached to
            # the actual cause (for example missing visual evidence data).
            if (
                action == "complete"
                and current_task.get("agent_id") == "format"
                and not self._format_delivery_succeeded(worker_result)
            ):
                render_result = (
                    worker_result.get("render_result")
                    or artifact.get("render_result")
                    or {}
                )
                render_detail = ""
                if isinstance(render_result, dict):
                    render_detail = str(render_result.get("detail") or "").strip()
                if not render_detail:
                    deliverables = (artifact.get("artifact_manifest") or {}).get(
                        "deliverables"
                    ) or []
                    render_detail = next(
                        (
                            str(item.get("blocking_reason") or "").strip()
                            for item in deliverables
                            if isinstance(item, dict)
                            and str(item.get("blocking_reason") or "").strip()
                        ),
                        "",
                    )
                detail_suffix = (
                    f" renderer detail: {render_detail}" if render_detail else ""
                )
                raise StepError(
                    "Format 不能 complete：runtime renderer 或渲染前置检查未通过。"
                    f"请修复真实渲染错误后重试。{detail_suffix}"
                )
            if requires_budget_pass and budget_audit.get("passed") is not True:
                detail = str(
                    budget_audit.get("detail")
                    or "runtime 未取得可验证的正文页数结果"
                )
                raise StepError(
                    f"{current_task.get('agent_id')} 不能{action}：正文页数硬约束未通过。"
                    f"{detail}。请提交 revise，并依据 body_budget_audit 压缩当前环节。"
                )
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
            # These are acceptance signals, not runtime state invariants. The
            # Manager may knowingly accept a narrowed claim or a presentation
            # warning; rejecting that decision here can strand a successfully
            # rendered deliverable behind a stale cross-stage observation.
            acceptance_warnings = [*truly_blocking, *blocking_cross_issues]
            if acceptance_warnings:
                decision.setdefault("runtime_acceptance_warnings", []).extend(
                    acceptance_warnings
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

        try:
            if phase == "planning":
                return self._commit_plan(state, decision)
            return self._commit_acceptance(state, decision)
        except Exception as exc:
            # Applying a valid Manager decision can still fail at dispatch
            # (for example, because an artifact reference cannot be resolved).
            # Restore the pre-submit state so the same instruction can be
            # corrected and submitted again without an out-of-band state hack.
            restored = copy.deepcopy(state_before_commit)
            restored["current_actor"] = "manager"
            restored["manager_step"] = "awaiting_output"
            restored["last_event"] = "manager_commit_failed"
            restored["last_error"] = {
                "at": now_iso(),
                "phase": phase,
                "message": str(exc),
                "recovery": "rewrite current Manager output, then report next / report submit",
            }
            self._save_state(restored)
            if isinstance(plan_before_commit, dict):
                write_json(self.plan_path, plan_before_commit)
            self._append_decision(
                "manager_commit_failed",
                "Manager decision application failed and state was rolled back",
                {"phase": phase, "error": str(exc)},
            )
            raise

    def record_worker_completed(self, result: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state()
        task = state.get("current_task")
        if state.get("current_actor") != "worker" or not isinstance(task, dict):
            raise StepError("当前没有可交给 Manager 验收的 Worker")
        if task.get("agent_id") == "evidence_harvester" and task.get(
            "task_kind"
        ) == "evidence_intake":
            return self._record_evidence_intake_completed(state, result)
        task["status"] = "worker_completed"
        task["artifact_path"] = result.get("artifact_path")
        task["review_summary"] = result.get("review_summary")
        task["render_result"] = result.get("render_result")
        task["rendered_files"] = list(result.get("rendered_files") or [])
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
            "render_result": result.get("render_result"),
            "rendered_files": list(result.get("rendered_files") or []),
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
            confirmation_ready = bool(decision.get("confirmation_ready"))
            if not confirmation_ready:
                questions = decision.get("questions")
                fields = "、".join(
                    str(item.get("header") or "").strip()
                    for item in questions
                    if isinstance(item, dict) and item.get("header")
                ) if isinstance(questions, list) else ""
                raise StepError(
                    "Brief 尚未获得用户明确确认，请先完成结构化提问"
                    + (f"：{fields}" if fields else "")
                )
            # run_mode: "full_auto" | "step_by_step" | ["agent_id", ...]
            raw_run_mode = (
                run_mode
                or decision.get("run_mode")
                or brief_data.get("run_mode")
            )
            if isinstance(raw_run_mode, list):
                state["run_mode"] = raw_run_mode  # custom pause points
                state["custom_pause_agents"] = raw_run_mode
            elif raw_run_mode == "step_by_step":
                state["run_mode"] = "step_by_step"
            elif raw_run_mode == "full_auto":
                state["run_mode"] = "full_auto"
            else:
                state["run_mode"] = list(DEFAULT_CHECKPOINT_PAUSE_AGENTS)
                state["custom_pause_agents"] = list(DEFAULT_CHECKPOINT_PAUSE_AGENTS)
            selected_review_mode = (
                review_mode
                or decision.get("review_mode")
                or brief_data.get("review_mode")
                or "schema_only"
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
            # Backward compatibility for runs created before planning started
            # dispatching the first Worker automatically.
            packet = decision.get("task_packet")
            if not isinstance(packet, dict):
                raise StepError("已批准计划，但 Manager decision 中没有首个 task_packet")
            state["human_gate"] = None
            state["pending_decision"] = None
            return self._dispatch(state, packet, reason="human approved Manager plan")
        if gate == "worker_result":
            # In step_by_step mode: user reviewed intermediate output, proceed to next worker
            if self._is_analysis_thesis_gate(state):
                selection = self._analysis_thesis_selection(state)
                if not selection:
                    state["analysis_feedback_error"] = (
                        "请在确认框填写一个 Analysis 主论点组编号；如果都不合适，"
                        "请在同一输入框填写“都不好”及原因或直接写出修改意见。"
                    )
                    self._save_state(state)
                    return self._human_gate_result(state)
                packet = decision.get("task_packet")
                if isinstance(packet, dict):
                    packet["selected_analysis_thesis"] = selection
                    objective = str(packet.get("objective") or "").strip()
                    suffix = (
                        f"沿用用户确认的 Analysis 主论点组 {selection.get('option_id', '')}。"
                    )
                    packet["objective"] = (
                        f"{objective}；{suffix}" if objective else suffix
                    )
            elif self._is_storyline_confirmation_gate(state):
                state.setdefault("project_state", {})["storyline_confirmation"] = {
                    "status": "approved",
                    "confirmed_at": now_iso(),
                }
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
                "rendered_files": self._accepted_rendered_files(state),
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
                "Default worker chain completed; user skipped optional translations",
                {},
            )
            return {
                "actor": "manager",
                "step": "completed",
                "status": "completed",
                "run_dir": str(self.run_dir),
                "accepted_artifacts": state.get("accepted_artifacts", []),
                "rendered_files": self._accepted_rendered_files(state),
                "present_to_user": "默认五阶段已完成；本次未继续转译 PPT/HTML。",
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
        if gate == "worker_result" and self._is_analysis_thesis_gate(state):
            return self._record_analysis_thesis_feedback(state, feedback)
        if gate == "worker_result" and self._is_storyline_confirmation_gate(state):
            return self._record_storyline_confirmation_feedback(state, feedback)
        if gate == "brief":
            return self._record_brief_feedback(state, feedback)
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

    def status_summary(self) -> dict[str, Any]:
        """Return the control-plane facts hosts need without artifact snapshots."""

        state = self._load_state()
        current = state.get("current_task") or {}
        if not isinstance(current, dict):
            current = {}
        return {
            "run_id": state.get("run_id"),
            "status": state.get("status"),
            "current_actor": state.get("current_actor"),
            "manager_phase": state.get("manager_phase"),
            "manager_step": state.get("manager_step"),
            "human_gate": state.get("human_gate"),
            "last_event": state.get("last_event"),
            "spawn_adapter": state.get("spawn_adapter"),
            "current_task": {
                key: current.get(key)
                for key in (
                    "task_id",
                    "agent_id",
                    "status",
                    "task_dir",
                    "input_path",
                    "artifact_path",
                )
                if current.get(key) not in (None, "")
            },
            "state_path": str(self.state_path),
            "plan_path": str(self.plan_path),
            "charter_path": str(self.charter_path),
            "last_error": state.get("last_error"),
        }

    def current_worker_dir(self, state: Optional[dict[str, Any]] = None) -> Optional[Path]:
        current = (state or self._load_state()).get("current_task")
        if not isinstance(current, dict) or not current.get("task_dir"):
            return None
        return Path(str(current["task_dir"]))

    def _prepare_evidence_intake(
        self, state: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Run Evidence once at run scope before the user confirms the Brief."""

        brief = read_json(self.raw_brief_path, default={})
        if not isinstance(brief, dict):
            brief = {}
        if isinstance(brief.get("evidence_catalog"), dict) and self._evidence_catalog_reusable(
            brief
        ):
            state["manager_phase"] = "brief_confirmation"
            state["evidence_intake"] = {
                "status": "reused",
                "catalog_ref": brief.get("evidence_catalog_ref", "raw_brief:evidence_catalog"),
            }
            self._save_state(state)
            return None
        if isinstance(brief.get("evidence_catalog"), dict):
            brief.pop("evidence_catalog", None)
            brief.pop("evidence_catalog_ref", None)
            brief.pop("evidence_index", None)
            brief.pop("source_manifest", None)
            brief.pop("material_resolution", None)
            write_json(self.raw_brief_path, brief)
            state["evidence_intake"] = {
                "status": "invalidated",
                "reason": "source_manifest_changed",
            }

        raw_materials = self._evidence_intake_materials(brief)
        if not raw_materials:
            state["manager_phase"] = "brief_confirmation"
            state["evidence_intake"] = {
                "status": "not_required",
                "reason": "no_file_or_raw_material_inputs",
            }
            self._save_state(state)
            return None

        from presentation_agent.spawn import prepare_evidence_intake

        prepared = prepare_evidence_intake(
            root=self.root,
            run_dir=self.run_dir,
            data_root=self.data_root,
            raw_materials=raw_materials,
            brief=brief,
        )
        evidence_dir = Path(str(prepared["task_dir"]))
        task = {
            "task_id": "evidence-intake",
            "agent_id": "evidence_harvester",
            "agent_name": "证据完整盘点",
            "task_kind": "evidence_intake",
            "task_dir": str(evidence_dir),
            "input_path": str(prepared["input_path"]),
            "status": "dispatched",
            "created_at": now_iso(),
        }
        state["current_task"] = task
        state["current_actor"] = "worker"
        state["status"] = "running_evidence_intake"
        state["evidence_intake"] = {
            "status": "running",
            "task_dir": str(evidence_dir),
        }
        instruction = dict(prepared)
        instruction["actor"] = "worker"
        instruction["evidence_intake"] = True
        self._save_state(state)
        self._annotate_spawn(evidence_dir, instruction)
        instruction["next_action"] = (
            "host_spawn_then_submit"
            if instruction.get("spawn")
            else "host_write_output_then_report_submit"
        )
        state["last_instruction"] = instruction
        self._save_state(state)
        self._append_decision(
            "evidence_intake_dispatched",
            "Run-level Evidence Harvester dispatched before Brief confirmation",
            {"task_dir": str(evidence_dir)},
        )
        return instruction

    @staticmethod
    def _evidence_intake_materials(brief: dict[str, Any]) -> list[Any]:
        raw = brief.get("raw_materials")
        if isinstance(raw, list) and raw:
            return raw
        materials = brief.get("materials")
        if isinstance(materials, list):
            path_keys = {"path", "source_path", "file_path", "filepath", "artifact_path"}
            raw_keys = {"text", "source_units", "rows", "raw_content"}
            candidates = [
                item
                for item in materials
                if isinstance(item, dict)
                and (path_keys.intersection(item) or raw_keys.intersection(item))
            ]
            if candidates:
                return candidates
        if isinstance(brief.get("source_units"), list) and brief["source_units"]:
            return [{"material_type": "source_units", "source_units": brief["source_units"]}]
        if isinstance(brief.get("rows"), list) and brief["rows"]:
            return [{"material_type": "table", "rows": brief["rows"]}]
        return []

    @staticmethod
    def _evidence_catalog_reusable(brief: dict[str, Any]) -> bool:
        catalog = brief.get("evidence_catalog")
        if not isinstance(catalog, dict):
            return False
        manifest = catalog.get("source_manifest") or brief.get("source_manifest")
        if not isinstance(manifest, list) or not manifest:
            return True
        for record in manifest:
            if not isinstance(record, dict):
                continue
            path = Path(str(record.get("path") or ""))
            if not path.is_file():
                return False
            stat = path.stat()
            if record.get("size_bytes") not in (None, stat.st_size):
                return False
            if record.get("modified_at_ns") not in (None, stat.st_mtime_ns):
                return False
            expected_hash = str(record.get("content_hash") or "")
            if expected_hash and ManagerOrchestrator._source_file_sha256(path) != expected_hash:
                return False
        return True

    @staticmethod
    def _source_file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _record_evidence_intake_completed(
        self, state: dict[str, Any], result: dict[str, Any]
    ) -> dict[str, Any]:
        artifact_path = Path(str(result.get("artifact_path") or ""))
        if not artifact_path.is_file():
            raise StepError(f"Evidence Intake artifact 不存在: {artifact_path}")
        catalog = read_json(artifact_path, default={})
        if not isinstance(catalog, dict) or not isinstance(catalog.get("items"), list):
            raise StepError("Evidence Intake 必须产出含 items array 的 Evidence Catalog")

        evidence_dir = artifact_path.parent
        evidence_input = read_json(evidence_dir / "input.json", default={})
        for key in (
            "evidence_index",
            "source_manifest",
            "material_resolution",
        ):
            value = evidence_input.get(key)
            if value not in (None, "", [], {}):
                catalog[key] = value
        manifest = catalog.get("source_manifest") or []
        catalog["catalog_fingerprint"] = hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        catalog["generated_at"] = now_iso()
        canonical_path = evidence_dir / "evidence_catalog.json"
        write_json(canonical_path, catalog)

        brief = read_json(self.raw_brief_path, default={})
        if not isinstance(brief, dict):
            brief = {}
        brief["evidence_catalog"] = catalog
        brief["evidence_catalog_ref"] = str(canonical_path)
        for key in ("evidence_index", "source_manifest", "material_resolution"):
            if catalog.get(key) not in (None, "", [], {}):
                brief[key] = catalog[key]
        write_json(self.raw_brief_path, brief)

        state["evidence_intake"] = {
            "status": "completed",
            "catalog_ref": str(canonical_path),
            "catalog_fingerprint": catalog["catalog_fingerprint"],
            "item_count": len(catalog["items"]),
            "unresolved_count": len(catalog.get("unresolved") or []),
        }
        state["current_task"] = None
        state["current_actor"] = "manager"
        state["manager_phase"] = "brief_confirmation"
        state["manager_step"] = "init"
        state["status"] = "running"
        state["last_event"] = "evidence_intake_completed"
        state["last_instruction"] = None
        self._save_state(state)
        self._append_decision(
            "evidence_intake_completed",
            "Evidence Catalog generated and injected into the Brief",
            state["evidence_intake"],
        )
        return self.prepare()

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
        # Extra guard: if the output already exists and has meaningful
        # content, don't re-spawn — the sub-agent already completed.
        output_path = Path(out_path)
        if output_path.exists() and output_path.stat().st_size > 0:
            try:
                out_data = read_json(output_path, default={})
                if isinstance(out_data, dict) and any(
                    isinstance(v, (list, dict)) and len(v) > 0
                    for v in out_data.values()
                    if v is not None
                ):
                    instruction["spawn"] = {
                        "adapter": adapter.kind,
                        "role": "worker",
                        "status": "completed",
                        "detail": "output exists — skipping re-spawn",
                    }
                    return
            except Exception:
                pass
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
        delivery_budget = derive_delivery_budget(charter)
        global_state = dict(charter.get("global_state_seed") or {})
        global_state.update({
            "report_charter": charter,
            "updated_at": now_iso(),
        })
        if delivery_budget:
            global_state["delivery_budget"] = delivery_budget
        write_json(self.run_dir / "state.json", global_state)
        state["report_charter"] = charter
        if delivery_budget:
            state.setdefault("project_state", {})["delivery_budget"] = delivery_budget
        if decision.get("action") == "ask_human":
            state["current_actor"] = "human"
            state["human_gate"] = "decision"
            state["pending_decision"] = decision
            state["status"] = "awaiting_human_decision"
            self._save_state(state)
            return self._human_gate_result(state)

        plan = {
            "plan_id": "runtime-canonical-chain",
            "tasks": [
                {
                    "task_id": f"runtime-{index}-{agent_id}",
                    "agent_id": agent_id,
                    "objective": f"complete {agent_id}",
                    "dependencies": (
                        [] if index == 1 else [f"runtime-{index - 1}-{previous}"]
                    ),
                    "status": "planned",
                }
                for index, (agent_id, previous) in enumerate(
                    (
                        ("analysis", ""),
                        ("storyline", "analysis"),
                        ("report", "storyline"),
                        ("qa_preparation", "report"),
                        ("format", "qa_preparation"),
                    ),
                    1,
                )
            ],
            "human_gates": ["delivery_options"],
            "completion_criteria": ["format delivered"],
            "generated_by": "runtime",
        }
        decision["execution_plan"] = plan
        write_json(self.plan_path, plan)
        state["execution_plan"] = plan
        state["human_gate"] = None
        state["pending_decision"] = None
        return self._dispatch(
            state,
            decision["task_packet"],
            reason="Manager planning completed; automatically dispatched first Worker",
        )

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
            if task.get("agent_id") == "format":
                worker_result = state.get("worker_result") or {}
                artifact = worker_result.get("artifact") or {}
                task["render_result"] = (
                    worker_result.get("render_result")
                    or artifact.get("render_result")
                    or task.get("render_result")
                )
                task["rendered_files"] = self._format_rendered_files(worker_result)
            task["manager_acceptance"] = decision.get("acceptance_report")
            task["status"] = "accepted" if action in ("dispatch", "complete") else "revision_required"
            task["accepted_at"] = now_iso() if task["status"] == "accepted" else None
            self._replace_task(state, task)
            self._set_plan_task_status(str(task.get("task_id") or ""), task["status"])
            state["execution_plan"] = read_json(self.plan_path, default={})
            if task["status"] == "accepted" and task.get("artifact_path"):
                state["accepted_artifacts"] = [
                    item
                    for item in state.get("accepted_artifacts", [])
                    if item.get("task_id") != task.get("task_id")
                    and item.get("task_dir") != task.get("task_dir")
                ]
                state.setdefault("accepted_artifacts", []).append({
                    "task_id": task.get("task_id"),
                    "agent_id": task.get("agent_id"),
                    "artifact_path": task.get("artifact_path"),
                    "task_dir": task.get("task_dir"),
                    "render_result": task.get("render_result"),
                    "rendered_files": list(task.get("rendered_files") or []),
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
            and self._is_default_document_format_task(task)
        ):
            state["human_gate"] = "delivery_options"
            state["status"] = "awaiting_delivery_option_selection"
            decision["user_message"] = (
                "默认五阶段已完成。是否继续转译为 PPT 或 HTML？"
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

    @staticmethod
    def _is_default_document_format_task(task: dict[str, Any]) -> bool:
        """Return true for the main-chain document Format task.

        Format also handles optional PPT/HTML translations after the delivery
        options gate. Those follow-up tasks should complete the run instead of
        reopening the same gate.
        """
        if task.get("agent_id") != "format":
            return False
        context = task.get("context") if isinstance(task.get("context"), dict) else {}
        target = task.get("delivery_target") or context.get("delivery_target") or "document"
        return str(target) == "document"

    @staticmethod
    def _format_delivery_succeeded(worker_result: dict[str, Any]) -> bool:
        artifact = worker_result.get("artifact") or {}
        render_result = worker_result.get("render_result") or artifact.get("render_result")
        if not isinstance(render_result, dict) or render_result.get("status") != "rendered":
            return False
        return bool(ManagerOrchestrator._format_rendered_files(worker_result))

    @staticmethod
    def _body_budget_audit(worker_result: dict[str, Any]) -> dict[str, Any]:
        artifact = worker_result.get("artifact") or {}
        direct = artifact.get("body_budget_audit")
        if isinstance(direct, dict):
            return direct
        render_result = worker_result.get("render_result") or artifact.get(
            "render_result"
        ) or {}
        if not isinstance(render_result, dict):
            return {}
        metrics = render_result.get("metrics") or {}
        audit = metrics.get("body_budget_audit") if isinstance(metrics, dict) else None
        return audit if isinstance(audit, dict) else {}

    @staticmethod
    def _format_rendered_files(worker_result: dict[str, Any]) -> list[str]:
        artifact = worker_result.get("artifact") or {}
        render_result = worker_result.get("render_result") or artifact.get("render_result") or {}
        candidates = list(worker_result.get("rendered_files") or [])
        output_path = str(render_result.get("output_path") or "")
        if output_path:
            candidates.append(output_path)
        artifact_path = Path(str(worker_result.get("artifact_path") or ""))
        base_dir = artifact_path.parent if artifact_path.name else None
        files: list[str] = []
        for value in candidates:
            path = Path(str(value))
            if not path.is_absolute() and base_dir is not None:
                path = base_dir / path
            if path.is_file() and str(path) not in files:
                files.append(str(path))
        return files

    @staticmethod
    def _accepted_rendered_files(state: dict[str, Any]) -> list[str]:
        files: list[str] = []
        for item in state.get("accepted_artifacts", []):
            if item.get("agent_id") != "format":
                continue
            for path in item.get("rendered_files") or []:
                value = str(path)
                if value and value not in files:
                    files.append(value)
        return files

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
            "raw_brief": self._manager_brief_projection(raw_brief),
            "raw_brief_path": str(self.raw_brief_path),
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
            "worker_result": self._manager_worker_result_projection(
                state.get("worker_result") or {}
            ),
            "human_feedback": feedback[-5:],
            "previous_manager_decision": self._manager_decision_projection(
                state.get("previous_pending_decision") or {}
            ),
            "artifact_catalog": self._artifact_catalog(state),
            "manager_memory": self.agent.memory.generation_guidance(
                MANAGER_MEMORY_DIMENSIONS, limit=6
            ),
            "available_workers": self.workers.capabilities(),
        }

    def _manager_brief_projection(self, brief: dict[str, Any]) -> dict[str, Any]:
        """Keep planning semantic context while moving evidence payloads to refs."""

        projected = {
            key: copy.deepcopy(value)
            for key, value in brief.items()
            if key
            not in {
                "evidence_catalog",
                "evidence_index",
                "evidence_assets",
                "source_manifest",
                "raw_materials",
                "source_units",
                "rows",
                "resolved_materials",
            }
        }
        catalog = brief.get("evidence_catalog")
        if isinstance(catalog, dict):
            items = catalog.get("items") or catalog.get("evidence_items") or []
            sources = catalog.get("source_manifest") or []
            evidence_index = catalog.get("evidence_index") or brief.get(
                "evidence_index"
            ) or []
            projected["evidence_catalog_summary"] = {
                "schema": catalog.get("schema"),
                "catalog_ref": brief.get("evidence_catalog_ref"),
                "catalog_fingerprint": catalog.get("catalog_fingerprint"),
                "item_count": len(items) if isinstance(items, list) else 0,
                "source_count": len(sources) if isinstance(sources, list) else 0,
                "unresolved_count": len(catalog.get("unresolved") or []),
                "material_inventory": [
                    {
                        key: row.get(key)
                        for key in (
                            "id",
                            "material_id",
                            "source_name",
                            "source_type",
                            "summary",
                        )
                        if row.get(key) not in (None, "")
                    }
                    for row in evidence_index[:30]
                    if isinstance(row, dict)
                ],
            }
        return projected

    @staticmethod
    def _manager_worker_result_projection(result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {}
        return {
            key: copy.deepcopy(value)
            for key, value in result.items()
            if key != "artifact" and value not in (None, "", [], {})
        }

    @staticmethod
    def _manager_decision_projection(decision: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(decision, dict):
            return {}
        return {
            key: copy.deepcopy(value)
            for key, value in decision.items()
            if key
            in {
                "action",
                "acceptance_report",
                "task_packet",
                "missing_fields",
                "brief_stage",
                "confirmation_ready",
            }
            and value not in (None, "", [], {})
        }

    @staticmethod
    def _recommended_routes(
        report_type: str,
        contract_profile: str,
    ) -> dict[str, Any]:
        return {
            "default": [
                "analysis",
                "storyline",
                "report",
                "qa_preparation",
                "format",
            ],
            "optional_after_document": [
                "format(ppt)",
                "format(html)",
            ],
            "input_preparation": ["evidence_harvester"],
            "internal_subagents": {
                "analysis": ["evidence_harvester (legacy/direct-run fallback only)"]
            },
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
    def _first_brief_text(brief: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = brief.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @classmethod
    def _brief_collection_questions(
        cls, brief: dict[str, Any], *, always_ask: bool = False
    ) -> list[dict[str, Any]]:
        """Return the three user-owned free-text Brief questions.

        The opening WorkBuddy interaction passes ``always_ask=True`` so
        inferred draft values never suppress explicit user ownership. The
        caller appends Brief confirmation as question four in the same panel.
        """

        questions: list[dict[str, Any]] = []
        if always_ask or not cls._first_brief_text(brief, "research_purpose"):
            questions.append({
                "header": "研究目的",
                "question": "项目研究目的是什么（如为了回答XX问题，或XX研究的延伸）？",
                "inputType": "text",
                "multiSelect": False,
                "options": [],
            })
        if always_ask or not cls._first_brief_text(
            brief,
            "research_direction",
            "hypothesis",
            "hypo",
        ):
            questions.append({
                "header": "当前研究 hypo",
                "question": "当前的研究hypo是什么（如当前结论判断，或预期引导的讨论方向）？",
                "inputType": "text",
                "multiSelect": False,
                "options": [],
            })
        if always_ask or "high_confidence_evidence" not in brief:
            questions.append({
                "header": "高可信论据",
                "question": (
                    "请填写你认为高可信或重要的论据（可写 evidence list 的编号、"
                    "证据名称或原文片段）；如无特别优先项，请填写“无”。"
                ),
                "inputType": "text",
                "multiSelect": False,
                "options": [],
            })
        return questions[:3]

    @staticmethod
    def _brief_confirmation_question() -> dict[str, Any]:
        return {
            "header": "Brief确认",
            "question": "以上完整 Brief 是否准确？",
            "multiSelect": False,
            "options": [
                {
                    "label": "准确，继续",
                    "description": "确认后进入 Manager 规划阶段",
                },
                {
                    "label": "需要修改",
                    "description": "补充修改内容后重新展示完整 Brief",
                },
            ],
        }

    @classmethod
    def _parse_brief_feedback(cls, feedback: str) -> dict[str, Any]:
        """Parse the host's deterministic Brief answer payload.

        The preferred protocol is a JSON object. Labelled text remains
        accepted for compatibility with older host adapters.
        """

        aliases = {
            "research_purpose": "research_purpose",
            "研究目的": "research_purpose",
            "research_direction": "research_direction",
            "hypothesis": "research_direction",
            "hypo": "research_direction",
            "当前研究hypo": "research_direction",
            "当前研究 hypo": "research_direction",
            "高可信论据": "high_confidence_evidence",
            "high_confidence_evidence": "high_confidence_evidence",
            "brief_confirmed": "brief_confirmed",
            "Brief确认": "brief_confirmed",
        }
        allowed_updates = {
            "topic",
            "audience",
            "project_type",
            "report_type",
            "delivery_format",
            "delivery_targets",
            "output_format",
            "report_length",
            "constraints",
            "research_purpose",
            "research_direction",
            "high_confidence_evidence",
            "brief_confirmed",
        }
        try:
            payload = json.loads(feedback)
        except json.JSONDecodeError:
            payload = None

        updates: dict[str, Any] = {}
        if isinstance(payload, dict):
            for key, value in payload.items():
                canonical = aliases.get(str(key))
                if canonical:
                    updates[canonical] = value
            brief_updates = payload.get("brief_updates")
            if isinstance(brief_updates, dict):
                for key, value in brief_updates.items():
                    if str(key) in allowed_updates:
                        updates[str(key)] = value
            return updates

        label_pattern = re.compile(
            r"(?m)^\s*(研究目的|当前研究\s*hypo|高可信论据)\s*[：:]\s*(.+?)\s*$",
            re.IGNORECASE,
        )
        for match in label_pattern.finditer(feedback):
            label = re.sub(r"\s+", " ", match.group(1)).strip()
            canonical = aliases.get(label) or aliases.get(label.replace(" ", ""))
            if canonical:
                updates[canonical] = match.group(2).strip()
        return updates

    def _record_brief_feedback(
        self, state: dict[str, Any], feedback: str
    ) -> dict[str, Any]:
        updates = self._parse_brief_feedback(feedback)
        if not updates:
            state["brief_feedback_error"] = (
                "未识别到可写回 Brief 的字段。请按结构化答案提交研究目的、"
                "当前研究 hypo、高可信论据或 brief_updates。"
            )
            self._save_state(state)
            return self._human_gate_result(state)

        if state.get("brief_interaction_stage") == "collection_and_confirmation":
            required = {
                "research_purpose",
                "research_direction",
                "high_confidence_evidence",
                "brief_confirmed",
            }
            missing = sorted(required - set(updates))
            if missing:
                state["brief_feedback_error"] = (
                    "首次 Brief 交互必须回传四题答案，缺少字段："
                    + "、".join(missing)
                )
                self._save_state(state)
                return self._human_gate_result(state)

        explicit_confirmation = updates.pop("brief_confirmed", None)
        brief = read_json(self.raw_brief_path, default={})
        if not isinstance(brief, dict):
            brief = {}
        for key, value in updates.items():
            if key in {"research_purpose", "research_direction"}:
                text = str(value or "").strip()
                if text:
                    brief[key] = text
            elif key == "high_confidence_evidence":
                if isinstance(value, list):
                    brief[key] = [
                        str(item).strip() for item in value if str(item).strip()
                    ]
                else:
                    text = str(value or "").strip()
                    brief[key] = [] if text in {"无", "没有", "暂无"} else [text]
            else:
                brief[key] = value
        write_json(self.raw_brief_path, brief)

        state.pop("brief_feedback_error", None)
        if explicit_confirmation is not None:
            confirmed = (
                explicit_confirmation
                if isinstance(explicit_confirmation, bool)
                else str(explicit_confirmation).strip().lower()
                in {"true", "yes", "1", "准确", "准确，继续", "继续"}
            )
            state["brief_explicitly_confirmed"] = confirmed
            state["brief_interaction_stage"] = (
                "confirmed" if confirmed else "confirmation"
            )
        elif state.get("brief_interaction_stage") == "collection_and_confirmation":
            state["brief_interaction_stage"] = "confirmation"
        state["current_actor"] = "manager"
        state["manager_phase"] = "brief_confirmation"
        state["manager_step"] = "init"
        state["last_event"] = "brief_fields_updated"
        state["human_gate"] = None
        state["status"] = "running"
        state["previous_pending_decision"] = state.get("pending_decision")
        state["pending_decision"] = None
        self._save_state(state)
        self._append_decision(
            "brief_fields_updated",
            "Brief answers persisted before final confirmation",
            {"updated_fields": sorted(updates)},
        )
        return self.prepare()

    @staticmethod
    def _brief_evidence_options(brief: dict[str, Any]) -> list[dict[str, str]]:
        options: list[dict[str, str]] = []
        seen: set[str] = set()

        def add_option(value: str, label: str, description: str = "") -> None:
            clean_label = str(label or "").strip()
            if not clean_label:
                return
            clean_value = str(value or clean_label).strip()
            key = clean_value or clean_label
            if key in seen:
                return
            seen.add(key)
            option = {
                "label": clean_label[:80],
                "value": clean_value[:120],
                "description": str(description or "用户可填写为高可信论据")[:180],
            }
            options.append(option)

        def evidence_description(item: dict[str, Any]) -> str:
            for key in ("summary", "observation", "so_what", "description"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            evidence = item.get("evidence")
            if isinstance(evidence, list):
                return "；".join(
                    str(part) for part in evidence[:2] if str(part).strip()
                )
            if isinstance(evidence, str):
                return evidence.strip()
            findings = item.get("key_findings")
            if isinstance(findings, list):
                return "；".join(
                    str(part) for part in findings[:2] if str(part).strip()
                )
            return ""

        catalog = brief.get("evidence_catalog")
        catalog_items: list[Any] = []
        if isinstance(catalog, dict):
            raw_items = (
                catalog.get("items")
                or catalog.get("evidence_items")
                or catalog.get("evidence_index")
            )
            if isinstance(raw_items, list):
                catalog_items = raw_items
        for index, item in enumerate(catalog_items, 1):
            if not isinstance(item, dict):
                continue
            evidence_id = str(
                item.get("evidence_id") or item.get("id") or f"EV-{index}"
            )
            label = str(
                item.get("claim")
                or item.get("summary")
                or item.get("content")
                or item.get("source_name")
                or evidence_id
            )
            add_option(evidence_id, label, evidence_description(item))

        evidence_index = brief.get("evidence_index")
        if not catalog_items and isinstance(evidence_index, list):
            for index, item in enumerate(evidence_index, 1):
                if not isinstance(item, dict):
                    continue
                evidence_id = str(
                    item.get("id") or item.get("evidence_id") or f"E{index}"
                )
                label = str(
                    item.get("summary")
                    or item.get("claim")
                    or item.get("source_name")
                    or item.get("material_id")
                    or evidence_id
                )
                add_option(evidence_id, label, evidence_description(item))

        materials = brief.get("materials") or []
        if not catalog_items and isinstance(materials, list):
            for index, material in enumerate(materials, 1):
                if isinstance(material, dict):
                    value = str(
                        material.get("evidence_id")
                        or material.get("material_id")
                        or material.get("id")
                        or f"M{index}"
                    )
                    label = str(
                        material.get("claim")
                        or material.get("summary")
                        or material.get("description")
                        or material.get("path")
                        or material.get("fixture")
                        or material.get("file")
                        or value
                    )
                    add_option(value, label, evidence_description(material))
                else:
                    add_option(f"M{index}", str(material))
        return options

    @staticmethod
    def _display_audience(value: Any) -> str:
        labels = {
            "board": "董事会",
            "exec_office": "总办",
            "strategy_lead": "战略负责人",
            "business_team": "业务负责人",
            "external": "外部听众",
        }
        text = str(value or "exec_office").strip()
        return labels.get(text, text or "总办")

    @staticmethod
    def _display_project_type(brief: dict[str, Any]) -> str:
        raw = str(brief.get("project_type") or "").strip()
        if raw:
            return raw
        report_type = str(brief.get("report_type") or "deep_dive")
        return "梳理类" if report_type == "quick_sync" else "分析类"

    @staticmethod
    def _display_delivery(brief: dict[str, Any]) -> str:
        labels = {"document": "文档", "ppt": "PPT", "html": "HTML"}
        targets = brief.get("requested_delivery_targets") or brief.get(
            "delivery_targets"
        )
        if isinstance(targets, str):
            targets = [targets]
        if isinstance(targets, list) and targets:
            return " / ".join(labels.get(str(item), str(item)) for item in targets)
        raw = str(
            brief.get("delivery_format")
            or brief.get("output_format")
            or "document"
        ).strip()
        return labels.get(raw, raw or "文档")

    @staticmethod
    def _brief_report_length(brief: dict[str, Any]) -> str:
        value = str(brief.get("report_length") or "").strip()
        if value:
            return value
        delivery = ManagerOrchestrator._display_delivery(brief)
        return "10页PPT" if "PPT" in delivery else "3页"

    @staticmethod
    def _format_brief_confirmation(
        brief: dict[str, Any], *, confirmation_ready: bool = False
    ) -> str:
        """Build a structured Markdown brief confirmation for the user.

        The host agent simply echo this string to the user verbatim.
        Structured so the user can scan it in one glance and confirm
        accuracy, missing info, or run_mode preference.
        """
        topic = str(
            brief.get("topic") or "Manager 将根据输入信息和论据总结"
        )
        research_purpose = ManagerOrchestrator._first_brief_text(
            brief, "research_purpose"
        ) or "待用户补充"
        research_direction = ManagerOrchestrator._first_brief_text(
            brief,
            "research_direction",
            "hypothesis",
            "hypo",
        ) or "待用户补充"
        audience = ManagerOrchestrator._display_audience(
            brief.get("audience") or "exec_office"
        )
        project_type = ManagerOrchestrator._display_project_type(brief)
        delivery = ManagerOrchestrator._display_delivery(brief)
        report_length = ManagerOrchestrator._brief_report_length(brief)
        evidence_options = ManagerOrchestrator._brief_evidence_options(brief)
        materials = brief.get("materials") or []

        lines = [
            "## Brief 最终确认" if confirmation_ready else "## Brief 草案",
            "",
            "### 1. 项目需求",
            "",
            "| 项目 | 内容 |",
            "|------|------|",
            f"| **研究目的** | {research_purpose} |",
            f"| **当前研究 hypo** | {research_direction} |",
        ]

        lines.extend([
            "",
            "### 2. 论据可信度分类",
            "",
        ])
        if evidence_options:
            if isinstance(brief.get("evidence_catalog"), dict):
                lines.append(
                    "以下是 Evidence Harvester 从原始材料提取的可追溯论据，请填写你认为高可信的论据编号、名称或原文片段："
                )
            else:
                lines.append(
                    "以下是当前 Brief 已登记的结构化论据，请填写你认为高可信的论据编号、名称或原文片段："
                )
            for index, item in enumerate(evidence_options, 1):
                description = item.get("description", "")
                suffix = f"：{description}" if description else ""
                lines.append(f"{index}. **{item['label']}**{suffix}")
        else:
            lines.append("当前还没有正式提取的可引用论据；如已有材料或证据，请在回复中补充。")

        if "high_confidence_evidence" in brief:
            selected = brief.get("high_confidence_evidence")
            if isinstance(selected, list):
                selected_text = "；".join(
                    str(item) for item in selected if str(item).strip()
                ) or "无特别优先项"
            else:
                selected_text = str(selected or "无特别优先项")
            lines.extend(["", f"**用户标记的高可信论据**：{selected_text}"])

        lines.extend([
            "",
            "### 3-7. 报告设定",
            "",
            "| 项目 | 内容 |",
            "|------|------|",
            f"| **报告主题** | {topic} |",
            f"| **听众** | {audience} |",
            f"| **项目类型** | {project_type} |",
            f"| **交付形式** | {delivery} |",
            f"| **报告篇幅** | {report_length} |",
            "| **agent执行流程** | analysis（分析） → storyline（故事线） → report（报告产出） → qa_preparation（追问清单） → format（可视化排版） |",
            "| **是否发起review sub_agent** | 否（更高效） |",
        ])

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
        if confirmation_ready:
            lines.append(
                "请核对以上完整 Brief。选择“准确，继续”后才会进入规划；"
                "选择“需要修改”则写回修改内容并再次展示完整 Brief。"
                "默认会在 analysis 和 storyline 完成后各暂停确认一次，之后自动走到最终报告。"
            )
        else:
            lines.append(
                "请在同一个结构化提问面板中完成研究目的、当前研究 hypo、"
                "高可信论据三项填空，并确认其余 Brief 设定是否准确。"
            )

        return "\n".join(lines)

    def _human_gate_result(self, state: dict[str, Any]) -> dict[str, Any]:
        decision = state.get("pending_decision") or {}
        gate = state.get("human_gate")

        if gate == "brief" and not decision.get("user_message"):
            present_to_user = self._format_brief_confirmation(
                decision.get("brief", {}) if isinstance(decision.get("brief"), dict) else {},
                confirmation_ready=bool(decision.get("confirmation_ready")),
            )
        else:
            present_to_user = decision.get("user_message") or {
            "brief": "请确认 brief 信息是否完整、准确。请补充研究目的、当前研究 hypo，并填写高可信论据；可调整报告主题、听众、项目类型、交付形式和报告篇幅。",
            "plan": "请确认 Manager 的任务定义和执行计划。",
            "worker_result": "当前步骤已完成，请查看中间产物。如需继续，确认后进入下一步。",
            "final": "所有任务已完成，请确认最终交付物。",
            "delivery_options": "默认五阶段已完成。请选择是否转译 PPT/HTML；直接批准表示结束。",
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
            brief_payload = decision.get("brief", {})
            if not isinstance(brief_payload, dict):
                brief_payload = {}
            result["brief"] = brief_payload
            result["missing_fields"] = decision.get("missing_fields", [])
            result["brief_stage"] = decision.get("brief_stage", "collection")
            result["confirmation_ready"] = bool(
                decision.get("confirmation_ready")
            )
            evidence_options = self._brief_evidence_options(brief_payload)
            result["evidence_options"] = evidence_options
            result["brief_defaults"] = {
                "report_topic": self._first_brief_text(
                    brief_payload, "topic",
                )
                or "Manager 根据输入信息和论据总结",
                "report_length": self._brief_report_length(brief_payload),
                "audience": self._display_audience(
                    brief_payload.get("audience", "exec_office")
                ),
                "project_type": self._display_project_type(brief_payload),
                "delivery": self._display_delivery(brief_payload),
            }
            decision_questions = decision.get("questions")
            if not isinstance(decision_questions, list):
                decision_questions = []
            result["questions"] = decision_questions
            if result["confirmation_ready"]:
                result["next_action"] = "report_approve_without_asking_again"
            else:
                result["next_action"] = (
                    "host_call_AskUserQuestion_then_report_feedback"
                )
            if state.get("brief_feedback_error"):
                result["feedback_error"] = state["brief_feedback_error"]

        elif gate == "plan":
            result["report_charter"] = state.get("report_charter")
            result["execution_plan"] = state.get("execution_plan")
            result["next_action"] = "report_approve"

        elif gate == "worker_result":
            if self._is_analysis_thesis_gate(state):
                options = self._analysis_thesis_options_from_state(state)
                selection = self._analysis_thesis_selection(state)
                result["present_to_user"] = self._format_analysis_thesis_confirmation(
                    options,
                    selection=selection,
                    error=str(state.get("analysis_feedback_error") or ""),
                )
                result["acceptance_report"] = decision.get("acceptance_report")
                result["next_task"] = decision.get("task_packet", {}).get("agent_id")
                result["accepted_artifacts"] = state.get("accepted_artifacts", [])
                result["analysis_thesis_options"] = options
                result["analysis_thesis_selection"] = selection
                if selection:
                    result["next_action"] = "report_approve"
                else:
                    result["next_action"] = "human_feedback"
                    result["questions"] = self._analysis_thesis_questions(options)
            elif self._is_storyline_confirmation_gate(state):
                artifact = self._storyline_artifact_from_state(state)
                result["present_to_user"] = self._format_storyline_confirmation(
                    artifact,
                    error=str(state.get("storyline_feedback_error") or ""),
                )
                result["acceptance_report"] = decision.get("acceptance_report")
                result["next_task"] = decision.get("task_packet", {}).get("agent_id")
                result["accepted_artifacts"] = state.get("accepted_artifacts", [])
                result["storyline"] = artifact
                result["questions"] = self._storyline_confirmation_questions(
                    needs_detail=bool(state.get("storyline_feedback_error"))
                )
                result["next_action"] = "report_approve_or_feedback"
            else:
                result["acceptance_report"] = decision.get("acceptance_report")
                result["next_task"] = decision.get("task_packet", {}).get("agent_id")
                result["accepted_artifacts"] = state.get("accepted_artifacts", [])
                result["next_action"] = "report_approve"

        elif gate == "delivery_options":
            result["accepted_artifacts"] = state.get("accepted_artifacts", [])
            result["rendered_files"] = self._accepted_rendered_files(state)
            raw_brief = read_json(self.raw_brief_path, default={})
            result["requested_followup_targets"] = (
                raw_brief.get("requested_followup_targets", [])
                if isinstance(raw_brief, dict)
                else []
            )
            result["delivery_options"] = [
                "format:ppt",
                "format:html",
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

        self._attach_question_interaction(result)
        return result

    @staticmethod
    def _attach_question_interaction(result: dict[str, Any]) -> None:
        """Attach one deterministic WorkBuddy adapter to every question gate."""

        questions = result.get("questions")
        if not isinstance(questions, list):
            return
        interaction_required = bool(questions)
        result["interaction_required"] = interaction_required
        result["preferred_tool"] = "AskUserQuestion"
        result["must_call_tool_before_next_cli"] = interaction_required
        result["presentation_required_before_tool"] = interaction_required
        result["presentation_text"] = result.get("present_to_user", "")
        result["presentation_delivery_mode"] = (
            "separate_user_visible_message_before_tool"
            if interaction_required
            else "none"
        )
        result["host_action_sequence"] = (
            ["send_present_to_user_message", "call_AskUserQuestion"]
            if interaction_required
            else []
        )
        result["ask_user_question_payload"] = {
            "questions": [
                {
                    "question": question["question"],
                    "header": question["header"],
                    "options": question.get("options", []),
                    "multiSelect": bool(question.get("multiSelect", False)),
                }
                for question in questions
            ]
        }

    def _is_analysis_thesis_gate(self, state: dict[str, Any]) -> bool:
        current = state.get("current_task") or {}
        if current.get("agent_id") != "analysis":
            return False
        if state.get("human_gate") != "worker_result":
            return False
        return bool(self._analysis_thesis_options_from_state(state))

    def _analysis_thesis_selection(self, state: dict[str, Any]) -> dict[str, Any] | None:
        project_state = state.get("project_state")
        if not isinstance(project_state, dict):
            return None
        selection = project_state.get("analysis_thesis_selection")
        return selection if isinstance(selection, dict) else None

    def _analysis_thesis_options_from_state(
        self, state: dict[str, Any]
    ) -> list[dict[str, Any]]:
        worker_result = state.get("worker_result") or {}
        artifact = worker_result.get("artifact")
        if not isinstance(artifact, dict):
            task = state.get("current_task") or {}
            artifact_path = task.get("artifact_path")
            if artifact_path:
                artifact = read_json(Path(str(artifact_path)), default={})
        return self._analysis_thesis_options(artifact if isinstance(artifact, dict) else {})

    @staticmethod
    def _analysis_thesis_options(artifact: dict[str, Any]) -> list[dict[str, Any]]:
        raw_options = artifact.get("thesis_options")
        if not isinstance(raw_options, list) or not raw_options:
            raw_options = artifact.get("viewpoint_candidates")
        if not isinstance(raw_options, list):
            return []

        findings = {
            str(item.get("id") or item.get("finding_id")): item
            for item in artifact.get("findings") or []
            if isinstance(item, dict) and (item.get("id") or item.get("finding_id"))
        }
        options: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_options[:3], 1):
            if not isinstance(raw, dict):
                continue
            option_id = str(
                raw.get("option_id")
                or raw.get("thesis_id")
                or raw.get("viewpoint_id")
                or f"TG-{index:02d}"
            ).strip()
            main_thesis = str(
                raw.get("main_thesis")
                or raw.get("statement")
                or raw.get("claim")
                or ""
            ).strip()
            if not main_thesis:
                continue
            sub_theses = raw.get("sub_theses")
            normalized_subs: list[dict[str, Any]] = []
            if isinstance(sub_theses, list):
                for sub_index, sub in enumerate(sub_theses[:4], 1):
                    if isinstance(sub, dict):
                        claim = str(
                            sub.get("claim")
                            or sub.get("statement")
                            or sub.get("thesis")
                            or ""
                        ).strip()
                        refs = sub.get("finding_refs") or sub.get("findings") or []
                        confidence = sub.get("confidence")
                    else:
                        claim = str(sub).strip()
                        refs = []
                        confidence = None
                    if claim:
                        normalized_subs.append(
                            {
                                "id": f"{option_id}-S{sub_index}",
                                "claim": claim,
                                "finding_refs": [
                                    str(ref) for ref in refs if str(ref).strip()
                                ]
                                if isinstance(refs, list)
                                else [],
                                "confidence": confidence or "",
                                "why_it_matters": (
                                    str(sub.get("why_it_matters") or "")
                                    if isinstance(sub, dict)
                                    else ""
                                ),
                            }
                        )
            if not normalized_subs:
                refs = raw.get("finding_refs") or []
                if isinstance(refs, list):
                    for sub_index, ref in enumerate(refs[:4], 1):
                        finding = findings.get(str(ref), {})
                        claim = str(
                            finding.get("claim")
                            or finding.get("statement")
                            or ref
                        ).strip()
                        if claim:
                            normalized_subs.append(
                                {
                                    "id": f"{option_id}-S{sub_index}",
                                    "claim": claim,
                                    "finding_refs": [str(ref)],
                                    "confidence": str(finding.get("confidence") or ""),
                                    "why_it_matters": str(finding.get("so_what") or ""),
                                }
                            )
            options.append(
                {
                    "option_id": option_id,
                    "main_thesis": main_thesis,
                    "sub_theses": normalized_subs[:4],
                    "finding_refs": [
                        str(ref)
                        for ref in raw.get("finding_refs", [])
                        if str(ref).strip()
                    ]
                    if isinstance(raw.get("finding_refs"), list)
                    else [],
                    "evidence_strength": str(
                        raw.get("evidence_strength") or raw.get("strength") or ""
                    ),
                    "best_for": str(raw.get("best_for") or ""),
                    "tradeoffs": [
                        str(item)
                        for item in raw.get("tradeoffs", [])
                        if str(item).strip()
                    ]
                    if isinstance(raw.get("tradeoffs"), list)
                    else [],
                }
            )
        return options

    @staticmethod
    def _format_analysis_thesis_confirmation(
        options: list[dict[str, Any]],
        *,
        selection: dict[str, Any] | None = None,
        error: str = "",
    ) -> str:
        lines = [
            "## Analysis 论点组确认",
            "",
            "Analysis 已基于当前证据整理出可进入 Storyline 的主论点方案。请在下方唯一输入框填写最适合本次汇报的方案编号；如果都不合适，请在同一处说明原因；如果你希望自己修改，也直接在同一处写出修改方向或新版本，Analysis 会重新整理成结构化表达。",
        ]
        if error:
            lines.extend(["", f"需要补充：{error}"])
        if selection:
            lines.extend(
                [
                    "",
                    f"已记录选择：**{selection.get('option_id', '')}**",
                    f"选择说明：{selection.get('human_feedback', '无')}",
                    "",
                    "如无进一步修改，确认后进入 Storyline。",
                ]
            )
        for option in options:
            lines.extend(["", f"### {option['option_id']}｜{option['main_thesis']}"])
            if option.get("best_for"):
                lines.append(f"- 适合场景：{option['best_for']}")
            if option.get("evidence_strength"):
                lines.append(f"- 证据强度：{option['evidence_strength']}")
            subs = option.get("sub_theses") or []
            if subs:
                lines.append("- 分论点：")
                for index, sub in enumerate(subs, 1):
                    refs = sub.get("finding_refs") or []
                    suffix = f"（引用：{', '.join(refs)}）" if refs else ""
                    confidence = (
                        f"；可信度：{sub.get('confidence')}"
                        if sub.get("confidence")
                        else ""
                    )
                    lines.append(
                        f"  {index}. {sub.get('claim', '')}{suffix}{confidence}"
                    )
            tradeoffs = option.get("tradeoffs") or []
            if tradeoffs:
                lines.append(f"- 主要取舍/边界：{'；'.join(tradeoffs)}")
        lines.extend(
            [
                "",
                "---",
                "",
                "请在同一个输入框填写方案编号；或填写“都不好 + 原因”；或直接写出你的修改意见。",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _analysis_thesis_questions(
        options: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        option_ids = " / ".join(
            str(option.get("option_id") or "").strip()
            for option in options
            if str(option.get("option_id") or "").strip()
        )
        choice_hint = f"（{option_ids}）" if option_ids else ""
        return [
            {
                "header": "论点组确认",
                "question": (
                    "请在一个输入框内完成确认或修改：同意已有方案时填写方案编号"
                    f"{choice_hint}，可选填理由；不同意时填写“都不好 + 原因”，"
                    "或直接写出你的修改意见。"
                ),
                "inputType": "text",
                "multiSelect": False,
                "options": [],
            },
        ]

    def _record_analysis_thesis_feedback(
        self,
        state: dict[str, Any],
        feedback: str,
    ) -> dict[str, Any]:
        options = self._analysis_thesis_options_from_state(state)
        intent = self._classify_analysis_thesis_feedback(feedback, options)
        if intent["kind"] == "select":
            option = intent["option"]
            selection = {
                "option_id": option["option_id"],
                "main_thesis": option["main_thesis"],
                "sub_theses": option.get("sub_theses", []),
                "finding_refs": option.get("finding_refs", []),
                "human_feedback": feedback,
                "selected_at": now_iso(),
            }
            state.setdefault("project_state", {})[
                "analysis_thesis_selection"
            ] = selection
            decision = state.get("pending_decision")
            if isinstance(decision, dict):
                packet = decision.get("task_packet")
                if isinstance(packet, dict):
                    packet["selected_analysis_thesis"] = selection
            state.pop("analysis_feedback_error", None)
            state["current_actor"] = "human"
            state["human_gate"] = "worker_result"
            state["status"] = "awaiting_intermediate_review"
            self._save_state(state)
            self._append_decision(
                "analysis_thesis_selected",
                "Human selected an Analysis thesis option",
                {
                    "option_id": option["option_id"],
                    "feedback": feedback,
                },
            )
            return self._human_gate_result(state)

        if intent["kind"] in ("rewrite", "custom"):
            if not self._has_meaningful_analysis_feedback_detail(
                feedback, intent["kind"]
            ):
                state["analysis_feedback_error"] = (
                    "选择“都不好，重新写”或“我自己修改”时，需要说明原因或提供修改内容，"
                    "否则 Analysis 只能随机重写。"
                )
                state["current_actor"] = "human"
                state["human_gate"] = "worker_result"
                state["status"] = "awaiting_intermediate_review"
                self._save_state(state)
                self._append_decision(
                    "analysis_thesis_feedback_needs_detail",
                    "Human asked to revise Analysis thesis options without actionable detail",
                    {"feedback": feedback, "intent": intent["kind"]},
                )
                return self._human_gate_result(state)
            return self._revise_current_analysis_task_from_human_feedback(
                state,
                feedback=feedback,
                mode=intent["kind"],
            )

        state["analysis_feedback_error"] = (
            "没有识别到你的选择。请明确选择某个方案编号（如 TG-01），"
            "或选择“都不好，重新写”/“我自己修改”。"
        )
        state["current_actor"] = "human"
        state["human_gate"] = "worker_result"
        state["status"] = "awaiting_intermediate_review"
        self._save_state(state)
        self._append_decision(
            "analysis_thesis_feedback_unrecognized",
            "Human feedback did not identify an Analysis thesis action",
            {"feedback": feedback},
        )
        return self._human_gate_result(state)

    @classmethod
    def _classify_analysis_thesis_feedback(
        cls,
        feedback: str,
        options: list[dict[str, Any]],
    ) -> dict[str, Any]:
        text = str(feedback or "")
        normalized = cls._normalize_choice_token(text)
        rewrite_tokens = (
            "rewrite",
            "都不好",
            "全部不好",
            "都不合适",
            "不合适",
            "不满意",
            "重新写",
            "重写",
            "重来",
        )
        custom_tokens = (
            "custom",
            "自己修改",
            "我自己改",
            "我来改",
            "自定义",
            "我的修改",
            "按以下",
            "改成",
            "修改为",
        )
        option = cls._selected_analysis_option(text, options)
        if option:
            return {"kind": "select", "option": option}
        if any(cls._normalize_choice_token(token) in normalized for token in rewrite_tokens):
            return {"kind": "rewrite"}
        if any(cls._normalize_choice_token(token) in normalized for token in custom_tokens):
            return {"kind": "custom"}
        if cls._looks_like_custom_analysis_feedback(text):
            return {"kind": "custom"}
        return {"kind": "unknown"}

    @classmethod
    def _selected_analysis_option(
        cls,
        feedback: str,
        options: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        normalized = cls._normalize_choice_token(feedback)
        for option in options:
            option_id = str(option.get("option_id") or "")
            if cls._normalize_choice_token(option_id) in normalized:
                return option
        index = cls._selected_option_index(feedback)
        if index is not None and 0 <= index < len(options):
            return options[index]
        return None

    @staticmethod
    def _normalize_choice_token(value: str) -> str:
        return re.sub(r"[\s_\-:：|｜#\"'`，,。；;、（）()\[\]]+", "", value).lower()

    @staticmethod
    def _selected_option_index(feedback: str) -> int | None:
        text = str(feedback or "")
        patterns = (
            r"(?:方案|选择|选|第)\s*([ABCabc123一二三])\s*(?:个|组|套|项|方案)?",
            r"\b([ABCabc])\b\s*(?:方案|组|项)",
        )
        mapping = {
            "a": 0,
            "1": 0,
            "一": 0,
            "b": 1,
            "2": 1,
            "二": 1,
            "c": 2,
            "3": 2,
            "三": 2,
        }
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return mapping.get(match.group(1).lower())
        return None

    @staticmethod
    def _looks_like_custom_analysis_feedback(feedback: str) -> bool:
        text = str(feedback or "").strip()
        if len(text) < 18:
            return False
        return any(
            token in text
            for token in (
                "主论点",
                "分论点",
                "应该",
                "更应该",
                "改为",
                "我觉得",
                "建议",
            )
        )

    @staticmethod
    def _has_meaningful_analysis_feedback_detail(feedback: str, mode: str) -> bool:
        detail = str(feedback or "")
        for token in (
            "rewrite",
            "custom",
            "都不好",
            "全部不好",
            "都不合适",
            "不合适",
            "不满意",
            "重新写",
            "重写",
            "重来",
            "自己修改",
            "我自己改",
            "我来改",
            "自定义",
            "我的修改",
            "原因",
            "理由",
            "因为",
        ):
            detail = detail.replace(token, "")
        detail = re.sub(r"[\s:：|｜#\"'`，,。；;、（）()\[\]]+", "", detail)
        meaningful_chars = re.findall(r"[\w\u4e00-\u9fff]", detail)
        threshold = 6 if mode == "custom" else 4
        return len(meaningful_chars) >= threshold

    def _revise_current_analysis_task_from_human_feedback(
        self,
        state: dict[str, Any],
        *,
        feedback: str,
        mode: str,
    ) -> dict[str, Any]:
        task = state.get("current_task")
        if not isinstance(task, dict) or task.get("agent_id") != "analysis":
            raise StepError("当前人审反馈不属于 Analysis task，不能复用 Analysis 上下文返工")
        task_dir = Path(str(task.get("task_dir") or ""))
        run_state_path = task_dir / "run_state.json"
        if not run_state_path.exists():
            raise StepError(f"Analysis run_state 不存在，无法复用当前 task: {run_state_path}")
        run_state = read_json(run_state_path, default={})
        round_index = int(run_state.get("round_index") or 0)
        run_state["current_step"] = "review_completed"
        run_state["status"] = "running"
        run_state["max_revision_rounds"] = max(
            int(run_state.get("max_revision_rounds") or 0),
            round_index + 2,
        )
        mode_label = "用户认为现有论点组都不合适" if mode == "rewrite" else "用户提供了自定义修改意见"
        run_state["p0_open"] = [
            {
                "id": f"P0-human-analysis-thesis-{now_iso().replace(':', '').replace('+', 'Z')}",
                "severity": "P0",
                "dimension": "人审偏好",
                "message": f"{mode_label}，需要复用当前 Analysis 上下文重新整理主论点组。",
                "evidence": feedback,
                "suggestion": (
                    "不要新起 Analysis task。基于当前 findings、证据边界和用户反馈，"
                    "重新输出 2-3 组 thesis_options；每组包含主论点和 2-4 个分论点。"
                ),
            }
        ]
        run_state["p1_open"] = []
        run_state.setdefault("human_feedback_requests", []).append(
            {
                "at": now_iso(),
                "gate": "analysis_thesis",
                "mode": mode,
                "feedback": feedback,
            }
        )
        run_state.setdefault("history", []).append(
            {
                "at": now_iso(),
                "step": "human_analysis_thesis_feedback",
                "message": f"{mode_label}: {feedback}",
            }
        )
        run_state["updated_at"] = now_iso()
        handoff_dir = task_dir / "handoff"
        stale_revise_output = handoff_dir / "output_revise.json"
        if stale_revise_output.exists():
            stale_revise_output.unlink()
        write_json(run_state_path, run_state)

        task["status"] = "revision_required"
        task["manager_acceptance"] = None
        task["accepted_at"] = None
        self._replace_task(state, task)
        self._set_plan_task_status(str(task.get("task_id") or ""), "revision_required")
        state["execution_plan"] = read_json(self.plan_path, default={})
        state["accepted_artifacts"] = [
            item
            for item in state.get("accepted_artifacts", [])
            if item.get("task_id") != task.get("task_id")
            and item.get("task_dir") != task.get("task_dir")
        ]
        project_state = state.setdefault("project_state", {})
        if isinstance(project_state, dict):
            project_state.pop("analysis_thesis_selection", None)
            project_state["analysis_thesis_revision_request"] = {
                "mode": mode,
                "feedback": feedback,
                "requested_at": now_iso(),
            }
        state.pop("analysis_feedback_error", None)
        state["previous_pending_decision"] = state.get("pending_decision")
        state["pending_decision"] = None
        state["human_gate"] = None
        state["current_actor"] = "worker"
        state["manager_step"] = "idle"
        state["status"] = "running"
        state["worker_result"] = None
        state["last_event"] = "analysis_thesis_feedback_revision"
        self._save_state(state)
        self._append_decision(
            "analysis_thesis_revision",
            "Human feedback returned to the same Analysis task for revision",
            {"task_id": task.get("task_id"), "mode": mode, "feedback": feedback},
        )
        return self.prepare()

    def _is_storyline_confirmation_gate(self, state: dict[str, Any]) -> bool:
        current = state.get("current_task") or {}
        if current.get("agent_id") != "storyline":
            return False
        if state.get("human_gate") != "worker_result":
            return False
        artifact = self._storyline_artifact_from_state(state)
        return bool(artifact.get("core_answer") or artifact.get("sections"))

    def _storyline_artifact_from_state(self, state: dict[str, Any]) -> dict[str, Any]:
        worker_result = state.get("worker_result") or {}
        artifact = worker_result.get("artifact")
        if isinstance(artifact, dict):
            return artifact
        task = state.get("current_task") or {}
        artifact_path = task.get("artifact_path")
        if artifact_path:
            loaded = read_json(Path(str(artifact_path)), default={})
            return loaded if isinstance(loaded, dict) else {}
        return {}

    @staticmethod
    def _format_storyline_confirmation(
        artifact: dict[str, Any],
        *,
        error: str = "",
    ) -> str:
        lines = [
            "## Storyline 确认",
            "",
            "Storyline 已基于确认后的 Analysis 方向整理出一版故事线。请确认这条主线是否可以进入 Report；如果不满意，请说明原因后让同一个 Storyline agent 重写；如果你希望自己修改，请直接写出修改方向或新版本。",
        ]
        if error:
            lines.extend(["", f"需要补充：{error}"])

        core_answer = str(artifact.get("core_answer") or "").strip()
        if core_answer:
            lines.extend(["", "### 核心答案", core_answer])

        executive_summary = artifact.get("executive_summary")
        if isinstance(executive_summary, dict):
            summary_lines = []
            for key in ("context", "core_answer"):
                value = executive_summary.get(key)
                if isinstance(value, str) and value.strip() and value.strip() != core_answer:
                    summary_lines.append(value.strip())
            implications = executive_summary.get("implications")
            if isinstance(implications, list):
                for item in implications[:2]:
                    if isinstance(item, dict) and item.get("statement"):
                        summary_lines.append(str(item["statement"]))
            if summary_lines:
                lines.extend(["", "### 摘要要点"])
                lines.extend(f"- {item}" for item in summary_lines[:4])
        elif isinstance(executive_summary, str) and executive_summary.strip():
            lines.extend(["", "### 摘要要点", executive_summary.strip()])

        sections = artifact.get("sections") or []
        if isinstance(sections, list) and sections:
            lines.extend(["", "### 故事线"])
            lines.extend(
                [
                    "| 序号 | 章节 | 标题（Leadline） | 核心论证 |",
                    "|---:|---|---|---|",
                ]
            )
            for index, section in enumerate(sections, 1):
                if not isinstance(section, dict):
                    continue
                chapter = str(section.get("chapter") or f"第 {index} 章").strip()
                heading = str(section.get("heading") or f"Section {index}").strip()
                brief = str(section.get("brief") or "").strip()
                cells = [chapter, heading, brief or "—"]
                escaped = [
                    value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")
                    for value in cells
                ]
                lines.append(
                    f"| {index} | {escaped[0]} | {escaped[1]} | {escaped[2]} |"
                )

        appendix_refs = artifact.get("appendix_finding_refs") or []
        open_items = artifact.get("open_issues") or artifact.get("open_questions") or []
        boundary_lines = []
        if isinstance(open_items, list):
            boundary_lines.extend(str(item) for item in open_items[:4] if str(item).strip())
        if isinstance(appendix_refs, list) and appendix_refs:
            boundary_lines.append("降层/附录 finding：" + ", ".join(str(item) for item in appendix_refs[:8]))
        if boundary_lines:
            lines.extend(["", "### 关键边界 / 不进入主线的内容"])
            lines.extend(f"- {item}" for item in boundary_lines)

        lines.extend(
            [
                "",
                "---",
                "",
                "请选择：可以进入 Report；或选择“不好，重新写”并说明为什么；或选择“我自己修改”并写出你的修改意见。",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _storyline_confirmation_questions(
        *, needs_detail: bool = False
    ) -> list[dict[str, Any]]:
        if needs_detail:
            return [
                {
                    "header": "修改说明",
                    "question": "请说明 Storyline 不合适的原因，或直接写出你的修改意见。",
                    "inputType": "text",
                    "multiSelect": False,
                    "options": [],
                }
            ]
        return [
            {
                "header": "Storyline确认",
                "question": "这版 Storyline 是否可以进入 Report？",
                "multiSelect": False,
                "options": [
                    {
                        "label": "可以，进入Report",
                        "value": "approve",
                        "description": "确认当前故事线，进入报告正文写作",
                    },
                    {
                        "label": "不好，重新写",
                        "value": "rewrite",
                        "description": "需要说明原因；会复用当前 Storyline agent 上下文重写",
                    },
                    {
                        "label": "我自己修改",
                        "value": "custom",
                        "description": "可直接写非结构化修改意见；Storyline 会整理为结构化故事线",
                    },
                ],
            },
        ]

    def _record_storyline_confirmation_feedback(
        self,
        state: dict[str, Any],
        feedback: str,
    ) -> dict[str, Any]:
        project_state = state.setdefault("project_state", {})
        pending_intent = (
            str(project_state.get("storyline_pending_feedback_intent") or "")
            if isinstance(project_state, dict)
            else ""
        )
        classified_intent = self._classify_storyline_confirmation_feedback(feedback)
        intent = (
            "approve"
            if classified_intent == "approve"
            else pending_intent
            if pending_intent in ("rewrite", "custom")
            else classified_intent
        )
        effective_feedback = feedback
        if pending_intent in ("rewrite", "custom") and classified_intent != "approve":
            prefix = "不好，原因：" if pending_intent == "rewrite" else "我自己修改："
            effective_feedback = f"{prefix}{feedback}"
        if intent == "approve":
            if isinstance(project_state, dict):
                project_state.pop("storyline_pending_feedback_intent", None)
            state.setdefault("project_state", {})["storyline_confirmation"] = {
                "status": "approved",
                "human_feedback": feedback,
                "confirmed_at": now_iso(),
            }
            state.pop("storyline_feedback_error", None)
            self._save_state(state)
            self._append_decision(
                "storyline_confirmed",
                "Human confirmed Storyline and approved dispatch to Report",
                {"feedback": feedback},
            )
            return self.approve()

        if intent in ("rewrite", "custom"):
            if not self._has_meaningful_storyline_feedback_detail(feedback, intent):
                if isinstance(project_state, dict):
                    project_state["storyline_pending_feedback_intent"] = intent
                state["storyline_feedback_error"] = (
                    "选择“不好，重新写”或“我自己修改”时，需要说明原因或提供修改内容，"
                    "否则 Storyline 只能随机重写。"
                )
                state["current_actor"] = "human"
                state["human_gate"] = "worker_result"
                state["status"] = "awaiting_intermediate_review"
                self._save_state(state)
                self._append_decision(
                    "storyline_feedback_needs_detail",
                    "Human asked to revise Storyline without actionable detail",
                    {"feedback": feedback, "intent": intent},
                )
                return self._human_gate_result(state)
            return self._revise_current_storyline_task_from_human_feedback(
                state,
                feedback=effective_feedback,
                mode=intent,
            )

        state["storyline_feedback_error"] = (
            "没有识别到你的选择。请明确确认可以进入 Report，"
            "或选择“不好，重新写”/“我自己修改”。"
        )
        state["current_actor"] = "human"
        state["human_gate"] = "worker_result"
        state["status"] = "awaiting_intermediate_review"
        self._save_state(state)
        self._append_decision(
            "storyline_feedback_unrecognized",
            "Human feedback did not identify a Storyline action",
            {"feedback": feedback},
        )
        return self._human_gate_result(state)

    @classmethod
    def _classify_storyline_confirmation_feedback(cls, feedback: str) -> str:
        text = str(feedback or "")
        normalized = cls._normalize_choice_token(text)
        rewrite_tokens = (
            "rewrite",
            "不好",
            "不行",
            "不合适",
            "不满意",
            "重新写",
            "重写",
            "重来",
            "主线不对",
            "故事线不对",
        )
        custom_tokens = (
            "custom",
            "自己修改",
            "我自己改",
            "我来改",
            "自定义",
            "我的修改",
            "按以下",
            "改成",
            "修改为",
        )
        approve_tokens = (
            "approve",
            "可以",
            "确认",
            "通过",
            "没问题",
            "继续",
            "进入report",
            "进入报告",
            "ok",
        )
        if any(cls._normalize_choice_token(token) in normalized for token in rewrite_tokens):
            return "rewrite"
        if any(cls._normalize_choice_token(token) in normalized for token in custom_tokens):
            return "custom"
        if cls._looks_like_custom_storyline_feedback(text):
            return "custom"
        if any(cls._normalize_choice_token(token) in normalized for token in approve_tokens):
            return "approve"
        return "unknown"

    @staticmethod
    def _looks_like_custom_storyline_feedback(feedback: str) -> bool:
        text = str(feedback or "").strip()
        if len(text) < 18:
            return False
        return any(
            token in text
            for token in (
                "故事线",
                "核心答案",
                "主线",
                "章节",
                "标题",
                "先讲",
                "再讲",
                "改为",
                "我觉得",
                "建议",
            )
        )

    @staticmethod
    def _has_meaningful_storyline_feedback_detail(feedback: str, mode: str) -> bool:
        detail = str(feedback or "")
        for token in (
            "rewrite",
            "custom",
            "不好",
            "不行",
            "不合适",
            "不满意",
            "重新写",
            "重写",
            "重来",
            "主线不对",
            "故事线不对",
            "自己修改",
            "我自己改",
            "我来改",
            "自定义",
            "我的修改",
            "原因",
            "理由",
            "因为",
        ):
            detail = detail.replace(token, "")
        detail = re.sub(r"[\s:：|｜#\"'`，,。；;、（）()\[\]]+", "", detail)
        meaningful_chars = re.findall(r"[\w\u4e00-\u9fff]", detail)
        threshold = 6 if mode == "custom" else 4
        return len(meaningful_chars) >= threshold

    def _revise_current_storyline_task_from_human_feedback(
        self,
        state: dict[str, Any],
        *,
        feedback: str,
        mode: str,
    ) -> dict[str, Any]:
        task = state.get("current_task")
        if not isinstance(task, dict) or task.get("agent_id") != "storyline":
            raise StepError("当前人审反馈不属于 Storyline task，不能复用 Storyline 上下文返工")
        task_dir = Path(str(task.get("task_dir") or ""))
        run_state_path = task_dir / "run_state.json"
        if not run_state_path.exists():
            raise StepError(f"Storyline run_state 不存在，无法复用当前 task: {run_state_path}")
        run_state = read_json(run_state_path, default={})
        round_index = int(run_state.get("round_index") or 0)
        run_state["current_step"] = "review_completed"
        run_state["status"] = "running"
        run_state["max_revision_rounds"] = max(
            int(run_state.get("max_revision_rounds") or 0),
            round_index + 2,
        )
        mode_label = "用户认为当前 Storyline 不成立" if mode == "rewrite" else "用户提供了自定义 Storyline 修改意见"
        run_state["p0_open"] = [
            {
                "id": f"P0-human-storyline-{now_iso().replace(':', '').replace('+', 'Z')}",
                "severity": "P0",
                "dimension": "人审偏好",
                "message": f"{mode_label}，需要复用当前 Storyline 上下文重新整理一版故事线。",
                "evidence": feedback,
                "suggestion": (
                    "不要新起 Storyline task。基于已确认的 Analysis 论点组、Analysis findings、"
                    "当前 Storyline 和用户反馈，重新输出一版 storyline.v3；只保留一条主线，"
                    "更新 core_answer、sections、appendix_finding_refs/open_issues。"
                ),
            }
        ]
        run_state["p1_open"] = []
        run_state.setdefault("human_feedback_requests", []).append(
            {
                "at": now_iso(),
                "gate": "storyline_confirmation",
                "mode": mode,
                "feedback": feedback,
            }
        )
        run_state.setdefault("history", []).append(
            {
                "at": now_iso(),
                "step": "human_storyline_feedback",
                "message": f"{mode_label}: {feedback}",
            }
        )
        run_state["updated_at"] = now_iso()
        handoff_dir = task_dir / "handoff"
        stale_revise_output = handoff_dir / "output_revise.json"
        if stale_revise_output.exists():
            stale_revise_output.unlink()
        write_json(run_state_path, run_state)

        task["status"] = "revision_required"
        task["manager_acceptance"] = None
        task["accepted_at"] = None
        self._replace_task(state, task)
        self._set_plan_task_status(str(task.get("task_id") or ""), "revision_required")
        state["execution_plan"] = read_json(self.plan_path, default={})
        state["accepted_artifacts"] = [
            item
            for item in state.get("accepted_artifacts", [])
            if item.get("task_id") != task.get("task_id")
            and item.get("task_dir") != task.get("task_dir")
        ]
        project_state = state.setdefault("project_state", {})
        if isinstance(project_state, dict):
            project_state.pop("storyline_confirmation", None)
            project_state.pop("storyline_pending_feedback_intent", None)
            project_state["storyline_revision_request"] = {
                "mode": mode,
                "feedback": feedback,
                "requested_at": now_iso(),
            }
        state.pop("storyline_feedback_error", None)
        state["previous_pending_decision"] = state.get("pending_decision")
        state["pending_decision"] = None
        state["human_gate"] = None
        state["current_actor"] = "worker"
        state["manager_step"] = "idle"
        state["status"] = "running"
        state["worker_result"] = None
        state["last_event"] = "storyline_confirmation_feedback_revision"
        self._save_state(state)
        self._append_decision(
            "storyline_confirmation_revision",
            "Human feedback returned to the same Storyline task for revision",
            {"task_id": task.get("task_id"), "mode": mode, "feedback": feedback},
        )
        return self.prepare()

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
            # Canonical plans are created before later task IDs exist. Bind the
            # planned slot for this Worker to the actual runtime task instead
            # of appending a duplicate plan entry.
            agent_id = task_record.get("agent_id")
            packet = task_record.get("packet") or {}
            for task in tasks:
                if (
                    task.get("agent_id") == agent_id
                    and task.get("status") in ("planned", "pending")
                ):
                    task.update(
                        {
                            "task_id": task_id,
                            "objective": packet.get(
                                "objective", task.get("objective", "")
                            ),
                            "dependencies": packet.get(
                                "dependencies", task.get("dependencies", [])
                            ),
                            "status": status,
                        }
                    )
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
    - ``None`` → default checkpoint pause after Analysis and Storyline
    """
    if run_mode == "full_auto":
        return False
    if run_mode == "step_by_step":
        return True
    if isinstance(run_mode, list):
        return agent_id in run_mode
    return agent_id in DEFAULT_CHECKPOINT_PAUSE_AGENTS
