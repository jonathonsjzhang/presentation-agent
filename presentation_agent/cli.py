from __future__ import annotations

import argparse
import json
from pathlib import Path

from presentation_agent.launch import BriefError, launch_report
from presentation_agent.learning import LearningEventStore, compare_material_versions
from presentation_agent.loop import LoopRunner
from presentation_agent.manager import ManagerOrchestrator
from presentation_agent.memory import MemoryStore
from presentation_agent.memory_router import MemoryRouter
from presentation_agent.pipeline import Pipeline
from presentation_agent.step import PipelineStepper, StepError, StepRunner
from presentation_agent.workspace import init_workspace, resolve_workspace, workspace_status


def _add_spawn_adapter_option(
    parser: argparse.ArgumentParser, *, required: bool = False
) -> None:
    parser.add_argument(
        "--spawn-adapter",
        choices=["inline", "workbuddy", "claude", "codex", "cli"],
        required=required,
        help=(
            "Sub-agent host for this run. The override is persisted in manager_state; "
            "report start requires the host to select its native adapter; later commands "
            "preserve the run's persisted adapter unless overridden. Use inline only as "
            "an explicit compatibility fallback when the host cannot spawn sub-agents."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="presentation-agent")
    parser.add_argument("--root", default=".", help="Project root. Defaults to current directory.")
    parser.add_argument("--workspace", help="User workspace for memory/runs/artifacts.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-agents", help="List configured pipeline agents.")

    init_ws = sub.add_parser("init-workspace", help="Initialize a user workspace.")
    init_ws.add_argument("--force", action="store_true", help="Rewrite seed files such as config/global state.")

    sub.add_parser("doctor", help="Check repo and workspace health. Emits JSON.")

    derive = sub.add_parser(
        "derive-agents",
        help="Derive per-terminal sub-agent files from configs/agents.json.",
    )
    derive.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written without writing files.",
    )

    report = sub.add_parser("report", help="High-level host report commands.")
    report_subs = report.add_subparsers(dest="report_command", required=True)

    report_start = report_subs.add_parser("start", help="Start a report run and return first instruction.")
    report_start.add_argument("--brief-file", required=True, help="raw_brief JSON file path.")
    _add_spawn_adapter_option(report_start, required=True)

    report_next = report_subs.add_parser("next", help="Return the current report instruction.")
    report_next.add_argument("--run", required=True, help="Run id or run directory.")
    _add_spawn_adapter_option(report_next)

    report_continue = report_subs.add_parser(
        "continue",
        help="Consume ready outputs and deterministic transitions until a human gate, external Worker action, or error.",
    )
    report_continue.add_argument("--run", required=True, help="Run id or run directory.")
    report_continue.add_argument("--max-steps", type=int, default=50)
    _add_spawn_adapter_option(report_continue)

    report_submit = report_subs.add_parser("submit", help="Submit host output for the current instruction.")
    report_submit.add_argument("--run", required=True, help="Run id or run directory.")
    report_submit.add_argument("--output-file", help="JSON output file produced by the host model.")
    report_submit.add_argument(
        "--spawn-completed",
        action="store_true",
        help="Attest that the dispatched Worker sub-agent completed this step.",
    )
    _add_spawn_adapter_option(report_submit)

    report_approve = report_subs.add_parser("approve", help="Approve the current Manager human gate.")
    report_approve.add_argument("--run", required=True, help="Run id or run directory.")
    report_approve.add_argument(
        "--run-mode",
        choices=["full_auto", "step_by_step", "custom"],
        default=None,
        help=(
            "Brief gate execution mode. Omit for the default checkpoints after "
            "analysis and storyline."
        ),
    )
    report_approve.add_argument(
        "--pause-after",
        action="append",
        choices=["analysis", "storyline", "report", "qa_preparation", "format"],
        default=[],
        help="Worker pause point for --run-mode custom; repeat as needed.",
    )
    report_approve.add_argument(
        "--delivery-option",
        choices=[
            "format:ppt",
            "format:html",
            "skip",
        ],
        help="Delivery-options gate selection after the default worker chain.",
    )
    _add_spawn_adapter_option(report_approve)

    report_feedback = report_subs.add_parser("feedback", help="Return human feedback to Manager.")
    report_feedback.add_argument("--run", required=True, help="Run id or run directory.")
    report_feedback.add_argument("--text", required=True, help="Human feedback for the current Manager gate.")
    _add_spawn_adapter_option(report_feedback)

    report_revise = report_subs.add_parser(
        "revise", help="Explicitly revise one v0.4 stage from a human gate."
    )
    report_revise.add_argument("--run", required=True, help="Run id or run directory.")
    report_revise.add_argument(
        "--stage",
        required=True,
        choices=["analysis", "storyline", "report", "qa_preparation", "format"],
    )
    report_revise.add_argument("--feedback", required=True)
    _add_spawn_adapter_option(report_revise)

    report_status = report_subs.add_parser("status", help="Show report run status.")
    report_status.add_argument("--run", required=True, help="Run id or run directory.")
    _add_spawn_adapter_option(report_status)

    report_manager_status = report_subs.add_parser("manager-status", help="Show manager state for a report run.")
    report_manager_status.add_argument("--run", required=True, help="Run id or run directory.")
    _add_spawn_adapter_option(report_manager_status)

    report_manager_plan = report_subs.add_parser("manager-plan", help="Show manager plan for a report run.")
    report_manager_plan.add_argument("--run", required=True, help="Run id or run directory.")
    _add_spawn_adapter_option(report_manager_plan)

    run = sub.add_parser("run", help="Run one agent loop.")
    run.add_argument("agent_id")
    run.add_argument("--input", required=True, help="Input artifact JSON path.")
    run.add_argument("--out", help="Optional output directory.")
    run.add_argument("--provider", help="Override LLM provider (mock/cli/codex/inline).")

    pipe = sub.add_parser("pipeline", help="Run the five-stage debug pipeline.")
    pipe.add_argument("--input", required=True, help="Initial raw brief JSON path.")
    pipe.add_argument("--out", help="Optional output directory.")
    pipe.add_argument("--auto", action="store_true", help="Run all stages back to back.")
    pipe.add_argument("--start-stage", type=int, default=1, help="Stage to start from (resume).")
    pipe.add_argument("--provider", help="Override LLM provider (mock/cli/codex/inline).")

    launch = sub.add_parser(
        "launch",
        help="Host entry: normalize a brief and initialize a Manager-controlled report run.",
    )
    launch.add_argument(
        "--brief",
        required=True,
        help="raw_brief JSON: a file path, or an inline JSON string the host assembled.",
    )
    launch.add_argument("--out", help="Optional output directory.")
    launch.add_argument("--auto", action="store_true", help="Run all stages back to back.")
    launch.add_argument(
        "--provider",
        default="cli",
        help="LLM provider (default: cli — borrow the host's coding-agent CLI).",
    )
    launch.add_argument(
        "--init-only",
        action="store_true",
        help="Only initialize the pipeline (write brief, create stage dirs); do not run any agent.",
    )
    _add_spawn_adapter_option(launch, required=True)

    # ---- inline step commands (host-self-execution) -------------------------
    step = sub.add_parser("step", help="Inline step commands (host-driven single-step execution).")
    step_subs = step.add_subparsers(dest="step_command", required=True)

    step_status = step_subs.add_parser("status", help="Show current step state of a stage run_dir.")
    step_status.add_argument("--run-dir", required=True, help="Path to stage run_dir.")

    step_prepare = step_subs.add_parser("prepare", help="Assemble instruction and write handoff file.")
    step_prepare.add_argument("--run-dir", required=True, help="Path to stage run_dir.")

    step_commit = step_subs.add_parser("commit", help="Read handoff output, validate, and advance state.")
    step_commit.add_argument("--run-dir", required=True, help="Path to stage run_dir.")

    step_abort = step_subs.add_parser("abort", help="Abort the current stage.")
    step_abort.add_argument("--run-dir", required=True, help="Path to stage run_dir.")

    # ---- pipeline level inline commands -------------------------------------
    pipe_init = sub.add_parser("pipeline-init", help="Initialize inline pipeline (write brief, create stage 1 dir).")
    pipe_init.add_argument("--brief", required=True, help="Brief JSON file path or inline JSON string.")
    pipe_init.add_argument("--out", help="Optional pipeline output directory.")

    pipe_adv = sub.add_parser("pipeline-advance", help="Advance to next stage (after current stage is done).")
    pipe_adv.add_argument("--run-dir", required=True, help="Pipeline root run_dir (same as --out of pipeline-init).")

    pipe_status = sub.add_parser("pipeline-status", help="Show pipeline-level status (all stages).")
    pipe_status.add_argument("--run-dir", required=True, help="Pipeline root run_dir.")

    feedback = sub.add_parser("feedback", help="Append human feedback and update hot memory.")
    feedback.add_argument("agent_id")
    feedback.add_argument("--dimension", required=True)
    feedback.add_argument("--problem", required=True)
    feedback.add_argument("--reason", default="")
    feedback.add_argument("--change", required=True)
    feedback.add_argument("--scene", default="human_review")
    feedback.add_argument("--scope", default="agent", choices=["agent", "global"])

    feedback_text = sub.add_parser(
        "feedback-text",
        help="Parse natural-language human feedback from chat and update memory.",
    )
    feedback_text.add_argument("agent_id")
    feedback_text.add_argument("--text", required=True, help="Raw feedback sentence from the conversation.")
    feedback_text.add_argument("--dimension", help="Optional explicit memory dimension.")
    feedback_text.add_argument("--scene", default="human_review_chat")
    feedback_text.add_argument("--scope", default="agent", choices=["agent", "global"])
    feedback_text.add_argument("--run-state", help="Optional run_state.json to append the feedback log id to.")

    success = sub.add_parser("success-memory", help="Record a reusable successful pattern into memory.")
    success.add_argument("agent_id")
    success.add_argument("--dimension", required=True)
    success.add_argument("--pattern", required=True, help="What worked and should be reused.")
    success.add_argument("--why", default="", help="Why the pattern worked.")
    success.add_argument("--scene", default="success_review")

    compare = sub.add_parser(
        "compare-reflect",
        help="Compare two material versions and record a reusable comparison lesson.",
    )
    compare.add_argument("agent_id")
    compare.add_argument("--before", required=True, help="Earlier material path.")
    compare.add_argument("--after", required=True, help="Later/final material path.")
    compare.add_argument("--dimension", default="", help="Optional explicit memory dimension.")
    compare.add_argument("--lesson", default="", help="Optional human-written lesson to store.")
    compare.add_argument("--scene", default="version_comparison")

    memory = sub.add_parser("show-memory", help="Show hot memory for one agent.")
    memory.add_argument("agent_id")

    maintain = sub.add_parser(
        "memory-maintain",
        help="Lint and optionally clean hot memory for one agent.",
    )
    maintain.add_argument("agent_id")
    maintain.add_argument("--lint", action="store_true", help="Show lint diagnosis.")
    maintain.add_argument(
        "--apply",
        action="store_true",
        help="Apply deterministic lint cleanup.",
    )

    dream = sub.add_parser(
        "memory-dream",
        help="Summarize and clean fragmented memory for one agent or all agents.",
    )
    dream.add_argument("agent_id", nargs="?", help="Agent id. Omit when using --all.")
    dream.add_argument("--all", action="store_true", help="Run memory dreaming for all configured agents.")
    dream.add_argument("--apply", action="store_true", help="Apply deterministic cleanup while dreaming.")
    dream.add_argument("--reason", default="manual", help="Reason label stored in dream report.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    workspace = resolve_workspace(getattr(args, "workspace", None), start=root)

    if args.command == "init-workspace":
        _print_json(init_workspace(workspace, root, force=args.force))
        return

    if args.command == "doctor":
        import platform
        import subprocess

        report = workspace_status(workspace, root)
        report["python"] = platform.python_version()
        try:
            commit = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            report["git_commit"] = commit.stdout.strip() if commit.returncode == 0 else ""
        except Exception:
            report["git_commit"] = ""
        _print_json(report)
        return

    if args.command == "derive-agents":
        from presentation_agent.derive_agents import derive_all, write_derived

        derived = derive_all(root)
        summary = [
            {"host": d.host, "role": d.role, "agent_id": d.agent_id, "path": str(d.path)}
            for d in derived
        ]
        if args.dry_run:
            _print_json({"ok": True, "dry_run": True, "count": len(derived), "files": summary})
            return
        written = write_derived(root, derived)
        _print_json({
            "ok": True,
            "dry_run": False,
            "count": len(written),
            "files": [str(p.relative_to(root)) for p in written],
        })
        return

    if args.command == "report":
        _handle_report_command(args, root, workspace)
        return

    if args.command == "list-agents":
        runner = LoopRunner(root)
        control = runner.config.get("control_plane", {})
        if control:
            print(
                f"0. manager ({control.get('name', 'Manager')}) skill=manager "
                f"in={control.get('input_schema')} out={control.get('output_schema')}"
            )
        active = set(runner.config.get("pipeline", {}).get("stages", []))
        for spec in runner.list_agents():
            if spec.id not in active:
                continue
            print(
                f"{spec.stage}. {spec.id} ({spec.name}) skill={spec.skill} "
                f"in={spec.input_schema} out={spec.output_schema}"
            )
        return

    if args.command == "run":
        runner = LoopRunner(
            root,
            provider_override=getattr(args, "provider", None),
            contract_profile="v0_4",
        )
        result = runner.run(args.agent_id, Path(args.input).resolve(), Path(args.out).resolve() if args.out else None)
        print(f"status: {result['status']}")
        print(f"artifact: {result['artifact_path']}")
        print(f"human_review: {result['human_review_path']}")
        return

    if args.command == "pipeline":
        pipeline = Pipeline(root, provider_override=getattr(args, "provider", None))
        summary = pipeline.run(
            Path(args.input).resolve(),
            run_dir=Path(args.out).resolve() if args.out else None,
            auto=args.auto,
            start_stage=args.start_stage,
        )
        print(f"pipeline status: {summary['status']} ({summary['mode']})")
        for record in summary["stages"]:
            print(f"  stage {record['stage']} {record['agent_id']}: {record['status']}")
        if summary["stopped_reason"]:
            print(f"note: {summary['stopped_reason']}")
        print(f"overview: {summary['output_dir']}/pipeline_overview.md")
        return

    if args.command == "launch":
        try:
            result = launch_report(
                args.brief,
                root=root,
                provider=args.provider,
                auto=args.auto,
                out=Path(args.out).resolve() if args.out else None,
                spawn_adapter=args.spawn_adapter,
                init_only=getattr(args, "init_only", False),
                contract_profile="v0_4",
            )
        except BriefError as exc:
            print(f"brief error: {exc}")
            raise SystemExit(2)
        if getattr(args, "init_only", False):
            print(f"brief: {result['brief_path']}")
            print(f"pipeline dir: {result['output_dir']}")
            print(f"stage 1 dir: {result['stage_1_dir']}")
            print("pipeline initialized. Use step commands to drive each stage.")
            return
        if result.get("mode") == "manager_controlled":
            print(f"brief: {result['brief_path']}")
            print(f"contract profile: {result.get('contract_profile', 'v0_4')}")
            print(f"run dir: {result['run_dir']}")
            print(json.dumps(result["instruction"], ensure_ascii=False, indent=2))
            return
        print(f"brief: {result['brief_path']}")
        print(f"provider: {result['provider']}")
        print(f"pipeline status: {result['status']} ({result['mode']})")
        for record in result["stages"]:
            print(f"  stage {record['stage']} {record['agent_id']}: {record['status']}")
        if result["stopped_reason"]:
            print(f"note: {result['stopped_reason']}")
        print(f"overview: {result['output_dir']}/pipeline_overview.md")
        return

    if args.command == "step":
        run_dir = Path(args.run_dir).resolve()
        runner = StepRunner(root, run_dir)
        try:
            if args.step_command == "status":
                s = runner.status()
                print(f"agent: {s['agent_name']} ({s['agent_id']}) stage={s['stage']}")
                print(f"current_step: {s['current_step']} round={s['round_index']}")
                print(f"p0_open: {s['p0_open_count']}")
                if s['instruction_path']:
                    print(f"instruction: {s['instruction_path']}")
                if s['output_path']:
                    print(f"output: {s['output_path']}")
            elif args.step_command == "prepare":
                r = runner.prepare()
                print(f"step: {r['step']} round={r.get('round_index', 0)}")
                print(f"instruction: {r['instruction_path']}")
                print(f"output: {r['output_path']}")
            elif args.step_command == "commit":
                r = runner.commit()
                # ---- human-in-the-loop: always show content ----
                present = r.get("present_to_user")
                if present:
                    print(present)
                    print("")
                if r.get("validation_summary") and r["step"] != "done":
                    print(f"🔍 {r['validation_summary']}")
                if r.get("revision_reason"):
                    print(f"🔧 {r['revision_reason']}")
                if r.get("memory_notes") and r["step"] != "done":
                    print(f"🧠 {r['memory_notes']}")
                if r["step"] == "done":
                    print(f"artifact: {r.get('artifact_path', '')}")
                    print(f"status: {r.get('status', 'done')}")
                else:
                    print(f"next instruction: {r['instruction_path']}")
            elif args.step_command == "abort":
                r = runner.abort()
                print(f"status: {r['status']}")
        except StepError as exc:
            print(f"step error: {exc}")
            raise SystemExit(3)
        return

    if args.command == "pipeline-init":
        from presentation_agent.launch import normalize_brief
        from presentation_agent.io import write_json
        from presentation_agent.models import now_iso
        run_id = f"pipeline-{now_iso().replace(':', '').replace('+', 'Z')}"
        out_root = Path(args.out).resolve() if args.out else (root / "artifacts" / run_id)
        normalized = normalize_brief(args.brief, root)
        brief_path = out_root / "raw_brief.json"
        out_root.mkdir(parents=True, exist_ok=True)
        write_json(brief_path, normalized)
        stepper = PipelineStepper(root, out_root)
        stage1 = stepper.init_pipeline(brief_path)
        print(f"pipeline dir: {out_root}")
        print(f"brief: {brief_path}")
        print(f"stage 1: {stage1['agent_name']} ({stage1['agent_id']})")
        print(f"stage 1 dir: {stage1['stage_dir']}")
        print("ready — use step prepare/commit on stage dirs to drive the pipeline")
        return

    if args.command == "pipeline-advance":
        run_dir = Path(args.run_dir).resolve()
        stepper = PipelineStepper(root, run_dir)
        try:
            result = stepper.advance_stage()
            print(f"next stage: {result['agent_name']} ({result['agent_id']})")
            print(f"stage dir: {result['stage_dir']}")
            print(f"input: {result['input_path']}")
        except StepError as exc:
            print(f"advance error: {exc}")
            raise SystemExit(3)
        return

    if args.command == "pipeline-status":
        run_dir = Path(args.run_dir).resolve()
        stepper = PipelineStepper(root, run_dir)
        ps = stepper.pipeline_status()
        print(f"pipeline: {ps['pipeline_id']}")
        print(f"current stage: {ps['current_stage']}")
        for s in ps["stages"]:
            marker = "←" if s["index"] == ps["current_stage"] else " "
            print(f"  {marker} {s['index']}. {s['agent_name']}: {s['status']}")
        return

    if args.command == "feedback":
        store = MemoryStore(root, args.agent_id, data_root=workspace.data_dir)
        log_id = store.record_feedback(
            scope=args.scope,
            dimension=args.dimension,
            trigger_scene=args.scene,
            problem=args.problem,
            reason=args.reason,
            change=args.change,
            source="human",
        )
        print(f"recorded: {log_id}")
        return

    if args.command == "feedback-text":
        route_result = None
        if args.agent_id == "auto":
            router = MemoryRouter(root, data_root=workspace.data_dir)
            route_result = router.record_text_feedback_multi(
                text=args.text,
                trigger_scene=args.scene,
                run_state_path=Path(args.run_state).resolve() if args.run_state else None,
                explicit_dimension=args.dimension,
                scope=args.scope,
            )
            parsed = route_result["parsed"]
            target_agent_id = route_result["route"]["target_agent_id"]
            routed_records = route_result["records"]
        else:
            store = MemoryStore(root, args.agent_id, data_root=workspace.data_dir)
            parsed = store.record_text_feedback(
                text=args.text,
                trigger_scene=args.scene,
                source="human-chat",
                dimension=args.dimension,
                scope=args.scope,
            )
            target_agent_id = args.agent_id
            routed_records = [{"parsed": parsed, "route": {"target_agent_id": target_agent_id}}]
        if args.run_state:
            from presentation_agent.io import read_json, write_json
            from presentation_agent.models import now_iso

            run_state_path = Path(args.run_state).resolve()
            state = read_json(run_state_path)
            state.setdefault("feedback_logged", []).extend(
                record["parsed"]["log_id"] for record in routed_records
            )
            state.setdefault("history", []).append(
                {
                    "at": now_iso(),
                    "step": "learning_capture",
                    "message": f"Chat feedback recorded: {parsed['log_id']} -> {target_agent_id}",
                }
            )
            if route_result:
                state.setdefault("feedback_routes", []).extend(route_result["routes"])
            state["updated_at"] = now_iso()
            write_json(run_state_path, state)
        print(f"recorded: {parsed['log_id']}")
        print("agent: " + ",".join(
            record["route"]["target_agent_id"] for record in routed_records
        ))
        if route_result:
            print(f"route_reason: {route_result['route']['reason']}")
        print(f"dimension: {parsed['dimension']}")
        print(f"problem: {parsed['problem']}")
        print(f"change: {parsed['change']}")
        return

    if args.command == "success-memory":
        store = MemoryStore(root, args.agent_id, data_root=workspace.data_dir)
        log_id = store.record_success(
            dimension=args.dimension,
            trigger_scene=args.scene,
            pattern=args.pattern,
            why_it_worked=args.why,
        )
        print(f"recorded success: {log_id}")
        return

    if args.command == "compare-reflect":
        store = MemoryStore(root, args.agent_id, data_root=workspace.data_dir)
        before = Path(args.before).resolve()
        after = Path(args.after).resolve()
        comparison = compare_material_versions(before, after)
        dimension = args.dimension or MemoryStore._infer_dimension(" ".join(comparison.get("change_tags", [])))
        lesson = args.lesson.strip()
        if not lesson:
            tags = ", ".join(comparison.get("change_tags", []))
            lesson = f"后续同类材料应参考版本演化中的稳定修改方向：{tags}"
        log_id = store.record_comparison(
            dimension=dimension,
            trigger_scene=args.scene,
            before_ref=str(before),
            after_ref=str(after),
            change_summary=", ".join(comparison.get("change_tags", [])),
            lesson=lesson,
        )
        LearningEventStore(root, data_root=workspace.data_dir).append(
            event_type="comparison",
            agent_id=args.agent_id,
            source="cli",
            payload={"log_id": log_id, "comparison": comparison, "lesson": lesson},
        )
        print(f"recorded comparison: {log_id}")
        print(f"dimension: {dimension}")
        print(f"tags: {', '.join(comparison.get('change_tags', []))}")
        print(f"lesson: {lesson}")
        return

    if args.command == "show-memory":
        store = MemoryStore(root, args.agent_id, data_root=workspace.data_dir)
        for item in store.load_items():
            print(f"{item.id} [{item.dimension}] hits={item.hit_count}: {item.suggestion}")
        return

    if args.command == "memory-maintain":
        store = MemoryStore(root, args.agent_id)
        if args.lint:
            if args.apply:
                result = store.apply_lint()
                print(f"evicted: {result['evicted']}; remaining: {result['remaining']}")
            else:
                report = store.lint()
                print(f"total={report['total']} soft_limit={report['soft_limit']}")
                print(f"  over_limit: {report['over_limit']}")
                print(f"  orphan_links: {report['orphan_links']}")
                print(f"  duplicates: {report['duplicates']}")
        if not args.promote and not args.lint:
            print("specify --promote and/or --lint")
        return

    if args.command == "memory-dream":
        if args.all:
            runner = LoopRunner(root)
            agent_ids = [spec.id for spec in runner.list_agents()]
        elif args.agent_id:
            agent_ids = [args.agent_id]
        else:
            print("memory-dream requires <agent_id> or --all")
            raise SystemExit(2)
        for agent_id in agent_ids:
            result = MemoryStore(
                root,
                agent_id,
                data_root=workspace.data_dir,
            ).dream(apply=args.apply, reason=args.reason)
            print(
                f"{agent_id}: before={result['before_count']} after={result['after_count']} "
                f"conflicts={len(result['potential_conflicts'])} report={result['report_path']}"
            )
        return


def _current_instruction(result: object) -> dict[str, object]:
    """Normalize Manager/Worker/Human transitions to one host-facing shape."""

    if not isinstance(result, dict):
        return {}
    nested = result.get("instruction")
    instruction = nested if isinstance(nested, dict) else result
    # Large artifacts and complete briefs live on disk. Human-facing text and
    # structured question payloads stay inline because the host must present
    # them immediately.
    omitted = {"brief", "evidence_options", "storyline"}
    normalized = {
        key: value
        for key, value in instruction.items()
        if key not in omitted
    }
    if "next_action" not in normalized and result.get("next_action"):
        normalized["next_action"] = result["next_action"]
    return normalized


def _report_response(
    *,
    run_dir: Path,
    result: object,
    manager: ManagerOrchestrator,
    run_id: str | None = None,
    brief_path: str | None = None,
) -> dict[str, object]:
    instruction = _current_instruction(result)
    spawn = instruction.get("spawn")
    response: dict[str, object] = {
        "ok": True,
        "run_dir": str(run_dir),
        "current_instruction": instruction,
        "spawn_required": bool(
            isinstance(spawn, dict) and spawn.get("status") == "dispatched"
        ),
        "manager": manager.status_summary(),
        "next_action": instruction.get(
            "next_action", "host_write_output_then_report_submit"
        ),
    }
    if run_id:
        response["run_id"] = run_id
    if brief_path:
        response["brief_path"] = brief_path
    return response


def _handle_report_command(args: argparse.Namespace, root: Path, workspace) -> None:
    if args.report_command == "start":
        from presentation_agent.io import write_json
        from presentation_agent.launch import normalize_brief
        from presentation_agent.models import now_iso

        init_workspace(workspace, root)
        run_id = f"report-{now_iso().replace(':', '').replace('+', 'Z')}"
        run_dir = workspace.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        normalized = normalize_brief(
            str(Path(args.brief_file).expanduser().resolve()),
            root,
            "v0_4",
        )
        brief_path = run_dir / "raw_brief.json"
        write_json(brief_path, normalized)
        manager = ManagerOrchestrator(
            root,
            run_dir,
            data_root=workspace.data_dir,
            spawn_adapter=args.spawn_adapter,
            contract_profile="v0_4",
        )
        prepared = manager.initialize_run(brief_path)
        _print_json(
            _report_response(
                run_dir=run_dir,
                result=prepared,
                manager=manager,
                run_id=run_id,
                brief_path=str(brief_path),
            )
        )
        return

    run_dir = workspace.run_dir(args.run)
    manager = ManagerOrchestrator(
        root,
        run_dir,
        data_root=workspace.data_dir,
        spawn_adapter=getattr(args, "spawn_adapter", None),
    )

    if args.report_command == "status":
        _print_json({
            "ok": True,
            "run_dir": str(run_dir),
            "manager": manager.status_summary(),
        })
        return

    if args.report_command == "manager-status":
        _print_json({"ok": True, "run_dir": str(run_dir), "manager": manager.status().get("state", {})})
        return

    if args.report_command == "manager-plan":
        _print_json({"ok": True, "run_dir": str(run_dir), "manager_plan": manager.status().get("plan", {})})
        return

    if args.report_command == "next":
        try:
            prepared = manager.prepare()
        except StepError as exc:
            _print_json({"ok": False, "error": str(exc), "manager": manager.status_summary()})
            raise SystemExit(3)
        _print_json(_report_response(run_dir=run_dir, result=prepared, manager=manager))
        return

    if args.report_command == "continue":
        try:
            result = manager.continue_until_boundary(max_steps=max(1, args.max_steps))
        except StepError as exc:
            _print_json({"ok": False, "error": str(exc), "manager": manager.status_summary()})
            raise SystemExit(3)
        _print_json(_report_response(run_dir=run_dir, result=result, manager=manager))
        return

    if args.report_command == "submit":
        state = manager.status().get("state", {})
        actor = state.get("current_actor")
        commit_attempted = False
        try:
            if actor == "manager":
                if args.output_file:
                    manager.copy_manager_output(Path(args.output_file).expanduser().resolve())
                result = manager.commit_manager()
            elif actor == "worker":
                stage_dir = manager.current_worker_dir(state)
                if stage_dir is None:
                    raise StepError("Manager state 缺少当前 Worker task_dir")
                runner = StepRunner(
                    root,
                    stage_dir,
                    data_root=workspace.data_dir,
                    contract_profile=state.get("contract_profile"),
                )
                if args.output_file:
                    _copy_report_output(runner, Path(args.output_file).expanduser().resolve())
                if state.get("spawn_adapter") != "inline":
                    if not args.spawn_completed:
                        raise StepError(
                            "当前 Worker 使用非 inline adapter；必须由真实 sub-agent "
                            "完成后使用 report submit --spawn-completed。"
                        )
                    manager.record_spawn_completed()
                commit_attempted = True
                worker_result = runner.commit()
                if worker_result.get("step") == "done":
                    result = manager.record_worker_completed(worker_result)
                else:
                    result = manager.prepare()
            elif actor == "human":
                raise StepError("当前等待人工确认，请调用 report approve 或先提供反馈")
            else:
                raise StepError(f"未知 current_actor: {actor}")
        except StepError as exc:
            if actor == "worker" and commit_attempted:
                try:
                    result = manager.record_worker_failure(exc)
                except StepError:
                    pass
                else:
                    _print_json(_report_response(run_dir=run_dir, result=result, manager=manager))
                    return
            _print_json({"ok": False, "error": str(exc), "manager": manager.status_summary()})
            raise SystemExit(3)
        _print_json(_report_response(run_dir=run_dir, result=result, manager=manager))
        return

    if args.report_command == "approve":
        try:
            selected_run_mode = getattr(args, "run_mode", None)
            if selected_run_mode == "custom":
                selected_run_mode = list(getattr(args, "pause_after", []))
                if not selected_run_mode:
                    raise StepError(
                        "--run-mode custom 至少需要一个 --pause-after"
                    )
            result = manager.approve(
                run_mode=selected_run_mode,
                delivery_option=getattr(args, "delivery_option", None),
            )
        except StepError as exc:
            _print_json({"ok": False, "error": str(exc), "manager": manager.status_summary()})
            raise SystemExit(3)
        response = _report_response(run_dir=run_dir, result=result, manager=manager)
        if isinstance(result, dict) and result.get("status") == "completed":
            response["next_action"] = "completed"
        _print_json(response)
        return

    if args.report_command == "feedback":
        try:
            result = manager.record_human_feedback(args.text)
        except StepError as exc:
            _print_json({"ok": False, "error": str(exc), "manager": manager.status_summary()})
            raise SystemExit(3)
        _print_json(_report_response(run_dir=run_dir, result=result, manager=manager))
        return


    if args.report_command == "revise":
        try:
            result = manager.revise_stage(args.stage, args.feedback)
        except StepError as exc:
            _print_json({"ok": False, "error": str(exc), "manager": manager.status_summary()})
            raise SystemExit(3)
        _print_json(_report_response(run_dir=run_dir, result=result, manager=manager))
        return


def _current_stage_dir(stepper: PipelineStepper, run_dir: Path) -> Path | None:
    status = stepper.pipeline_status()
    current = int(status.get("current_stage", 1))
    if current > len(stepper.ordered):
        return None
    spec = stepper.ordered[current - 1]
    return run_dir / f"stage_{spec.stage}_{spec.id}"


def _copy_report_output(runner: StepRunner, output_file: Path) -> None:
    status = runner.status()
    step = status.get("current_step")
    kind_map = {
        "awaiting_gen_output": "gen",
        "awaiting_revise_output": "revise",
    }
    kind = kind_map.get(str(step))
    if not kind:
        raise StepError(f"current step {step} is not awaiting host output")
    target = runner._handoff_output_path(kind)
    target.write_text(output_file.read_text(encoding="utf-8"), encoding="utf-8")


def _mark_pipeline_completed(run_dir: Path) -> None:
    from presentation_agent.io import read_json, write_json

    state_path = run_dir / "pipeline_state.json"
    state = read_json(state_path, default={})
    state["status"] = "completed"
    write_json(state_path, state)


def _mark_stage_approved(stage_dir: Path) -> None:
    from presentation_agent.io import read_json, write_json
    from presentation_agent.models import now_iso

    state_path = stage_dir / "run_state.json"
    state = read_json(state_path, default={})
    state["status"] = "approved"
    state["approved_at"] = now_iso()
    state.setdefault("history", []).append(
        {"at": state["approved_at"], "step": "human_review", "message": "Stage approved by human"}
    )
    write_json(state_path, state)


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
