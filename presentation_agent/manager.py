from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from presentation_agent.cross_review import CrossStageReviewer
from presentation_agent.io import append_jsonl, read_json, write_json
from presentation_agent.memory import MemoryStore
from presentation_agent.models import now_iso


class ManagerController:
    """Project-level orchestration layer for report runs.

    The manager records plans and decisions around the existing pipeline. It
    does not generate stage artifacts and does not bypass StepRunner or
    PipelineStepper.
    """

    MEMORY_DIMENSIONS = ["调度", "阶段依赖", "返工", "人审偏好", "跨阶段一致性", "并行策略"]

    def __init__(self, root: Path, run_dir: Path, data_root: Optional[Path] = None) -> None:
        self.root = root
        self.run_dir = run_dir
        self.data_root = data_root or (root / "data")
        self.state_path = run_dir / "manager_state.json"
        self.plan_path = run_dir / "manager_plan.json"
        self.decisions_path = run_dir / "manager_decisions.jsonl"
        self.memory = MemoryStore(root, "manager", data_root=self.data_root)
        self.cross_reviewer = CrossStageReviewer(root, run_dir)

    def initialize_run(
        self,
        *,
        brief_path: Path,
        first_stage: dict[str, Any],
        instruction: dict[str, Any],
    ) -> dict[str, Any]:
        config = read_json(self.root / "configs" / "agents.json", default={})
        stages = list(config.get("pipeline", {}).get("stages", []))
        memory_guidance = self.memory.generation_guidance(self.MEMORY_DIMENSIONS, limit=6)

        plan = {
            "version": "manager_plan.v1",
            "mode": "sequential_with_manager",
            "brief_path": str(brief_path),
            "stages": stages,
            "human_review_required": bool(config.get("pipeline", {}).get("human_review_required", True)),
            "initial_strategy": {
                "principle": "串行主干，保留后续局部并行和 sub-agent 调度扩展点",
                "manager_memory_guidance": memory_guidance,
            },
            "created_at": now_iso(),
        }
        write_json(self.plan_path, plan)

        state = {
            "version": "manager_state.v1",
            "run_id": self.run_dir.name,
            "mode": "manager_sequential_v1",
            "status": "running",
            "current_stage": first_stage.get("agent_id"),
            "current_stage_dir": first_stage.get("stage_dir"),
            "risk_flags": [],
            "memory_used": memory_guidance,
            "last_instruction": instruction,
            "last_decision": {
                "decision": "start",
                "reason": "report run initialized under manager control",
                "at": now_iso(),
            },
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        write_json(self.state_path, state)
        self._append_decision("start", "report run initialized", {
            "brief_path": str(brief_path),
            "first_stage": first_stage,
            "instruction": instruction,
        })
        return state

    def record_instruction(self, *, stage_dir: Path, stage_status: dict[str, Any], instruction: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state()
        state["current_stage"] = stage_status.get("agent_id")
        state["current_stage_dir"] = str(stage_dir)
        state["last_instruction"] = instruction
        state["last_decision"] = {
            "decision": "prepare_instruction",
            "reason": "stage instruction prepared or reused",
            "at": now_iso(),
        }
        self._write_state(state)
        self._append_decision("prepare_instruction", "stage instruction prepared or reused", {
            "stage": stage_status,
            "instruction": instruction,
        })
        return state

    def record_submit(self, *, stage_dir: Path, stage_status: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state()
        state["current_stage"] = stage_status.get("agent_id")
        state["current_stage_dir"] = str(stage_dir)
        state["last_submit_result"] = result

        cross_review = None
        risk_flags = list(state.get("risk_flags", []))
        if result.get("step") == "done":
            cross_review = self.cross_reviewer.review_stage(stage_dir)
            state["last_cross_stage_review"] = cross_review
            for issue in cross_review.get("issues", []):
                risk_flags.append({
                    "stage": stage_status.get("agent_id"),
                    "severity": issue.get("severity", "P1"),
                    "message": issue.get("message", ""),
                    "suggested_owner": issue.get("suggested_owner"),
                    "at": now_iso(),
                })
        state["risk_flags"] = risk_flags[-20:]
        state["last_decision"] = {
            "decision": "stage_done" if result.get("step") == "done" else "continue_stage",
            "reason": "stage reached human review" if result.get("step") == "done" else "stage loop continues",
            "at": now_iso(),
        }
        self._write_state(state)
        self._append_decision(state["last_decision"]["decision"], state["last_decision"]["reason"], {
            "stage": stage_status,
            "result_step": result.get("step"),
            "cross_stage_review": cross_review,
        })
        return state

    def record_approval(self, *, stage_dir: Path, stage_status: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state()
        state["current_stage"] = stage_status.get("agent_id")
        state["current_stage_dir"] = str(stage_dir)
        state["last_decision"] = {
            "decision": "approve_stage",
            "reason": "human approved current stage",
            "at": now_iso(),
        }
        self._write_state(state)
        self._append_decision("approve_stage", "human approved current stage", {
            "stage": stage_status,
        })
        return state

    def record_advance(self, *, next_stage: dict[str, Any], instruction: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state()
        state["current_stage"] = next_stage.get("agent_id")
        state["current_stage_dir"] = next_stage.get("stage_dir")
        state["last_instruction"] = instruction
        state["last_decision"] = {
            "decision": "advance_stage",
            "reason": "pipeline advanced to next stage",
            "at": now_iso(),
        }
        self._write_state(state)
        self._append_decision("advance_stage", "pipeline advanced to next stage", {
            "next_stage": next_stage,
            "instruction": instruction,
        })
        return state

    def mark_completed(self) -> dict[str, Any]:
        state = self._load_state()
        state["status"] = "completed"
        state["last_decision"] = {
            "decision": "complete",
            "reason": "all stages approved",
            "at": now_iso(),
        }
        self._write_state(state)
        self._append_decision("complete", "all stages approved", {})
        return state

    def status(self) -> dict[str, Any]:
        return {
            "state": read_json(self.state_path, default={}),
            "plan": read_json(self.plan_path, default={}),
            "decisions_path": str(self.decisions_path),
        }

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            return read_json(self.state_path, default={})
        return {
            "version": "manager_state.v1",
            "run_id": self.run_dir.name,
            "mode": "manager_sequential_v1",
            "status": "running",
            "risk_flags": [],
            "memory_used": [],
            "created_at": now_iso(),
        }

    def _write_state(self, state: dict[str, Any]) -> None:
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
