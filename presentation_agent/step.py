from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from presentation_agent.capabilities.budget import estimate_tokens
from presentation_agent.capabilities.compiler import compile_skill_package
from presentation_agent.input_loader import load_agent_input
from presentation_agent.io import read_json, write_json
from presentation_agent.learning import LearningEventStore
from presentation_agent.memory import MemoryStore
from presentation_agent.memory_retrieval import MemoryRetriever
from presentation_agent.models import AgentSpec, Objection, ReviewReport, StopDecision, now_iso
from presentation_agent.review import ArtifactReviewer, StopChecker
from presentation_agent.routing import build_routing_policy
from presentation_agent.skill_package import SkillPackage
from presentation_agent.skills.base import SkillContext
from presentation_agent.skills.generic import GenericSkill
from presentation_agent.skills.registry import get_skill


class StepError(RuntimeError):
    """Raised when a step operation is called at the wrong state."""


def _load_run_state(root: Path, run_dir: Path, data_root: Optional[Path] = None) -> dict[str, Any]:
    """Load the per-run global state, seeded from the global template on first use.

    Each pipeline run (``artifacts/<run_name>/``) has its own ``state.json`` so
    that different projects never cross-contaminate shared state.  The file at
    ``data/global/state.json`` serves only as the initial seed/template — once
    a run's state exists, the global file is never read for that run again.
    """
    state_path = run_dir.parent / "state.json"
    if state_path.exists():
        return read_json(state_path, default={})
    template = (data_root or (root / "data")) / "global" / "state.json"
    seed = read_json(template, default={})
    if seed:
        write_json(state_path, seed)
    return seed


def memo_suffix(note: str) -> str:
    return f"（{note}）" if note else ""


# ---- Agent-level step runner ------------------------------------------------

