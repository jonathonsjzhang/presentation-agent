from __future__ import annotations

import argparse
import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from presentation_agent.capabilities.registry import CapabilityRegistry
from presentation_agent.io import read_json, write_json
from presentation_agent.learning import LearningEventStore, compare_material_versions
from presentation_agent.loop import LoopRunner
from presentation_agent.memory import MemoryStore
from presentation_agent.models import now_iso
from presentation_agent.skill_package import load_skill_package
from presentation_agent.step import PipelineStepper, StepError, StepRunner


STATIC_DIR = Path(__file__).resolve().parent / "web_static"

EDITABLE_PREFIXES = (
    "configs/",
    "data/",
    "examples/",
    "docs/",
    "skills/",
    "presentation_agent/skills/",
)
READABLE_PREFIXES = EDITABLE_PREFIXES + (
    "artifacts/",
    "outputs/",
    "presentation_agent/",
    "README.md",
    "汇报助手系统设计方案.md",
)


class WebApp:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def handle_get(self, path: str, query: dict[str, list[str]]) -> tuple[int, Any, str]:
        if path == "/api/overview":
            return self.json(self.overview())
        if path == "/api/files":
            return self.json({"files": self.list_files()})
        if path == "/api/file":
            rel_path = self.required_query(query, "path")
            return self.json(self.read_file(rel_path))
        if path == "/api/artifacts":
            return self.json({"runs": self.list_runs()})
        if path == "/api/artifact":
            rel_path = self.required_query(query, "path")
            return self.json(self.read_artifact(rel_path))
        if path == "/api/learning":
            return self.json(self.learning_overview())
        if path == "/api/step/status":
            return self.json(self.step_status(query))
        raise NotFound(f"Unknown API route: {path}")

    def handle_post(self, path: str, body: dict[str, Any]) -> tuple[int, Any, str]:
        if path == "/api/file":
            return self.json(self.save_file(str(body.get("path", "")), str(body.get("content", ""))))
        if path == "/api/run":
            return self.json(self.run_agent(body))
        if path == "/api/feedback":
            return self.json(self.record_feedback(body))
        if path == "/api/feedback-text":
            return self.json(self.record_feedback_text(body))
        if path == "/api/human-review":
            return self.json(self.record_human_review(body))
        if path == "/api/memory/dream":
            return self.json(self.dream_memory(body))
        if path == "/api/memory/success":
            return self.json(self.record_success_memory(body))
        if path == "/api/memory/compare":
            return self.json(self.compare_reflect(body))
        if path == "/api/command":
            return self.json(self.run_command(str(body.get("command", "")).strip()))
        if path == "/api/step/init":
            return self.json(self.step_init(body))
        if path == "/api/step/prepare":
            return self.json(self.step_prepare(body))
        if path == "/api/step/output":
            return self.json(self.step_write_output(body))
        if path == "/api/step/commit":
            return self.json(self.step_commit(body))
        if path == "/api/step/advance":
            return self.json(self.step_advance(body))
        raise NotFound(f"Unknown API route: {path}")

    def overview(self) -> dict[str, Any]:
        runner = LoopRunner(self.root)
        agents = []
        control_plane = runner.config.get("control_plane", {})
        if control_plane:
            manager_package = load_skill_package(self.root, "manager")
            agents.append({
                "id": "manager",
                "name": control_plane.get("name", "Manager"),
                "stage": 0,
                "skill": "manager",
                "description": "定义汇报任务、规划和派发 Worker、验收、返工与完结。",
                "previous_agent_id": None,
                "next_agent_id": None,
                "input_schema": control_plane.get("input_schema", "manager_context.v1"),
                "output_schema": control_plane.get("output_schema", "manager_decision.v1"),
                "input_contract": {"required_inputs": ["raw brief", "Worker capabilities", "run state"]},
                "output_contract": {
                    "primary_artifact": "Manager decision",
                    "required_handoff_fields": ["report_charter", "task_packet", "acceptance_report"],
                },
                "memory_dimensions": control_plane.get("memory_dimensions", []),
                "state": {"agent_memory_scope": "manager_only"},
                "harness": {
                    "skill_package": "skills/manager",
                    "runtime_adapter": "manager_agent_runtime",
                    "review_policy": "schema_validation + structured_action_execution",
                    "implementation_status": "implemented",
                },
                "skill_package": {
                    "exists": manager_package.exists,
                    "path": self.to_rel(manager_package.path),
                    "schema_count": len(manager_package.schemas),
                },
                "implemented": True,
            })
        active_workers = set(runner.config.get("pipeline", {}).get("stages", []))
        for spec in runner.list_agents():
            if spec.id not in active_workers:
                continue
            skill_package = load_skill_package(self.root, spec.id)
            agent = spec.to_dict()
            agent["skill_package"] = {
                "exists": skill_package.exists,
                "path": self.to_rel(skill_package.path) if skill_package.exists else f"skills/{spec.id}",
                "schema_count": len(skill_package.schemas),
            }
            agent["implemented"] = True
            agents.append(agent)
        core_agents = [
            spec.id for spec in runner.list_agents() if spec.id in active_workers
        ]
        registry = CapabilityRegistry(self.root)
        return {
            "agents": agents,
            "pipeline": runner.config.get("pipeline", {}),
            "capabilities": {
                **read_json(
                    self.root / "configs" / "capabilities.json", default={}
                ),
                "packages": registry.inventory(core_agents),
            },
            "state_policy": runner.config.get("state_policy", {}),
            "loop_steps": runner.config.get("loop_steps", []),
            "latest_runs": self.list_runs(limit=6),
            "editable_prefixes": list(EDITABLE_PREFIXES),
        }

    def learning_overview(self) -> dict[str, Any]:
        runner = LoopRunner(self.root)
        global_state_path = self.root / "data" / "global" / "state.json"
        global_state = read_json(global_state_path, default={})
        agents: list[dict[str, Any]] = []
        recent_logs: list[dict[str, Any]] = []
        total_memory = 0
        event_log = self._read_event_log()
        event_counts: dict[str, int] = {}
        for event in event_log:
            event_type = str(event.get("event_type") or "unknown")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        control = runner.config.get("control_plane", {})
        active = set(runner.config.get("pipeline", {}).get("stages", []))
        memory_specs = []
        if control:
            memory_specs.append((
                "manager",
                control.get("name", "Manager"),
                0,
                control.get("memory_dimensions", []),
            ))
        memory_specs.extend(
            (spec.id, spec.name, spec.stage, spec.memory_dimensions)
            for spec in runner.list_agents()
            if spec.id in active
        )

        for agent_id, agent_name, stage, dimensions in memory_specs:
            store = MemoryStore(self.root, agent_id)
            items = [item.to_dict() for item in store.load_items()]
            logs = self._read_learning_log(store.log_path)
            lint = store.lint()
            total_memory += len(items)
            for entry in logs:
                entry.setdefault("agent_id", agent_id)
                recent_logs.append(entry)
            agents.append(
                {
                    "id": agent_id,
                    "name": agent_name,
                    "stage": stage,
                    "memory_dimensions": dimensions,
                    "memory_count": len(items),
                    "learning_log_count": len(logs),
                    "lint": lint,
                    "recent_memory": items[-5:],
                    "recent_logs": logs[-5:],
                }
            )

        recent_logs.sort(key=lambda item: str(item.get("date", "")), reverse=True)
        return {
            "global_state": global_state,
            "global_state_path": self.to_rel(global_state_path),
            "state_policy": runner.config.get("state_policy", {}),
            "totals": {
                "memory_items": total_memory,
                "learning_logs": len(recent_logs),
                "learning_events": len(event_log),
            },
            "event_counts": event_counts,
            "recent_events": event_log[-20:][::-1],
            "agents": agents,
            "recent_logs": recent_logs[:20],
        }

    def list_files(self) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        for prefix in READABLE_PREFIXES:
            target = self.root / prefix
            if target.is_file():
                rel = self.to_rel(target)
                files.append({"path": rel, "editable": self.is_editable(rel), "kind": "file"})
                continue
            if not target.exists():
                continue
            for path in target.rglob("*"):
                if not path.is_file() or "__pycache__" in path.parts:
                    continue
                if any(part.startswith(".") for part in path.relative_to(self.root).parts):
                    continue
                rel = self.to_rel(path)
                if path.stat().st_size > 600_000:
                    continue
                files.append({"path": rel, "editable": self.is_editable(rel), "kind": self.kind_for(rel)})
        return sorted(files, key=lambda item: item["path"])

    def read_file(self, rel_path: str) -> dict[str, Any]:
        path = self.safe_path(rel_path, READABLE_PREFIXES)
        content = path.read_text(encoding="utf-8")
        return {"path": self.to_rel(path), "content": content, "editable": self.is_editable(self.to_rel(path))}

    def save_file(self, rel_path: str, content: str) -> dict[str, Any]:
        path = self.safe_path(rel_path, EDITABLE_PREFIXES)
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": self.to_rel(path)}

    def run_agent(self, body: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(body.get("agent_id") or "storyline")
        input_path = Path(str(body.get("input_path") or "examples/storyline_input.json"))
        inline_input = str(body.get("input_json") or "").strip()
        run_name = self.slug(str(body.get("run_name") or "ui_run"))
        run_dir = self.root / "artifacts" / run_name

        if inline_input:
            parsed = json.loads(inline_input)
            input_dir = self.root / "artifacts" / "_ui_inputs"
            input_dir.mkdir(parents=True, exist_ok=True)
            input_path = input_dir / f"{run_name}.json"
            write_json(input_path, parsed)
        else:
            input_path = self.safe_path(str(input_path), ("examples/", "artifacts/"))

        runner = LoopRunner(self.root)
        result = runner.run(agent_id, input_path, run_dir)
        result["latest_runs"] = self.list_runs(limit=6)
        return result

    def record_feedback(self, body: dict[str, Any]) -> dict[str, Any]:
        required = ["agent_id", "dimension", "problem", "change"]
        missing = [field for field in required if not str(body.get(field, "")).strip()]
        if missing:
            raise BadRequest(f"Missing required fields: {', '.join(missing)}")
        store = MemoryStore(self.root, str(body["agent_id"]))
        log_id = store.record_feedback(
            scope=str(body.get("scope") or "agent"),
            dimension=str(body["dimension"]),
            trigger_scene=str(body.get("scene") or "ui_feedback"),
            problem=str(body["problem"]),
            reason=str(body.get("reason") or ""),
            change=str(body["change"]),
            source="human-ui",
            owner=str(body.get("capability_owner") or "").strip() or None,
            applies_to=body.get("applies_to")
            if isinstance(body.get("applies_to"), dict)
            else None,
        )
        return {"ok": True, "log_id": log_id, "memory": [item.to_dict() for item in store.load_items()]}

    def record_feedback_text(self, body: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(body.get("agent_id") or "").strip()
        text = str(body.get("text") or "").strip()
        if not agent_id:
            raise BadRequest("Missing agent_id")
        if not text:
            raise BadRequest("Missing text")
        store = MemoryStore(self.root, agent_id)
        parsed = store.record_text_feedback(
            text=text,
            trigger_scene=str(body.get("scene") or "human_review_chat"),
            source=str(body.get("source") or "human-chat"),
            dimension=str(body.get("dimension") or "").strip() or None,
            scope=str(body.get("scope") or "agent"),
        )
        run_state_ref = str(body.get("run_state_path") or "").strip()
        if run_state_ref:
            run_state_path = self.safe_path(run_state_ref, ("artifacts/",))
            run_state = read_json(run_state_path)
            run_state.setdefault("feedback_logged", []).append(parsed["log_id"])
            run_state.setdefault("history", []).append(
                {
                    "at": now_iso(),
                    "step": "learning_capture",
                    "message": f"Chat feedback recorded: {parsed['log_id']}",
                }
            )
            run_state["updated_at"] = now_iso()
            write_json(run_state_path, run_state)
        return {
            "ok": True,
            "feedback": parsed,
            "memory": [item.to_dict() for item in store.load_items()],
            "learning": self.learning_overview(),
        }

    def record_human_review(self, body: dict[str, Any]) -> dict[str, Any]:
        run_state_ref = str(body.get("run_state_path") or body.get("run_state") or "").strip()
        if not run_state_ref and body.get("run_dir"):
            run_state_ref = str(Path(str(body["run_dir"])) / "run_state.json")
        if not run_state_ref:
            raise BadRequest("Missing run_state_path")

        run_state_path = self.safe_path(run_state_ref, ("artifacts/",))
        run_state = read_json(run_state_path)
        agent_id = str(body.get("agent_id") or run_state.get("agent_id") or "").strip()
        if not agent_id:
            raise BadRequest("Missing agent_id")

        decision = str(body.get("decision") or "").strip().lower()
        allowed = {"approve", "revise", "stop"}
        if decision not in allowed:
            raise BadRequest(f"decision must be one of: {', '.join(sorted(allowed))}")

        feedback = dict(body.get("feedback") or {})
        log_ids: list[str] = []
        has_feedback = any(str(feedback.get(field, "")).strip() for field in ("dimension", "problem", "change"))
        if has_feedback:
            missing = [field for field in ("dimension", "problem", "change") if not str(feedback.get(field, "")).strip()]
            if missing:
                raise BadRequest(f"Feedback missing required fields: {', '.join(missing)}")
            store = MemoryStore(self.root, agent_id)
            log_ids.append(
                store.record_feedback(
                    scope=str(feedback.get("scope") or "agent"),
                    dimension=str(feedback["dimension"]),
                    trigger_scene=str(feedback.get("scene") or f"human_review:{run_state.get('run_id', run_state_path.parent.name)}"),
                    problem=str(feedback["problem"]),
                    reason=str(feedback.get("reason") or ""),
                    change=str(feedback["change"]),
                    source="human-review",
                )
            )

        timestamp = now_iso()
        decision_record = {
            "at": timestamp,
            "decision": decision,
            "reviewer": str(body.get("reviewer") or "human"),
            "notes": str(body.get("notes") or ""),
            "feedback_log_ids": log_ids,
        }
        run_state["human_decision"] = decision_record
        run_state["status"] = {
            "approve": "approved_by_human",
            "revise": "human_requested_revision",
            "stop": "stopped_by_human",
        }[decision]
        run_state["next_action"] = {
            "approve": "advance_to_next_agent",
            "revise": "revise_current_agent",
            "stop": "stop_pipeline",
        }[decision]
        run_state.setdefault("feedback_logged", []).extend(log_ids)
        run_state.setdefault("history", []).append(
            {
                "at": timestamp,
                "step": "learning_capture",
                "message": f"Human review decision={decision}; feedback_logged={len(log_ids)}",
            }
        )
        run_state["current_step"] = "learning_capture"
        run_state["updated_at"] = timestamp
        write_json(run_state_path, run_state)

        self._append_human_review_note(run_state_path.parent / "human_review.md", decision_record, feedback)
        return {
            "ok": True,
            "run_state_path": self.to_rel(run_state_path),
            "human_decision": decision_record,
            "run_state": run_state,
            "learning": self.learning_overview(),
        }

    def dream_memory(self, body: dict[str, Any]) -> dict[str, Any]:
        apply = bool(body.get("apply", False))
        reason = str(body.get("reason") or "api")
        if body.get("all"):
            runner = LoopRunner(self.root)
            agent_ids = [spec.id for spec in runner.list_agents()]
        else:
            agent_id = str(body.get("agent_id") or "").strip()
            if not agent_id:
                raise BadRequest("Missing agent_id or all=true")
            agent_ids = [agent_id]
        reports = [MemoryStore(self.root, agent_id).dream(apply=apply, reason=reason) for agent_id in agent_ids]
        return {"ok": True, "reports": reports, "learning": self.learning_overview()}

    def record_success_memory(self, body: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(body.get("agent_id") or "").strip()
        dimension = str(body.get("dimension") or "").strip()
        pattern = str(body.get("pattern") or "").strip()
        if not agent_id:
            raise BadRequest("Missing agent_id")
        if not dimension:
            raise BadRequest("Missing dimension")
        if not pattern:
            raise BadRequest("Missing pattern")
        log_id = MemoryStore(self.root, agent_id).record_success(
            dimension=dimension,
            trigger_scene=str(body.get("scene") or "success_review"),
            pattern=pattern,
            why_it_worked=str(body.get("why") or ""),
            source=str(body.get("source") or "success-ui"),
        )
        return {"ok": True, "log_id": log_id, "learning": self.learning_overview()}

    def compare_reflect(self, body: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(body.get("agent_id") or "").strip()
        before_ref = str(body.get("before_path") or body.get("before") or "").strip()
        after_ref = str(body.get("after_path") or body.get("after") or "").strip()
        if not agent_id:
            raise BadRequest("Missing agent_id")
        if not before_ref or not after_ref:
            raise BadRequest("Missing before_path / after_path")
        before = self.safe_path(before_ref, READABLE_PREFIXES)
        after = self.safe_path(after_ref, READABLE_PREFIXES)
        comparison = compare_material_versions(before, after)
        dimension = str(body.get("dimension") or "").strip() or MemoryStore._infer_dimension(
            " ".join(comparison.get("change_tags", []))
        )
        lesson = str(body.get("lesson") or "").strip()
        if not lesson:
            tags = ", ".join(comparison.get("change_tags", []))
            lesson = f"后续同类材料应参考版本演化中的稳定修改方向：{tags}"
        log_id = MemoryStore(self.root, agent_id).record_comparison(
            dimension=dimension,
            trigger_scene=str(body.get("scene") or "version_comparison"),
            before_ref=self.to_rel(before),
            after_ref=self.to_rel(after),
            change_summary=", ".join(comparison.get("change_tags", [])),
            lesson=lesson,
            source=str(body.get("source") or "comparison-ui"),
        )
        LearningEventStore(self.root).append(
            event_type="comparison",
            agent_id=agent_id,
            source="web",
            payload={"log_id": log_id, "comparison": comparison, "lesson": lesson},
        )
        return {"ok": True, "log_id": log_id, "comparison": comparison, "learning": self.learning_overview()}

    def run_command(self, command: str) -> dict[str, Any]:
        if not command:
            raise BadRequest("Command is empty")
        lower = command.lower()
        if lower in {"help", "/help"}:
            return {
                "ok": True,
                "message": "Commands: list agents | run storyline | open <path> | show memory <agent_id>",
            }
        if lower in {"list agents", "agents"}:
            return {"ok": True, "kind": "overview", "data": self.overview()}
        if lower == "run storyline":
            return {"ok": True, "kind": "run", "data": self.run_agent({"agent_id": "storyline"})}
        if lower.startswith("run "):
            parts = command.split()
            agent_id = parts[1] if len(parts) > 1 else "storyline"
            if agent_id in {"storyline", "storyline-design"}:
                agent_id = "storyline"
            body: dict[str, Any] = {"agent_id": agent_id}
            if len(parts) > 2:
                body["input_path"] = parts[2]
            return {"ok": True, "kind": "run", "data": self.run_agent(body)}
        if lower.startswith("open "):
            return {"ok": True, "kind": "file", "data": self.read_file(command[5:].strip())}
        if lower.startswith("show memory"):
            parts = command.split()
            agent_id = parts[-1] if len(parts) >= 3 else "storyline"
            store = MemoryStore(self.root, agent_id)
            return {"ok": True, "kind": "memory", "data": [item.to_dict() for item in store.load_items()]}
        return {
            "ok": False,
            "message": "I can route simple local commands now. Use: list agents, run storyline, open <path>, show memory <agent_id>.",
        }

    # ---- inline single-step pipeline (PipelineStepper / StepRunner) --------

    def _pipeline_run_dir(self, run_name: str) -> Path:
        return self.root / "artifacts" / self.slug(run_name)

    def _current_stage_dir(self, run_dir: Path) -> Optional[Path]:
        """Resolve the run_dir of the stage the pipeline is currently on."""
        stepper = PipelineStepper(self.root, run_dir)
        ps = read_json(run_dir / "pipeline_state.json", default={})
        idx = int(ps.get("current_stage", 1)) - 1
        if idx < 0 or idx >= len(stepper.ordered):
            return None
        spec = stepper.ordered[idx]
        return run_dir / f"stage_{spec.stage}_{spec.id}"

    def step_init(self, body: dict[str, Any]) -> dict[str, Any]:
        run_name = self.slug(str(body.get("run_name") or "ui_inline"))
        run_dir = self._pipeline_run_dir(run_name)

        inline_input = str(body.get("input_json") or "").strip()
        if inline_input:
            parsed = json.loads(inline_input)
            input_dir = self.root / "artifacts" / "_ui_inputs"
            input_dir.mkdir(parents=True, exist_ok=True)
            brief_path = input_dir / f"{run_name}_brief.json"
            write_json(brief_path, parsed)
        else:
            brief_ref = str(body.get("input_path") or "examples/raw_brief.json")
            brief_path = self.safe_path(brief_ref, ("examples/", "artifacts/"))

        stepper = PipelineStepper(self.root, run_dir)
        stage = stepper.init_pipeline(brief_path)
        return {
            "ok": True,
            "run_name": run_name,
            "run_dir": self.to_rel(run_dir),
            "stage": stage,
            "pipeline": self._safe_pipeline_status(stepper),
        }

    def step_status(self, query: dict[str, list[str]]) -> dict[str, Any]:
        run_name = self.required_query(query, "run_name")
        run_dir = self._pipeline_run_dir(run_name)
        if not (run_dir / "pipeline_state.json").exists():
            raise NotFound(f"No inline pipeline named {run_name!r}")
        stepper = PipelineStepper(self.root, run_dir)
        return {
            "ok": True,
            "run_name": run_name,
            "run_dir": self.to_rel(run_dir),
            "pipeline": self._safe_pipeline_status(stepper),
            "stage": self._stage_view(run_dir),
        }

    def step_prepare(self, body: dict[str, Any]) -> dict[str, Any]:
        run_dir = self._require_run_dir(body)
        runner = self._stage_runner(run_dir)
        try:
            result = runner.prepare()
        except StepError as exc:
            raise BadRequest(str(exc))
        return {"ok": True, "run_dir": self.to_rel(run_dir), "result": result,
                "stage": self._stage_view(run_dir)}

    def step_write_output(self, body: dict[str, Any]) -> dict[str, Any]:
        """Write the host model's generation/review output into the handoff slot."""
        run_dir = self._require_run_dir(body)
        runner = self._stage_runner(run_dir)
        status = runner.status()
        output_path = status.get("output_path")
        if not output_path:
            raise BadRequest("当前步骤没有等待写入的 output（请先 prepare）")
        raw = body.get("output_json")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError as exc:
                raise BadRequest(f"output_json 不是合法 JSON: {exc}")
        elif isinstance(raw, dict):
            parsed = raw
        else:
            raise BadRequest("缺少 output_json（字符串或对象）")
        write_json(Path(output_path), parsed)
        return {"ok": True, "output_path": self.to_rel(Path(output_path))}

    def step_commit(self, body: dict[str, Any]) -> dict[str, Any]:
        run_dir = self._require_run_dir(body)
        runner = self._stage_runner(run_dir)
        try:
            result = runner.commit()
        except StepError as exc:
            raise BadRequest(str(exc))
        return {"ok": True, "run_dir": self.to_rel(run_dir), "result": result,
                "stage": self._stage_view(run_dir)}

    def step_advance(self, body: dict[str, Any]) -> dict[str, Any]:
        run_dir = self._require_run_dir(body)
        stepper = PipelineStepper(self.root, run_dir)
        try:
            stage = stepper.advance_stage()
        except StepError as exc:
            raise BadRequest(str(exc))
        return {"ok": True, "run_dir": self.to_rel(run_dir), "stage": stage,
                "pipeline": self._safe_pipeline_status(stepper),
                "stage_view": self._stage_view(run_dir)}

    # -- step helpers --------------------------------------------------------

    def _require_run_dir(self, body: dict[str, Any]) -> Path:
        run_name = str(body.get("run_name") or "").strip()
        if not run_name:
            raise BadRequest("Missing run_name")
        run_dir = self._pipeline_run_dir(run_name)
        if not (run_dir / "pipeline_state.json").exists():
            raise BadRequest(f"未找到 inline pipeline: {run_name}（请先 init）")
        return run_dir

    def _stage_runner(self, run_dir: Path) -> StepRunner:
        stage_dir = self._current_stage_dir(run_dir)
        if stage_dir is None or not (stage_dir / "run_state.json").exists():
            raise BadRequest("当前阶段尚未初始化")
        manager_state = read_json(run_dir / "manager_state.json", default={})
        return StepRunner(
            self.root,
            stage_dir,
            contract_profile=manager_state.get("contract_profile"),
        )

    def _safe_pipeline_status(self, stepper: PipelineStepper) -> dict[str, Any]:
        ps = stepper.pipeline_status()
        for stage in ps.get("stages", []):
            if stage.get("dir"):
                try:
                    stage["dir"] = self.to_rel(Path(stage["dir"]))
                except ValueError:
                    pass
        return ps

    def _stage_view(self, run_dir: Path) -> dict[str, Any]:
        """Rich view of the current stage: status + instruction/output text + renders."""
        stage_dir = self._current_stage_dir(run_dir)
        if stage_dir is None:
            return {"current_step": "done"}
        try:
            manager_state = read_json(run_dir / "manager_state.json", default={})
            runner = StepRunner(
                self.root,
                stage_dir,
                contract_profile=manager_state.get("contract_profile"),
            )
            status = runner.status()
        except (StepError, KeyError, FileNotFoundError):
            return {"current_step": "uninitialized"}

        view = dict(status)
        # attach instruction + output content if present
        instr = status.get("instruction_path")
        if instr and Path(instr).exists():
            view["instruction_text"] = Path(instr).read_text(encoding="utf-8")
            view["instruction_rel"] = self.to_rel(Path(instr))
        out = status.get("output_path")
        if out and Path(out).exists():
            view["output_text"] = Path(out).read_text(encoding="utf-8")
            view["output_rel"] = self.to_rel(Path(out))

        # surface rendered deliverables (draft/final) for this stage
        view["rendered_files"] = self._stage_rendered_files(stage_dir)
        # surface latest review summary if any
        view["review"] = self._latest_stage_review(stage_dir)
        return view

    def _stage_rendered_files(self, stage_dir: Path) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        for pattern in ("*.pptx", "*.html", "*.docx"):
            for f in sorted(stage_dir.glob(pattern)):
                if "__" in f.name and f.name.endswith(".html") and f.name.startswith("instruction"):
                    continue
                try:
                    rel = self.to_rel(f)
                except ValueError:
                    continue
                files.append({"path": rel, "name": f.name, "size": f.stat().st_size,
                              "kind": f.suffix.lstrip(".")})
        return files

    def _latest_stage_review(self, stage_dir: Path) -> Optional[dict[str, Any]]:
        reviews = sorted(stage_dir.glob("review_round_*.json"))
        if not reviews:
            return None
        data = read_json(reviews[-1])
        objs = data.get("objections", [])
        return {
            "reviewer": data.get("reviewer"),
            "p0": [o for o in objs if o.get("severity") == "P0"],
            "p1": [o for o in objs if o.get("severity") == "P1"],
        }

    def list_runs(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        artifacts = self.root / "artifacts"
        if not artifacts.exists():
            return []
        runs: list[dict[str, Any]] = []
        for path in artifacts.iterdir():
            if not path.is_dir() or path.name.startswith("_"):
                continue
            result_path = path / "loop_result.json"
            if result_path.exists():
                result = read_json(result_path)
                run_state = read_json(path / "run_state.json", default={})
                runs.append(
                    {
                        "name": path.name,
                        "status": result.get("status"),
                        "agent_id": result.get("agent_id"),
                        "run_id": result.get("run_id"),
                        "artifact": self.to_rel(path / "artifact.json"),
                        "review": self.to_rel(path / "review.json"),
                        "run_state": self.to_rel(path / "run_state.json"),
                        "human_review": self.to_rel(path / "human_review.md"),
                        "selected_capabilities": run_state.get("selected_capabilities", []),
                        "prompt_budget": run_state.get("prompt_budget", {}),
                        "skill_budget": run_state.get("skill_budget", {}),
                        "context_mode": run_state.get("context_mode", "legacy_flat"),
                        "legacy_skill": not bool(run_state.get("selected_capabilities")),
                        "mtime": path.stat().st_mtime,
                    }
                )
        runs.sort(key=lambda item: item["mtime"], reverse=True)
        if limit is not None:
            runs = runs[:limit]
        return runs

    def read_artifact(self, rel_path: str) -> dict[str, Any]:
        path = self.safe_path(rel_path, ("artifacts/",))
        return {"path": self.to_rel(path), "content": path.read_text(encoding="utf-8")}

    def _read_learning_log(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    entries.append(item)
        return entries

    def _read_event_log(self) -> list[dict[str, Any]]:
        path = LearningEventStore(self.root).path
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    entries.append(item)
        return entries

    def _append_human_review_note(
        self,
        path: Path,
        decision: dict[str, Any],
        feedback: dict[str, Any],
    ) -> None:
        if not path.exists():
            return
        lines = [
            "",
            "## Recorded human review event",
            "",
            f"- at: {decision['at']}",
            f"- decision: {decision['decision']}",
            f"- reviewer: {decision['reviewer']}",
            f"- notes: {decision['notes'] or '-'}",
            f"- feedback_log_ids: {', '.join(decision['feedback_log_ids']) or '-'}",
        ]
        if feedback:
            lines.extend(
                [
                    f"- feedback_dimension: {feedback.get('dimension', '-')}",
                    f"- feedback_problem: {feedback.get('problem', '-')}",
                    f"- feedback_change: {feedback.get('change', '-')}",
                ]
            )
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def safe_path(self, rel_path: str, prefixes: tuple[str, ...]) -> Path:
        clean = rel_path.strip().lstrip("/")
        raw_path = Path(rel_path.strip())
        path = raw_path.resolve() if raw_path.is_absolute() else (self.root / clean).resolve()
        if not path.is_relative_to(self.root):
            raise BadRequest("Path escapes project root")
        rel = self.to_rel(path)
        if not any(rel == prefix.rstrip("/") or rel.startswith(prefix) for prefix in prefixes):
            raise BadRequest(f"Path is not allowed here: {rel}")
        if not path.exists() and path.suffix == "":
            raise BadRequest(f"Path does not exist: {rel}")
        return path

    def to_rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def is_editable(self, rel_path: str) -> bool:
        return any(rel_path.startswith(prefix) for prefix in EDITABLE_PREFIXES)

    def kind_for(self, rel_path: str) -> str:
        if rel_path.endswith(".json"):
            return "json"
        if rel_path.endswith(".py"):
            return "python"
        if rel_path.endswith(".md"):
            return "markdown"
        return "text"

    def slug(self, value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())[:80].strip("_")
        return safe or "ui_run"

    def required_query(self, query: dict[str, list[str]], name: str) -> str:
        values = query.get(name)
        if not values:
            raise BadRequest(f"Missing query parameter: {name}")
        return values[0]

    def json(self, data: Any, status: int = HTTPStatus.OK) -> tuple[int, Any, str]:
        return status, data, "application/json; charset=utf-8"


class AppError(Exception):
    status = HTTPStatus.INTERNAL_SERVER_ERROR


class BadRequest(AppError):
    status = HTTPStatus.BAD_REQUEST


class NotFound(AppError):
    status = HTTPStatus.NOT_FOUND


class RequestHandler(BaseHTTPRequestHandler):
    app: WebApp
    # HTTP/1.1 so persistent-connection clients (browsers, urllib, curl) read
    # the Content-Length-delimited body reliably. Every response sets an
    # explicit Content-Length, so keep-alive framing is unambiguous.
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                status, payload, content_type = self.app.handle_get(parsed.path, parse_qs(parsed.query))
                self.send_payload(status, payload, content_type)
                return
            self.serve_static(parsed.path)
        except AppError as exc:
            self.send_payload(exc.status, {"ok": False, "error": str(exc)}, "application/json; charset=utf-8")
        except Exception as exc:
            self.send_payload(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": str(exc)},
                "application/json; charset=utf-8",
            )

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            body = json.loads(raw or "{}")
            parsed = urlparse(self.path)
            status, payload, content_type = self.app.handle_post(parsed.path, body)
            self.send_payload(status, payload, content_type)
        except AppError as exc:
            self.send_payload(exc.status, {"ok": False, "error": str(exc)}, "application/json; charset=utf-8")
        except json.JSONDecodeError as exc:
            self.send_payload(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)}, "application/json; charset=utf-8")
        except Exception as exc:
            self.send_payload(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": str(exc)},
                "application/json; charset=utf-8",
            )

    def serve_static(self, path: str) -> None:
        rel = "index.html" if path in {"", "/"} else path.lstrip("/")
        target = (STATIC_DIR / rel).resolve()
        if not target.is_relative_to(STATIC_DIR) or not target.exists() or not target.is_file():
            target = STATIC_DIR / "index.html"
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_payload(self, status: int, payload: Any, content_type: str) -> None:
        if content_type.startswith("application/json"):
            raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        else:
            raw = str(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(prog="presentation-agent-web")
    parser.add_argument("--root", default=".")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()

    app = WebApp(Path(args.root))

    class BoundHandler(RequestHandler):
        pass

    BoundHandler.app = app
    server = ThreadingHTTPServer((args.host, args.port), BoundHandler)
    print(f"Presentation Agent UI: http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
