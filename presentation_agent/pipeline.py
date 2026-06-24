from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from presentation_agent.io import write_json
from presentation_agent.loop import LoopRunner
from presentation_agent.models import now_iso


class Pipeline:
    """Chain the seven agents into one report-building flow.

    Each stage's approved artifact becomes the next stage's input. Two modes,
    both honoring the design's human-in-the-loop principle:

    - stepwise (default): run one stage, stop at its human_review, and wait. The
      caller resumes the pipeline once the human approves. Safe and reviewable.
    - auto (`--auto`): run all reachable stages back to back, stopping only when
      a stage is blocked by an open P0. Convenient for debugging / dry runs.

    The pipeline never re-implements agent logic; it only orchestrates LoopRunner
    runs and passes artifacts downstream.
    """

    def __init__(self, root: Path, provider_override: Optional[str] = None) -> None:
        self.root = root
        self.runner = LoopRunner(root, provider_override=provider_override)
        self.stages = self._ordered_stages()

    def _ordered_stages(self):
        """Order stages by the top-level pipeline.stages list when present.

        Falls back to the per-agent `stage` number. This lets agents.json
        declare the canonical sequence in one place (pipeline.stages) instead of
        relying solely on scattered stage integers.
        """
        declared = self.runner.config.get("pipeline", {}).get("stages")
        specs_by_id = {spec.id: spec for spec in self.runner.list_agents()}
        if declared:
            ordered = [specs_by_id[sid] for sid in declared if sid in specs_by_id]
            if ordered:
                return ordered
        return self.runner.list_agents()

    def run(
        self,
        initial_input: Path,
        run_dir: Optional[Path] = None,
        auto: bool = False,
        start_stage: int = 1,
    ) -> dict[str, Any]:
        pipeline_id = f"pipeline-{now_iso().replace(':', '').replace('+', 'Z')}"
        out_root = run_dir or (self.root / "artifacts" / pipeline_id)
        out_root.mkdir(parents=True, exist_ok=True)

        stage_records: list[dict[str, Any]] = []
        current_input = Path(initial_input)
        status = "completed"
        stopped_reason = ""

        for spec in self.stages:
            if spec.stage < start_stage:
                continue
            stage_dir = out_root / f"stage_{spec.stage}_{spec.id}"
            result = self.runner.run(spec.id, current_input, stage_dir)
            record = {
                "stage": spec.stage,
                "agent_id": spec.id,
                "agent_name": spec.name,
                "status": result["status"],
                "artifact_path": result["artifact_path"],
                "human_review_path": result["human_review_path"],
                "stop_decision": result["stop_decision"],
            }
            stage_records.append(record)

            if result["status"] == "blocked_needs_human":
                status = "blocked"
                stopped_reason = f"stage {spec.stage} ({spec.id}) blocked by open P0; human must intervene"
                break

            # the just-produced artifact is the next stage's input
            current_input = Path(result["artifact_path"])

            if not auto:
                status = "awaiting_human_review"
                stopped_reason = (
                    f"stage {spec.stage} ({spec.id}) finished and is pending human review; "
                    "approve then resume with --start-stage "
                    f"{spec.stage + 1}"
                )
                break

        summary = {
            "pipeline_id": pipeline_id,
            "mode": "auto" if auto else "stepwise",
            "status": status,
            "stopped_reason": stopped_reason,
            "output_dir": str(out_root),
            "stages": stage_records,
            "created_at": now_iso(),
        }
        write_json(out_root / "pipeline_result.json", summary)
        self._write_overview(out_root, summary)
        return summary

    def _write_overview(self, out_root: Path, summary: dict[str, Any]) -> None:
        lines = [
            "# Pipeline run overview",
            "",
            f"- pipeline_id: {summary['pipeline_id']}",
            f"- mode: {summary['mode']}",
            f"- status: {summary['status']}",
        ]
        if summary["stopped_reason"]:
            lines.append(f"- note: {summary['stopped_reason']}")
        lines.extend(["", "## Stages", ""])
        for record in summary["stages"]:
            lines.append(
                f"- stage {record['stage']} {record['agent_id']} ({record['agent_name']}): "
                f"{record['status']} -> {record['artifact_path']}"
            )
        if not summary["stages"]:
            lines.append("- (none ran)")
        (out_root / "pipeline_overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