class StepRunner:
    """Drive one agent loop in single-step mode (inline / host-self-execution).

    Harness never calls any model. It assembles instruction prompts, writes
    them to handoff files, and on commit validates the host's output against
    the agent's output schema. The host (WorkBuddy / Claude Code / Codex) reads
    the instruction, runs its own model, writes the handoff output, and calls
    commit.

    State machine (current_step values):
      init → awaiting_gen_output → gen_completed →
        awaiting_review_output → review_completed →
          [P0] → awaiting_revise_output → gen_completed   (loop)
          [no P0] → done
    """

    def __init__(self, root: Path, run_dir: Path, data_root: Optional[Path] = None) -> None:
        self.root = root
        self.run_dir = run_dir
        self.data_root = data_root or (root / "data")
        self.run_state_path = run_dir / "run_state.json"
        self.handoff_dir = run_dir / "handoff"
        self.handoff_dir.mkdir(parents=True, exist_ok=True)

        config = read_json(self.root / "configs" / "agents.json")
        self.specs = {item["id"]: AgentSpec.from_dict(item) for item in config["agents"]}
        self.max_revision_rounds = int(config.get("pipeline", {}).get("default_max_revision_rounds", 2))

        state = self._load_state()
        agent_id = state.get("agent_id")
        if not agent_id:
            raise StepError("run_state.json 缺少 agent_id，该 stage 可能尚未初始化")
        self.spec = self.specs[agent_id]
        self.memory = MemoryStore(root, self.spec.id, data_root=self.data_root)
        compiled_path = self.run_dir / "compiled_skill_package.json"
        if compiled_path.exists():
            self.skill_package = SkillPackage.from_dict(read_json(compiled_path))
        else:
            input_data = self._load_input(state)
            self.skill_package = compile_skill_package(root, self.spec, input_data)
            write_json(compiled_path, self.skill_package.to_dict())
        state["selected_capabilities"] = self.skill_package.selected_capabilities
        state["skill_fingerprint"] = self.skill_package.fingerprint
        state["skill_budget"] = self.skill_package.budget
        write_json(self.run_state_path, state)
        self.skill = get_skill(self.spec.skill, llm=None)  # no LLM — host model generates

        self.full_global_state = _load_run_state(root, run_dir, data_root=self.data_root)

        self.reviewer = ArtifactReviewer(llm=None)  # deterministic-only in inline mode
        # 宿主自执行模式下不创建独立的 LLM checker。
        # StopChecker 仅做确定性判定（P0 数量、schema 匹配）。
        # LLM sanity check 由宿主在 review 阶段通过 _compose_review_instruction 完成。
        # LoopRunner 路径使用 StopChecker(llm=review_llm) 执行独立 LLM 合理性扫描，
        # 两者应对的场景不同：前者宿主只有一个模型可用，后者 harness 自持多个 LLM client。
        self.stop_checker = StopChecker()

    # ---- public API ---------------------------------------------------------

    def status(self) -> dict[str, Any]:
        state = self._load_state()
        return {
            "agent_id": state.get("agent_id"),
            "agent_name": state.get("agent_name"),
            "stage": state.get("stage"),
            "current_step": state.get("current_step"),
            "round_index": state.get("round_index"),
            "p0_open_count": len(state.get("p0_open", [])),
            "status": state.get("status"),
            "handoff_dir": str(self.handoff_dir),
            "instruction_path": self._last_instruction_path(state),
            "output_path": self._last_output_path(state),
            "selected_capabilities": state.get("selected_capabilities", []),
            "skill_fingerprint": state.get("skill_fingerprint", ""),
            "prompt_budget": state.get("prompt_budget", {}),
        }

    def prepare(self) -> dict[str, Any]:
        state = self._load_state()
        step = state.get("current_step")

        if step == "done":
            raise StepError("stage 已完成，无需 prepare")
        if step in ("awaiting_gen_output", "awaiting_review_output", "awaiting_revise_output"):
            instr_path = self._instruction_path_for(step)
            raise StepError(
                f"已处于 {step}，指令文件 {instr_path.name} 已就绪，请先 commit"
            )

        if step in ("init", "gen_completed"):
            return self._prepare_gen(state)
        if step == "review_completed":
            if state.get("p0_open"):
                return self._prepare_revise(state)
            return self._finalize(state)

        raise StepError(f"未知 step: {step}")

    def commit(self) -> dict[str, Any]:
        state = self._load_state()
        step = state.get("current_step")

        handlers = {
            "awaiting_gen_output": self._commit_gen,
            "awaiting_review_output": self._commit_review,
            "awaiting_revise_output": self._commit_revise,
        }
        if step in handlers:
            return handlers[step](state)
        if step == "done":
            raise StepError("stage 已完成")
        raise StepError(f"当前状态 {step} 没有待 commit 的内容，请先 prepare")

    def abort(self) -> dict[str, Any]:
        state = self._load_state()
        state["status"] = "aborted"
        state["current_step"] = "done"
        self._write_state(state, "abort", "人工中止")
        return {"status": "aborted", "agent_id": self.spec.id}

    # ---- internal: prepare --------------------------------------------------

    def _prepare_gen(self, state: dict[str, Any]) -> dict[str, Any]:
        context = self._build_context()
        input_data = self._load_input(state)
        self._assert_input_ready(input_data)
        self._apply_memory_routing(context, input_data, state)

        round_idx = state.get("round_index", 0)
        previous_artifact = None
        objections = None
        if round_idx > 0:
            artifact_path = self.run_dir / f"draft_round_{round_idx - 1}.json"
            if artifact_path.exists():
                previous_artifact = read_json(artifact_path)
                objections_raw = state.get("p0_open", [])
                objections = [
                    Objection(
                        id=o.get("id", ""),
                        severity=o.get("severity", "P0"),
                        dimension=o.get("dimension", ""),
                        message=o.get("message", ""),
                        evidence=o.get("evidence", ""),
                        suggestion=o.get("suggestion", ""),
                    )
                    for o in objections_raw
                ]

        request = self.skill._build_request(
            self.spec, input_data, context,
            round_index=round_idx,
            objections=objections,
            previous_artifact=previous_artifact,
        )
        state.setdefault("prompt_budget", {})[f"generation_round_{round_idx}"] = dict(
            self.skill.last_prompt_budget
        )

        instruction_path = self.handoff_dir / "instruction_gen.md"
        output_path = self.handoff_dir / "output_gen.json"
        self._write_instruction(instruction_path, output_path, request, kind="gen")

        state["current_step"] = "awaiting_gen_output"
        self._write_state(state, "prepare_gen", "generation 指令已就绪，等待宿主模型写入")

        return {
            "step": "gen",
            "round_index": round_idx,
            "instruction_path": str(instruction_path),
            "output_path": str(output_path),
        }

    def _prepare_review(self, state: dict[str, Any]) -> dict[str, Any]:
        artifact_path = self.run_dir / f"draft_round_{state['round_index']}.json"
        artifact = read_json(artifact_path)
        input_data = self._load_input(state)

        instruction = self._compose_review_instruction(artifact, input_data)
        state.setdefault("prompt_budget", {})[f"review_round_{state['round_index']}"] = {
            "total_chars": len(instruction),
            "total_tokens_estimate": estimate_tokens(instruction),
        }
        instruction_path = self.handoff_dir / "instruction_review.md"
        output_path = self.handoff_dir / "output_review.json"
        instruction_path.write_text(instruction, encoding="utf-8")

        state["current_step"] = "awaiting_review_output"
        self._write_state(state, "prepare_review", "review 指令已就绪，等待宿主模型写入审查意见")

        return {
            "step": "review",
            "round_index": state["round_index"],
            "instruction_path": str(instruction_path),
            "output_path": str(output_path),
        }

    def _prepare_revise(self, state: dict[str, Any]) -> dict[str, Any]:
        context = self._build_context()
        input_data = self._load_input(state)
        self._apply_memory_routing(context, input_data, state)

        round_idx = state["round_index"]
        previous_artifact = None
        prev_path = self.run_dir / f"draft_round_{round_idx}.json"
        if prev_path.exists():
            previous_artifact = read_json(prev_path)

        objections_raw = state.get("p0_open", [])
        objections = [
            Objection(
                id=o.get("id", ""),
                severity=o.get("severity", "P0"),
                dimension=o.get("dimension", ""),
                message=o.get("message", ""),
                evidence=o.get("evidence", ""),
                suggestion=o.get("suggestion", ""),
            )
            for o in objections_raw
        ]

        request = self.skill._build_request(
            self.spec, input_data, context,
            round_index=round_idx + 1,
            objections=objections,
            previous_artifact=previous_artifact,
        )

        instruction_path = self.handoff_dir / "instruction_revise.md"
        output_path = self.handoff_dir / "output_revise.json"
        self._write_instruction(instruction_path, output_path, request, kind="revise")

        state["round_index"] = round_idx + 1
        state["current_step"] = "awaiting_revise_output"
        self._write_state(state, "prepare_revise", f"revise round {state['round_index']} 指令已就绪")

        p0_msgs = [o.get("message", "") for o in objections_raw[:3]]
        schema_p0s = [o for o in objections_raw if "schema-" in str(o.get("rubric_id", ""))]
        llm_p0s = [o for o in objections_raw if "schema-" not in str(o.get("rubric_id", ""))]
        parts = []
        if schema_p0s:
            parts.append(f"schema 校验发现 {len(schema_p0s)} 个 P0")
        if llm_p0s:
            parts.append(f"LLM review 发现 {len(llm_p0s)} 个 P0")
        revision_reason = "；".join(parts) if parts else ("P0 问题：" + "；".join(p0_msgs) if p0_msgs else "返工修复")

        return {
            "step": "revise",
            "round_index": state["round_index"],
            "instruction_path": str(instruction_path),
            "output_path": str(output_path),
            "revision_reason": revision_reason,
        }

    # ---- internal: commit ---------------------------------------------------

    def _commit_gen(self, state: dict[str, Any]) -> dict[str, Any]:
        artifact = self._read_and_validate_output("output_gen.json", state)

        round_idx = state["round_index"]
        draft_path = self.run_dir / f"draft_round_{round_idx}.json"
        write_json(draft_path, artifact)
        state["produced_artifacts"].append(str(draft_path))

        memory_note = self._record_gen_memory(state)
        self._write_state(state, "commit_gen", f"draft round {round_idx} 校验通过{memo_suffix(memory_note)}")

        state["current_step"] = "gen_completed"
        self._save_state(state)

        result = self._prepare_review(state)
        if memory_note:
            result["memory_notes"] = memory_note
        return result

    def _commit_review(self, state: dict[str, Any]) -> dict[str, Any]:
        review_data = self._read_and_validate_output("output_review.json", state)

        objections_raw = review_data.get("objections", [])
        objections: list[Objection] = []
        for idx, raw in enumerate(objections_raw, start=1):
            severity = raw.get("severity")
            if severity not in ("P0", "P1"):
                continue
            objections.append(Objection(
                id=f"{severity}-{raw.get('rubric_id', f'host-{idx}')}",
                severity=severity,
                dimension=str(raw.get("dimension", "")),
                message=str(raw.get("message", "")),
                evidence=str(raw.get("evidence", raw.get("rubric_id", ""))),
                suggestion=str(raw.get("suggestion", "")),
            ))

        review = ReviewReport(reviewer="host_model", objections=objections)
        review_path = self.run_dir / f"review_round_{state['round_index']}.json"
        write_json(review_path, review.to_dict())
        state["produced_artifacts"].append(str(review_path))

        # Also run deterministic schema gate
        artifact_path = self.run_dir / f"draft_round_{state['round_index']}.json"
        artifact = read_json(artifact_path)
        schema_objections = self.reviewer._schema_gate(
            self.spec, artifact, self.skill_package.to_dict()
        )
        all_p0 = review.p0 + [o for o in schema_objections if o.severity == "P0"]
        all_p1 = review.p1 + [o for o in schema_objections if o.severity == "P1"]
        merged = ReviewReport(
            reviewer="host_model+schema_gate",
            objections=all_p0 + all_p1,
        )

        state["p0_open"] = [o.to_dict() for o in merged.p0]
        state["p1_open"] = [o.to_dict() for o in merged.p1]
        new_learning = [o for o in merged.objections if not o.id.startswith("P1-memory-")]
        log_ids = self.memory.record_objections(state.get("run_id", self.run_dir.name), new_learning)
        state.setdefault("feedback_logged", []).extend(log_ids)

        decision = self.stop_checker.check(self.spec, artifact, merged)
        stop_path = self.run_dir / f"stop_decision_round_{state['round_index']}.json"
        write_json(stop_path, decision.to_dict())
        state["produced_artifacts"].append(str(stop_path))
        state["stop_decision"] = decision.to_dict()

        self._write_state(state, "commit_review",
            f"review round {state['round_index']}: P0={len(merged.p0)}, P1={len(merged.p1)}")

        state["current_step"] = "review_completed"
        self._save_state(state)

        review_summary = self._objections_to_summary(merged, state["round_index"])
        memory_note = f"审查完成，P0={len(merged.p0)}，P1={len(merged.p1)}；已记录 {len(log_ids)} 条学习日志"

        if decision.can_stop:
            result = self._finalize(state)
            result["review_summary"] = review_summary
            result["memory_notes"] = (result.get("memory_notes", "") + "; " + memory_note).strip("; ")
            return result

        if state["round_index"] >= self.max_revision_rounds:
            self._write_state(state, "commit_review",
                f"达到最大返工轮数 {self.max_revision_rounds}，强制结束")
            state["current_step"] = "review_completed"
            self._save_state(state)
            result = self._finalize(state)
            result["review_summary"] = review_summary
            result["memory_notes"] = (result.get("memory_notes", "") + "; 已达最大返工轮数，强制结束").strip("; ")
            return result

        result = self._prepare_revise(state)
        result["review_summary"] = review_summary
        result["memory_notes"] = memory_note
        return result

    def _commit_revise(self, state: dict[str, Any]) -> dict[str, Any]:
        artifact = self._read_and_validate_output("output_revise.json", state)

        round_idx = state["round_index"]
        draft_path = self.run_dir / f"draft_round_{round_idx}.json"
        write_json(draft_path, artifact)
        state["produced_artifacts"].append(str(draft_path))

        self._write_state(state, "commit_revise", f"revise round {round_idx} 校验通过")

        state["current_step"] = "gen_completed"
        self._save_state(state)

        return self._prepare_review(state)

    # ---- internal: helpers --------------------------------------------------

    def _finalize(self, state: dict[str, Any]) -> dict[str, Any]:
        round_idx = state["round_index"]
        artifact_path = self.run_dir / f"draft_round_{round_idx}.json"
        artifact = read_json(artifact_path)

        write_json(self.run_dir / "artifact.json", artifact)
        review_path_latest = self.run_dir / f"review_round_{round_idx}.json"
        if review_path_latest.exists():
            review_json = read_json(review_path_latest)
        else:
            review_json = {"objections": []}
        write_json(self.run_dir / "review.json", review_json)

        state["status"] = "pending_human_review"
        state["current_step"] = "done"
        state["next_action"] = "await_human_decision"
        self._write_state(state, "finalize", "stage 完成，等待人工评审")

        global_writes_applied = self._apply_global_writes(artifact)

        self._write_human_review(artifact, review_json)

        render_result = self._render_deliverable(artifact)

        preview = self._artifact_preview(artifact)
        review_summary = self._review_summary(review_json)
        memory_notes = self._memory_diff(global_writes_applied)
        render_note = render_result.present_line() if render_result else ""
        present = self._compose_stage_done_present(
            preview, review_summary, memory_notes, render_note
        )

        result = {
            "step": "done",
            "status": "pending_human_review",
            "agent_id": self.spec.id,
            "agent_name": self.spec.name,
            "stage": self.spec.stage,
            "round_index": round_idx,
            "artifact_path": str(self.run_dir / "artifact.json"),
            "review_summary": review_summary,
            "memory_notes": memory_notes,
            "present_to_user": present,
        }
        if render_result:
            result["render_result"] = render_result.to_dict()
            if render_result.status == "rendered" and render_result.output_path:
                # real deliverable files the host should surface to the user
                result["rendered_files"] = [render_result.output_path]
        return result

    def _render_deliverable(self, artifact: dict[str, Any]):
        """Render page_filling/format artifacts into real deliverable files.

        - page_filling (agent4): renders `artifact["draft_material"]` at draft
          fidelity (wireframe-level PPT/HTML/docx).
        - format (agent5): renders the artifact itself at final fidelity
          (McKinsey-grade PPT/HTML/docx).

        Returns a RenderResult, or None when this agent has no deliverable to
        render. Missing optional deps never crash: the RenderResult carries a
        `skipped_missing_dep` status instead.
        """
        if self.spec.id == "page_filling":
            material = artifact.get("draft_material")
            fidelity = "draft"
        elif self.spec.id == "format":
            material = artifact
            fidelity = "final"
        else:
            return None
        if not isinstance(material, dict) or not material.get("material_units"):
            return None

        try:
            from presentation_agent.renderers import render_material
        except Exception:
            return None

        topic = artifact.get("topic") or material.get("topic") or "deliverable"
        stem = self._safe_stem(topic)
        package = getattr(self, "skill_package", None)
        selected_capabilities = (
            package.selected_capabilities if package is not None else []
        )
        selected_formats = [
            item.removeprefix("format.")
            for item in selected_capabilities
            if item.startswith("format.")
        ]
        expected_format = selected_formats[0] if len(selected_formats) == 1 else None
        try:
            return render_material(
                material,
                self.run_dir,
                fidelity=fidelity,
                file_stem=stem,
                expected_format=expected_format,
                selected_capabilities=selected_capabilities,
            )
        except Exception as exc:  # never let rendering break the stage commit
            from presentation_agent.renderers.base import RenderResult

            fmt = str(material.get("format") or "ppt").lower()
            return RenderResult(status="error", fmt=fmt, fidelity=fidelity, detail=str(exc))

    @staticmethod
    def _safe_stem(topic: str) -> str:
        import re

        stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", str(topic)).strip("_")
        return (stem or "deliverable")[:40]

    def _build_context(self) -> SkillContext:
        scoped = self._scoped_global_reads()
        return SkillContext(
            global_state=scoped,
            style_guidance=[],
            skill_package=self.skill_package.to_dict(),
        )

    def _apply_memory_routing(
        self,
        context: SkillContext,
        input_data: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        gen_dimensions = (
            self.spec.state_contract.get("generation_memory_dimensions")
            or self.spec.memory_dimensions
        )
        config = read_json(self.root / "configs" / "agents.json", default={})
        limit = int(config.get("state_policy", {}).get("memory_retrieval_limit", 6))
        retrieved = MemoryRetriever(self.memory).retrieve(
            spec=self.spec,
            input_data=input_data,
            global_state=context.get("global_state", {}),
            dimensions=gen_dimensions,
            limit=limit,
            active_capabilities=self.skill_package.selected_capabilities,
        )
        routing_policy = build_routing_policy(
            spec=self.spec,
            input_data=input_data,
            global_state=context.get("global_state", {}),
            retrieved_memory=retrieved,
        )
        context["style_guidance"] = [row.to_prompt_line() for row in retrieved]
        context["retrieved_memory"] = [row.to_dict() for row in retrieved]
        context["routing_policy"] = routing_policy
        state["retrieved_memory"] = context["retrieved_memory"]
        state["routing_policy"] = routing_policy
        LearningEventStore(self.root, data_root=self.data_root).append(
            event_type="memory_retrieval",
            agent_id=self.spec.id,
            run_id=state.get("run_id"),
            source="step-runner",
            payload={
                "selected": context["retrieved_memory"],
                "routing_policy": routing_policy,
            },
        )

    def _load_input(self, state: dict[str, Any]) -> dict[str, Any]:
        input_path_str = state.get("input_path")
        if input_path_str:
            return load_agent_input(Path(input_path_str), self.spec)
        return {}

    @staticmethod
    def _assert_input_ready(input_data: dict[str, Any]) -> None:
        readiness = input_data.get("input_readiness", {})
        if not isinstance(readiness, dict) or readiness.get("status") != "blocked":
            return
        issues = readiness.get("blocking_issues", [])
        summary = "; ".join(
            f"{item.get('source_id')}:{item.get('field')}"
            for item in issues
            if isinstance(item, dict)
        )
        raise StepError(
            "输入完整性门禁阻断：需要完整材料的字段仅提供了 preview"
            + (f" ({summary})" if summary else "")
        )

    def _scoped_global_reads(self) -> dict[str, Any]:
        reads = self.spec.state_contract.get("global_reads", [])
        return {key: self.full_global_state[key] for key in reads if key in self.full_global_state}

    def _apply_global_writes(self, artifact: dict[str, Any]) -> bool:
        writes = self.spec.state_contract.get("global_writes", [])
        updated = dict(self.full_global_state)
        applied = False
        for key in writes:
            if key == "state_revisions":
                continue  # handled below
            if key in artifact and artifact[key] not in ("", [], {}, None):
                updated[key] = artifact[key]
                applied = True

        # state_revisions: storyline_design (and potentially later stages)
        # can revise upstream state values after the full story emerges
        if "state_revisions" in writes:
            revisions = artifact.get("state_revisions") or {}
            for key, value in revisions.items():
                if value not in ("", [], {}, None):
                    updated[key] = value
                    applied = True

        if applied:
            updated["updated_at"] = now_iso()
            write_json(self.run_dir.parent / "state.json", updated)
        return applied

    def _read_and_validate_output(self, filename: str, state: dict[str, Any]) -> dict[str, Any]:
        output_path = self.handoff_dir / filename
        if not output_path.exists():
            raise StepError(
                f"handoff 输出文件不存在: {output_path}。"
                "宿主模型应先读指令文件，产出 JSON 写入此路径后再 commit。"
            )
        text = output_path.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            try:
                from presentation_agent.llm.schema import extract_json
                data = extract_json(text)
            except Exception as e2:
                raise StepError(
                    f"handoff 输出无法解析为 JSON。原始错误: {exc}；"
                    f"容错解析失败: {e2}。请修复输出文件后重新 commit。"
                ) from exc
        if not isinstance(data, dict):
            raise StepError("handoff 输出必须是 JSON 对象")
        return data

    def _write_instruction(
        self,
        instruction_path: Path,
        output_path: Path,
        request: Any,
        kind: str,
    ) -> None:
        schema_ref = self._schema_quick_ref() if kind == "gen" else ""
        lines = [
            f"# Worker Agent：{self.spec.name} · {kind}",
            "",
            f"## 角色与 SOP",
            "",
            request.system.strip(),
            "",
            "## 任务输入与约束",
            "",
            request.user.strip(),
            "",
            "## 输出操作",
            "",
            f"按上述要求产出 **严格符合 {self.spec.output_schema}** 的单个 JSON 对象。",
            f"直接写入: `{output_path}`",
            "",
        ]
        if schema_ref:
            lines.extend([
                "## Schema 字段速查（必须逐条对齐）",
                "",
                "以下是从实际 JSON Schema 文件提取的必填字段及其类型。产出 JSON 前逐条核验：",
                "",
                schema_ref,
                "",
                "> ⚠️ 字段名、类型、嵌套结构必须与上述定义完全一致。",
                "> 不要仅凭指令文字描述推断字段类型。",
                "",
            ])
        lines.extend([
            "## JSON 安全写作指引",
            "",
            "- 产出含中文文案的 JSON 时，中文里的双引号使用 `「」` 或 `『』`，",
            "  绝不使用 ASCII `\"` —— 它会和 JSON 结构引号冲突导致解析失败。",
            "- 确保所有 JSON 数组和对象正确闭合（`]` / `}`）。",
            "- 建议：全部构造完成后在脑中用 `json.loads()` 校验一遍。",
            "",
            "只写 JSON，不要任何解释、前言或结语。",
        ])
        instruction_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _schema_quick_ref(self) -> str:
        """Extract required fields + types from the output schema for worker guidance."""
        schema = (self.skill_package.to_dict().get("schemas") or {}).get(
            self.spec.output_schema
        )
        if not schema:
            return ""
        required = schema.get("required", [])
        props = schema.get("properties", {})
        if not required and not props:
            return ""

        lines: list[str] = []
        lines.append(f"**Schema**: `{self.spec.output_schema}`\n")
        if required:
            lines.append("### 顶层必填字段")
        for key in required:
            ps = props.get(key, {})
            ptype = ps.get("type", "?")
            pdesc = ps.get("description", "")
            desc = f" — {pdesc}" if pdesc else ""
            lines.append(f"- `{key}`: **{ptype}**{desc}")
            # If array, show item required fields
            if ptype == "array":
                items = ps.get("items", {})
                item_req = items.get("required", [])
                if item_req:
                    item_props = items.get("properties", {})
                    for ir in item_req:
                        ip = item_props.get(ir, {})
                        lines.append(f"  - `[各元素].{ir}`: {ip.get('type', '?')}  "
                                     f"({ip.get('description', '')})".rstrip())

        # Non-required but commonly missing fields
        opt_objects = {
            k: v for k, v in props.items()
            if k not in required and isinstance(v, dict) and v.get("type") == "object"
        }
        if opt_objects:
            lines.append("\n### 重要可选字段（类型）")
            for key, ps in sorted(opt_objects.items()):
                ptype = ps.get("type", "?")
                subreq = ps.get("required", [])
                sub = f", required: {subreq}" if subreq else ""
                lines.append(f"- `{key}`: **{ptype}**{sub}")

        return "\n".join(lines)

    def _compose_review_instruction(self, artifact: dict[str, Any], input_data: dict[str, Any]) -> str:
        all_rubrics = self.skill_package.to_dict().get("rubrics", [])
        if not isinstance(all_rubrics, list):
            all_rubrics = []
        # Rubrics with a machine_check are already evaluated deterministically
        # by the schema gate; exclude them so the host model doesn't redo (and
        # possibly contradict) mechanical checks. Also strip the machine_check
        # block from the rest — it's noise for a human-style reviewer.
        machine_ids = {
            r.get("id")
            for r in all_rubrics
            if isinstance(r.get("machine_check"), dict) and r.get("id")
        }
        rubrics = [
            {k: v for k, v in r.items() if k != "machine_check"}
            for r in all_rubrics
            if r.get("id") not in machine_ids
        ]
        machine_note = (
            f"（以下 rubric 已由确定性机械校验覆盖，无需你重复判断：{sorted(machine_ids)}）"
            if machine_ids
            else ""
        )
        lines = [
            f"# {self.spec.name} · 审查（review）",
            "",
            "## 角色",
            "你是独立审查者，以干净视角逐条对照 rubrics 判断产物质量。",
            "P0 是必须返工的硬伤，P1 是质量改进项。只报真实命中的条目。",
            machine_note,
            "",
            "## 审查 rubrics（逐条对照）",
            "```json",
            json.dumps(rubrics, ensure_ascii=False, indent=2),
            "```",
            "",
            "## 待审查的 artifact",
            "```json",
            json.dumps(artifact, ensure_ascii=False, indent=2),
            "```",
        ]

        # Upstream signal check: detect contradictions / degradation / missing
        # inheritance from the upstream artifact's key premises.
        if input_data:
            signal = self._signal_snapshot(input_data)
            lines.extend([
                "",
                "## 上游信号检查（upstream signal）",
                "```json",
                json.dumps(signal, ensure_ascii=False, indent=2),
                "```",
                "",
                "检查上游 artifact 的关键信号是否在当前 artifact 中被正确地继承或演化：",
                "- **矛盾**：当前 artifact 的结论、预设受众、方向是否与上游的明确信号正面冲突？",
                "- **强度漂移**：当前 artifact 是否无依据升级，或无理由弱化上游判断？",
                "- **上游越界处置**：若上游判断超过证据边界，当前 artifact 是否提交 revision request，而不是静默继承或静默改写？",
                "- **缺失继承**：上游明确提出的约束（受众类型、页数上限、目标 action）是否被忽略？",
                "",
                "如果发现上述任一问题，以 rubric_id=UPSTREAM-SIG-001、dimension=上游信号 "
                "报一条 P1 objection。没有发现任何问题时无需报。",
            ])

        lines.extend([
            "",
            "## 输出要求",
            "产出一个 JSON 对象，格式:",
            '{"objections": [{"rubric_id","severity","dimension","message","evidence","suggestion"}]}',
            "没有任何命中时输出 {\"objections\": []}。",
            "",
            f"直接写入: `{self.handoff_dir / 'output_review.json'}`",
        ])
        return "\n".join(lines) + "\n"

    @staticmethod
    def _signal_snapshot(upstream: dict[str, Any]) -> dict[str, Any]:
        """Extract the signal-relevant fields from an upstream artifact."""
        return ArtifactReviewer._signal_snapshot(upstream)

    def _write_human_review(self, artifact: dict[str, Any], review: dict[str, Any]) -> None:
        lines = [
            f"# Human Review: {self.spec.name}",
            "",
            f"- agent_id: {self.spec.id}",
            f"- schema: {self.spec.output_schema}",
            "",
            "## Reviewer objections",
            "",
        ]
        objections = review.get("objections", [])
        if not objections:
            lines.append("- None")
        for o in objections:
            lines.append(
                f"- {o['severity']} / {o['dimension']}: {o['message']} "
                f"=> {o.get('suggestion', '')}"
            )
        lines.extend([
            "",
            "## Human decision",
            "",
            "- [ ] Approve and pass to next stage",
            "- [ ] Revise in this stage",
            "- [ ] Stop and rethink upstream",
            "",
            "## Artifact preview",
            "",
            "```json",
            json.dumps(artifact, ensure_ascii=False, indent=2),
            "```",
        ])
        (self.run_dir / "human_review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- result enrichment helpers (human-in-the-loop visibility) -----------

    def _artifact_preview(self, artifact: dict[str, Any], max_keys: int = 8) -> str:
        """Extract the most important fields for user-facing summary."""
        priority_keys = [
            "topic", "topic_summary", "report_brief", "decision_goal",
            "core_conclusion", "executive_summary", "story_angle",
            "message_pyramid", "ordering_rationale", "closing_intent",
            "leadline", "title", "page_question", "key_question",
            "headline", "hook", "opening", "closing", "summary",
        ]
        lines: list[str] = []
        shown = 0
        for key in priority_keys:
            val = artifact.get(key)
            if val is None or val == "" or val == []:
                continue
            text = self._truncate_value(val)
            lines.append(f"- **{key}**: {text}")
            shown += 1
            if shown >= max_keys:
                break
        # fallback: show any non-empty string/scalar keys
        if shown == 0:
            for key, val in artifact.items():
                if key in ("schema", "agent_id", "unit_type"):
                    continue
                if isinstance(val, (str, int, float, bool)) and val not in ("", None):
                    lines.append(f"- **{key}**: {self._truncate_value(val)}")
                    shown += 1
                    if shown >= max_keys:
                        break
        return "\n".join(lines) if lines else "（产物已保存，见 artifact.json）"

    @staticmethod
    def _truncate_value(val: Any, limit: int = 140) -> str:
        if isinstance(val, str):
            s = val.replace("\n", " ").strip()
            return s[:limit] + ("..." if len(s) > limit else "")
        if isinstance(val, (int, float, bool)):
            return str(val)
        if isinstance(val, list):
            inner = ", ".join(str(v)[:40] for v in val[:3])
            tail = f" 等{len(val)}项" if len(val) > 3 else ""
            return f"[{inner}{tail}]"
        if isinstance(val, dict):
            keys = list(val.keys())[:4]
            return "{" + ", ".join(keys[:4]) + ("..." if len(val) > 4 else "") + "}"
        return str(val)[:limit]

    def _review_summary(self, review_json: dict[str, Any]) -> str:
        objections = review_json.get("objections", [])
        p0_list = [o for o in objections if o.get("severity") == "P0"]
        p1_list = [o for o in objections if o.get("severity") == "P1"]
        if not objections:
            return "审查通过（无 objections）"
        parts: list[str] = []
        if p0_list:
            parts.append(f"**P0={len(p0_list)}**（必须返工）：")
            for o in p0_list[:3]:
                parts.append(f"  - [{o.get('dimension','')}] {o.get('message','')}")
            if len(p0_list) > 3:
                parts.append(f"  ... 等 {len(p0_list)} 项")
        if p1_list:
            parts.append(f"P1={len(p1_list)}（建议改进）：")
            for o in p1_list[:2]:
                parts.append(f"  - [{o.get('dimension','')}] {o.get('message','')}")
        return "\n".join(parts)

    @staticmethod
    def _objections_to_summary(report: Any, round_idx: int) -> str:
        p0 = getattr(report, "p0", [])
        p1 = getattr(report, "p1", [])
        lines = [f"审查轮次 {round_idx}：P0={len(p0)}，P1={len(p1)}"]
        for o in p0[:5]:
            source = "schema_gate" if "schema-" in str(o.id) else \
                     "memory_scan" if "memory-" in str(o.id) else "llm_review"
            lines.append(f"  P0 [{o.dimension}] [{source}]: {o.message}")
        for o in p1[:3]:
            lines.append(f"  P1 [{o.dimension}]: {o.message}")
        return "\n".join(lines)

    def _memory_diff(self, global_applied: bool) -> str:
        notes: list[str] = []
        if global_applied:
            writes = self.spec.state_contract.get("global_writes", [])
            notes.append(f"全局状态已更新（写入：{','.join(writes)}）")
        return "; ".join(notes) if notes else ""

    def _record_gen_memory(self, state: dict[str, Any]) -> str:
        """Report what memory guidance was loaded for this generation round."""
        dims = (
            self.spec.state_contract.get("generation_memory_dimensions")
            or self.spec.memory_dimensions
        )
        if not dims:
            return ""
        guidance = self.memory.generation_guidance(
            dims,
            active_capabilities=self.skill_package.selected_capabilities,
        )
        if guidance:
            return f"已注入 {len(guidance)} 条历史风格记忆（维度：{','.join(dims[:3])}）"
        return ""

    def _compose_stage_done_present(
        self,
        preview: str,
        review_summary: str,
        memory_notes: str,
        render_note: str = "",
    ) -> str:
        lines = [
            f"## 阶段执行完成：{self.spec.name}",
            "",
            "### 产物内容摘要",
            "",
            preview,
            "",
            "### 审查结果",
            "",
            review_summary,
        ]
        if render_note:
            lines.extend(["", "### 交付文件", "", render_note])
        if memory_notes:
            lines.extend(["", "### 记忆更新", "", memory_notes])
        lines.extend([
            "",
            "### 下一步",
            "",
            "请确认后推进到下一阶段，或要求本阶段返工。",
        ])
        return "\n".join(lines)

    # ---- state file I/O -----------------------------------------------------

    def _load_state(self) -> dict[str, Any]:
        return read_json(self.run_state_path, default={
            "status": "init", "current_step": "init", "round_index": 0,
            "p0_open": [], "p1_open": [], "produced_artifacts": [],
            "history": [], "created_at": now_iso(),
        })

    def _save_state(self, state: dict[str, Any]) -> None:
        write_json(self.run_state_path, state)

    def _write_state(self, state: dict[str, Any], step: str, message: str) -> None:
        state["updated_at"] = now_iso()
        state.setdefault("history", []).append({"at": state["updated_at"], "step": step, "message": message})
        write_json(self.run_state_path, state)

    @staticmethod
    def _instruction_path_for(step: str) -> Path:
        kind = {"awaiting_gen_output": "gen", "awaiting_review_output": "review", "awaiting_revise_output": "revise"}.get(step, "gen")
        return Path(f"handoff/instruction_{kind}.md")

    def _last_instruction_path(self, state: dict[str, Any]) -> Optional[str]:
        step = state.get("current_step", "")
        if step in ("awaiting_gen_output", "awaiting_review_output", "awaiting_revise_output"):
            return str(self.handoff_dir / StepRunner._instruction_path_for(step).name)
        return None

    def _last_output_path(self, state: dict[str, Any]) -> Optional[str]:
        step = state.get("current_step", "")
        kind_map = {"awaiting_gen_output": "gen", "awaiting_review_output": "review", "awaiting_revise_output": "revise"}
        kind = kind_map.get(step)
        if kind:
            return str(self.handoff_dir / f"output_{kind}.json")
        return None


# ---- Pipeline-level stepper ------------------------------------------------

class PipelineStepper:
    """Initialize and advance inline pipeline stages.

    Creates stage run directories with proper run_state.json pointing at the
    correct input artifact. Does NOT run any agent — that is driven by the
    host via StepRunner.
    """

    def __init__(self, root: Path, run_dir: Path, data_root: Optional[Path] = None) -> None:
        self.root = root
        self.run_dir = run_dir
        self.data_root = data_root or (root / "data")
        config = read_json(self.root / "configs" / "agents.json")
        self.specs = {item["id"]: AgentSpec.from_dict(item) for item in config["agents"]}
        self.ordered = PipelineStepper._ordered_specs(config, self.specs)

    @staticmethod
    def _ordered_specs(config: dict[str, Any], specs: dict[str, AgentSpec]) -> list[AgentSpec]:
        declared = config.get("pipeline", {}).get("stages")
        if declared:
            ordered = [specs[sid] for sid in declared if sid in specs]
            if ordered:
                return ordered
        return sorted(specs.values(), key=lambda s: s.stage)

    def init_pipeline(self, brief_path: Path) -> dict[str, Any]:
        """Create stage 1 run_dir with input pointing at brief_path."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        # write a pipeline-level state file
        pipeline_state = {
            "pipeline_id": self.run_dir.name,
            "current_stage": 1,
            "status": "running",
            "created_at": now_iso(),
        }
        write_json(self.run_dir / "pipeline_state.json", pipeline_state)
        return self._init_stage(0, Path(brief_path))

    def advance_stage(self) -> dict[str, Any]:
        """Create the next stage dir after the current one completes."""
        ps = read_json(self.run_dir / "pipeline_state.json", default={})
        current = int(ps.get("current_stage", 0))
        prev_spec = self.ordered[current - 1]
        artifact_path = self.run_dir / f"stage_{prev_spec.stage}_{prev_spec.id}" / "artifact.json"
        if not artifact_path.exists():
            raise StepError(
                f"阶段 {current} 的 artifact 不存在: {artifact_path}。"
                "前一阶段可能未完成，请先将其驱动到 done。"
            )
        result = self._init_stage(current, artifact_path)
        ps["current_stage"] = current + 1
        write_json(self.run_dir / "pipeline_state.json", ps)
        return result

    def pipeline_status(self) -> dict[str, Any]:
        ps = read_json(self.run_dir / "pipeline_state.json", default={})
        stages = []
        for i, spec in enumerate(self.ordered):
            stage_dir = self.run_dir / f"stage_{spec.stage}_{spec.id}"
            rs_path = stage_dir / "run_state.json"
            stage_status = "pending"
            if rs_path.exists():
                rs = read_json(rs_path)
                stage_status = rs.get("status", "unknown")
            stages.append({
                "index": i + 1,
                "agent_id": spec.id,
                "agent_name": spec.name,
                "status": stage_status,
                "dir": str(stage_dir),
            })
        return {
            "pipeline_id": ps.get("pipeline_id", self.run_dir.name),
            "current_stage": ps.get("current_stage", 1),
            "status": ps.get("status"),
            "stages": stages,
        }

    def _init_stage(self, stage_index: int, input_path: Path) -> dict[str, Any]:
        spec = self.ordered[stage_index]
        stage_dir = self.run_dir / f"stage_{spec.stage}_{spec.id}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        run_state = {
            "run_id": f"{spec.id}-{now_iso().replace(':', '').replace('+', 'Z')}",
            "agent_id": spec.id,
            "agent_name": spec.name,
            "stage": spec.stage,
            "status": "init",
            "current_step": "init",
            "round_index": 0,
            "max_revision_rounds": spec.max_revision_rounds or 2,
            "input_path": str(input_path),
            "output_dir": str(stage_dir),
            "p0_open": [],
            "p1_open": [],
            "produced_artifacts": [],
            "history": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        write_json(stage_dir / "run_state.json", run_state)
        (stage_dir / "handoff").mkdir(parents=True, exist_ok=True)

        return {
            "agent_id": spec.id,
            "agent_name": spec.name,
            "stage": spec.stage,
            "stage_dir": str(stage_dir),
            "input_path": str(input_path),
        }
