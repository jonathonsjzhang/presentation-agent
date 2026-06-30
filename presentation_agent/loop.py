from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from presentation_agent.input_loader import load_agent_input
from presentation_agent.capabilities.compiler import compile_skill_package
from presentation_agent.io import read_json, write_json
from presentation_agent.learning import LearningEventStore
from presentation_agent.llm.factory import build_llm_client
from presentation_agent.memory import MemoryStore
from presentation_agent.memory_retrieval import MemoryRetriever
from presentation_agent.models import AgentSpec, StopDecision, now_iso
from presentation_agent.review import ArtifactReviewer, StopChecker
from presentation_agent.routing import build_routing_policy
from presentation_agent.skills.base import SkillContext
from presentation_agent.skills.registry import get_skill


class LoopRunner:
    def __init__(self, root: Path, provider_override: Optional[str] = None) -> None:
        self.root = root
        self.provider_override = provider_override
        self.config = read_json(self.root / "configs" / "agents.json")
        self.specs = self._load_specs()
        self.generate_llm = build_llm_client(root, purpose="generate", provider_override=provider_override)
        self.review_llm = build_llm_client(root, purpose="review", provider_override=provider_override)
        self.reviewer = ArtifactReviewer(llm=self.review_llm)
        self.stop_checker = StopChecker(llm=self.review_llm)

    def list_agents(self) -> list[AgentSpec]:
        return sorted(self.specs.values(), key=lambda spec: spec.stage)

    def run(self, agent_id: str, input_path: Path, run_dir: Optional[Path] = None) -> dict[str, Any]:
        spec = self.specs[agent_id]
        max_rounds = self._max_revision_rounds(spec)
        skill = get_skill(spec.skill, llm=self.generate_llm)
        input_data = load_agent_input(input_path, spec)

        run_id = f"{spec.id}-{now_iso().replace(':', '').replace('+', 'Z')}-{uuid4().hex[:8]}"
        output_dir = run_dir or (self.root / "artifacts" / run_id)

        # Per-run state: every loop invocation gets its own state.json so that
        # different projects / briefs never cross-contaminate. On first use,
        # seed from the global template.
        global_state_path = output_dir / "state.json"
        if global_state_path.exists():
            full_global_state = read_json(global_state_path, default={})
        else:
            template = self.root / "data" / "global" / "state.json"
            seed = read_json(template, default={})
            full_global_state = dict(seed)
            write_json(global_state_path, full_global_state)

        memory = MemoryStore(self.root, spec.id)
        skill_package = compile_skill_package(self.root, spec, input_data)

        # Generation sees only the global keys this agent declares it reads, and
        # is guided by its (more focused) generation_memory_dimensions, falling
        # back to the agent's full memory_dimensions. This honors the v2 state
        # contract: "generation reads only selected dimensions; no link-follow".
        scoped_global_state = self._scoped_global_reads(spec, full_global_state)
        gen_dimensions = spec.state_contract.get("generation_memory_dimensions") or spec.memory_dimensions
        retrieved_memory = MemoryRetriever(memory).retrieve(
            spec=spec,
            input_data=input_data,
            global_state=scoped_global_state,
            dimensions=gen_dimensions,
            limit=int(self.config.get("state_policy", {}).get("memory_retrieval_limit", 6)),
            active_capabilities=skill_package.selected_capabilities,
        )
        routing_policy = build_routing_policy(
            spec=spec,
            input_data=input_data,
            global_state=scoped_global_state,
            retrieved_memory=retrieved_memory,
        )
        style_guidance = [row.to_prompt_line() for row in retrieved_memory]
        LearningEventStore(self.root).append(
            event_type="memory_retrieval",
            agent_id=spec.id,
            run_id=run_id,
            source="loop-runner",
            payload={
                "selected": [row.to_dict() for row in retrieved_memory],
                "routing_policy": routing_policy,
            },
        )
        context = SkillContext(
            global_state=scoped_global_state,
            style_guidance=style_guidance,
            retrieved_memory=[row.to_dict() for row in retrieved_memory],
            routing_policy=routing_policy,
            skill_package=skill_package.to_dict(),
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        run_state_path = output_dir / "run_state.json"
        run_state = self._initial_run_state(run_id, spec, input_path, output_dir)
        run_state["retrieved_memory"] = [row.to_dict() for row in retrieved_memory]
        run_state["routing_policy"] = routing_policy
        run_state["selected_capabilities"] = skill_package.selected_capabilities
        run_state["skill_fingerprint"] = skill_package.fingerprint
        run_state["skill_budget"] = skill_package.budget
        self._write_run_state(run_state_path, run_state, "start", "Loop started")

        artifact: dict[str, Any] = {}
        review = None
        decision = StopDecision(can_stop=False, reason="loop did not run")
        p0_objections = []

        # Optional multi-candidate: generate several isolated round-0 drafts with
        # different angles, review each, and let the best one enter the revise
        # loop. Default off (token-expensive); driven by agents.json optional_features.
        seed_artifact = self._maybe_multi_candidate(
            spec, skill, input_data, context, memory, skill_package, output_dir, run_state, run_state_path
        )

        for round_index in range(max_rounds + 1):
            run_state["current_step"] = "workflow"
            run_state["round_index"] = round_index
            self._write_run_state(run_state_path, run_state, "workflow", f"Starting round {round_index}")
            if round_index == 0:
                artifact = seed_artifact if seed_artifact is not None else skill.run(spec, input_data, context)
            else:
                artifact = skill.revise(spec, input_data, artifact, p0_objections, context)
            generation_budget = getattr(skill, "last_prompt_budget", {})
            if generation_budget:
                run_state.setdefault("prompt_budget", {})[
                    f"generation_round_{round_index}"
                ] = dict(generation_budget)

            draft_path = output_dir / f"draft_round_{round_index}.json"
            write_json(draft_path, artifact)
            run_state["produced_artifacts"].append(str(draft_path))
            self._write_run_state(run_state_path, run_state, "workflow", f"Draft round {round_index} written")

            run_state["current_step"] = "review"
            review = self.reviewer.review(spec, artifact, memory, skill_package.to_dict(),
                                           upstream_artifact=input_data)
            if self.reviewer.last_prompt_budget:
                run_state.setdefault("prompt_budget", {})[
                    f"review_round_{round_index}"
                ] = dict(self.reviewer.last_prompt_budget)
            review_path = output_dir / f"review_round_{round_index}.json"
            write_json(review_path, review.to_dict())
            run_state["produced_artifacts"].append(str(review_path))
            run_state["p0_open"] = [obj.to_dict() for obj in review.p0]
            run_state["p1_open"] = [obj.to_dict() for obj in review.p1]
            new_learning = [obj for obj in review.objections if not obj.id.startswith("P1-memory-")]
            log_ids = memory.record_objections(run_id, new_learning)
            run_state["feedback_logged"].extend(log_ids)
            self._write_run_state(
                run_state_path,
                run_state,
                "review",
                f"Review round {round_index}: P0={len(review.p0)}, P1={len(review.p1)}",
            )

            run_state["current_step"] = "stop_check"
            decision = self.stop_checker.check(spec, artifact, review)
            stop_path = output_dir / f"stop_decision_round_{round_index}.json"
            write_json(stop_path, decision.to_dict())
            run_state["produced_artifacts"].append(str(stop_path))
            run_state["stop_decision"] = decision.to_dict()
            if decision.can_stop:
                run_state["next_action"] = "human_review"
                self._write_run_state(run_state_path, run_state, "stop_check", decision.reason)
                break
            p0_objections = review.p0
            run_state["next_action"] = "revise" if round_index < max_rounds else "human_review"
            self._write_run_state(run_state_path, run_state, "stop_check", decision.reason)

        status = "pending_human_review" if decision.can_stop else "blocked_needs_human"
        run_state["status"] = status
        run_state["current_step"] = "human_review"
        run_state["next_action"] = "await_human_decision"
        result = {
            "run_id": run_id,
            "agent_id": spec.id,
            "status": status,
            "output_dir": str(output_dir),
            "artifact_path": str(output_dir / "artifact.json"),
            "review_path": str(output_dir / "review.json"),
            "run_state_path": str(run_state_path),
            "human_review_path": str(output_dir / "human_review.md"),
            "stop_decision": decision.to_dict(),
        }
        write_json(output_dir / "artifact.json", artifact)
        # Only propagate global state from a clean (P0-free) artifact, so a
        # blocked stage cannot poison downstream agents' shared state.
        if decision.can_stop:
            written_keys = self._apply_global_writes(spec, artifact, global_state_path, full_global_state)
            run_state["global_writes_applied"] = written_keys
        if review is not None:
            write_json(output_dir / "review.json", review.to_dict())
        write_json(output_dir / "loop_result.json", result)
        self._write_human_review(output_dir, spec, result, artifact, review.to_dict() if review else {})
        run_state["produced_artifacts"].extend(
            [
                str(output_dir / "artifact.json"),
                str(output_dir / "review.json"),
                str(output_dir / "loop_result.json"),
                str(output_dir / "human_review.md"),
            ]
        )
        self._write_run_state(run_state_path, run_state, "human_review", "Waiting for human decision")
        return result

    def _load_specs(self) -> dict[str, AgentSpec]:
        return {item["id"]: AgentSpec.from_dict(item) for item in self.config["agents"]}

    def _multi_candidate_config(self, spec: AgentSpec) -> Optional[dict[str, Any]]:
        """Return the multi_candidate config if enabled for this agent, else None.

        Off unless agents.json optional_features.multi_candidate is an object with
        enabled_by_default true. A plain `false` (or missing) keeps single-draft.
        """
        feature = spec.optional_features.get("multi_candidate")
        if isinstance(feature, dict) and feature.get("enabled_by_default"):
            return feature
        return None

    def _candidate_hints(self, count: int, spec: Optional[AgentSpec] = None) -> list[str]:
        """Distinct angle prompts so candidates explore genuinely different framings.

        A small fixed catalog covers the common creative-diverge patterns; when the
        request exceeds the catalog the remaining slots use agent-aware generic angles.
        """
        catalog: list[str] = [
            "采用多因多果角度：不止列出单一解释，同时考虑 2-3 个竞争性归因，对比证据强度。",
            "采用逆向假设角度：先假设现状已不成立/最坏情形，反向推导支持当前判断的最低证据门槛。",
            "采用第三人称批判角度：把自己当作外部顾问/投资人，对本报告的核心主张挑出最尖锐的 3 个问题再展开。",
        ]
        generic = [
            "采用最高风险优先角度：优先回应最可能被追问或质疑的点，把论证防线前移。",
            "采用最小可行推论角度：只保留能被当前证据直接支撑的判断，所有延伸推论显式标注为假设。",
            "采用反事实推演角度：假设一个关键前提改变，重新推演对核心结论的影响。",
        ]
        result = list(catalog)
        remaining = count - len(result)
        if remaining > 0:
            result.extend(generic[:remaining])
        if len(result) < count:
            result.extend(f"采用第 {i} 种自定义角度，与上述均不同。" for i in range(len(result) + 1, count + 1))
        return result[:count]

    def _maybe_multi_candidate(
        self,
        spec: AgentSpec,
        skill: Any,
        input_data: dict[str, Any],
        context: SkillContext,
        memory: MemoryStore,
        skill_package: Any,
        output_dir: Path,
        run_state: dict[str, Any],
        run_state_path: Path,
    ) -> Optional[dict[str, Any]]:
        config = self._multi_candidate_config(spec)
        if config is None:
            return None

        count = min(int(config.get("max_candidates", 3)), len(self._candidate_hints(3)) + 3)
        hints = self._candidate_hints(count, spec=spec)
        candidates_dir = output_dir / "candidates"
        candidates_dir.mkdir(parents=True, exist_ok=True)

        scored: list[dict[str, Any]] = []
        for index, hint in enumerate(hints, start=1):
            artifact = skill.run(spec, input_data, context, candidate_hint=hint)
            artifact = self._stamp_identity(artifact, spec)
            review = self.reviewer.review(spec, artifact, memory, skill_package.to_dict(),
                                           upstream_artifact=input_data)
            cand_path = candidates_dir / f"candidate_{index}.json"
            write_json(cand_path, artifact)
            write_json(candidates_dir / f"candidate_{index}_review.json", review.to_dict())
            scored.append(
                {
                    "index": index,
                    "hint": hint,
                    "p0": len(review.p0),
                    "p1": len(review.p1),
                    "artifact": artifact,
                    "path": str(cand_path),
                }
            )

        # Selection: fewest P0 first, then fewest P1. Ties keep the earlier angle.
        scored.sort(key=lambda c: (c["p0"], c["p1"], c["index"]))
        winner = scored[0]
        run_state["multi_candidate"] = {
            "enabled": True,
            "count": count,
            "selection_owner": config.get("selection_owner", "review_sub_agent_then_human"),
            "candidates": [
                {"index": c["index"], "p0": c["p0"], "p1": c["p1"], "path": c["path"]} for c in scored
            ],
            "selected_index": winner["index"],
        }
        self._write_run_state(
            run_state_path,
            run_state,
            "workflow",
            f"Multi-candidate: generated {count}, selected #{winner['index']} "
            f"(P0={winner['p0']}, P1={winner['p1']})",
        )
        return winner["artifact"]

    def _stamp_identity(self, artifact: dict[str, Any], spec: AgentSpec) -> dict[str, Any]:
        if isinstance(artifact, dict):
            artifact.setdefault("agent_id", spec.id)
            artifact.setdefault("schema", spec.output_schema)
        return artifact

    def _max_revision_rounds(self, spec: AgentSpec) -> int:
        """Per-agent override, else the pipeline-level default from agents.json."""
        if spec.max_revision_rounds:
            return spec.max_revision_rounds
        return int(self.config.get("pipeline", {}).get("default_max_revision_rounds", 2))

    def _scoped_global_reads(self, spec: AgentSpec, full_state: dict[str, Any]) -> dict[str, Any]:
        """Return only the global_state keys this agent declares it reads.

        If the agent declares no reads, it sees an empty dict (explicit > implicit),
        keeping generation context tight and the read/write contract enforceable.
        """
        reads = spec.state_contract.get("global_reads", [])
        return {key: full_state[key] for key in reads if key in full_state}

    def _apply_global_writes(
        self,
        spec: AgentSpec,
        artifact: dict[str, Any],
        global_state_path: Path,
        full_state: dict[str, Any],
    ) -> list[str]:
        """Write back the global keys this agent owns, sourced from its artifact.

        A key is updated only if the artifact actually carries it, so a stage
        never blanks out shared state it did not produce.

        Supports ``state_revisions``: when an agent declares ``state_revisions``
        in its ``global_writes``, each key inside ``artifact.state_revisions``
        is unwrapped and applied to the corresponding top-level state slot.
        """
        writes = spec.state_contract.get("global_writes", [])
        applied: list[str] = []
        updated = dict(full_state)
        for key in writes:
            if key == "state_revisions":
                continue  # unwrapped below
            if key in artifact and artifact[key] not in ("", [], {}, None):
                updated[key] = artifact[key]
                applied.append(key)

        if "state_revisions" in writes:
            revisions = artifact.get("state_revisions") or {}
            for key, value in revisions.items():
                if value not in ("", [], {}, None):
                    updated[key] = value
                    applied.append(f"state_revisions.{key}")

        if applied:
            updated["updated_at"] = now_iso()
            write_json(global_state_path, updated)
        return applied

    def _initial_run_state(
        self,
        run_id: str,
        spec: AgentSpec,
        input_path: Path,
        output_dir: Path,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "agent_id": spec.id,
            "agent_name": spec.name,
            "status": "running",
            "current_step": "start",
            "round_index": 0,
            "max_revision_rounds": self._max_revision_rounds(spec),
            "input_path": str(input_path),
            "output_dir": str(output_dir),
            "p0_open": [],
            "p1_open": [],
            "human_decision": None,
            "next_action": "workflow",
            "produced_artifacts": [],
            "feedback_logged": [],
            "stop_decision": None,
            "history": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }

    def _write_run_state(
        self,
        path: Path,
        run_state: dict[str, Any],
        step: str,
        message: str,
    ) -> None:
        run_state["updated_at"] = now_iso()
        run_state["history"].append({"at": run_state["updated_at"], "step": step, "message": message})
        write_json(path, run_state)

    def _write_human_review(
        self,
        output_dir: Path,
        spec: AgentSpec,
        result: dict[str, Any],
        artifact: dict[str, Any],
        review: dict[str, Any],
    ) -> None:
        lines = [
            f"# Human Review: {spec.name}",
            "",
            f"- run_id: {result['run_id']}",
            f"- status: {result['status']}",
            f"- artifact: {result['artifact_path']}",
            f"- review: {result['review_path']}",
            "",
            "## Reviewer objections",
            "",
        ]
        objections = review.get("objections", [])
        if not objections:
            lines.append("- None")
        for objection in objections:
            lines.append(
                f"- {objection['severity']} / {objection['dimension']}: {objection['message']} "
                f"=> {objection.get('suggestion', '')}"
            )
        lines.extend(
            [
                "",
                "## Human decision",
                "",
                "- [ ] Approve and pass to next agent",
                "- [ ] Revise in this agent",
                "- [ ] Stop and rethink upstream manually",
                "",
                "## Human feedback to record",
                "",
                "- dimension:",
                "- problem:",
                "- reason:",
                "- change:",
                "",
                "## Artifact preview",
                "",
                "```json",
            ]
        )
        import json

        lines.append(json.dumps(artifact, ensure_ascii=False, indent=2))
        lines.append("```")
        (output_dir / "human_review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
