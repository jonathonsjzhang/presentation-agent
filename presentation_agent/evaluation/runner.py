from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from presentation_agent.evaluation.adapters import (
    ArtifactPreparationError,
    extract_context_text,
    prepare_artifact,
)
from presentation_agent.io import read_json, write_json
from presentation_agent.llm.schema import validate
from presentation_agent.models import now_iso


class EvalError(RuntimeError):
    pass


_JOB_DIMENSIONS = {
    "content": ["information_density", "storyline", "expression"],
    "visual": ["information_presentation"],
}


class EvaluationRunner:
    """Host-self-executed E2E evaluator for PPT, DOCX, and HTML artifacts."""

    def __init__(
        self,
        root: Path,
        run_dir: Path | None = None,
        runs_root: Path | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.run_dir = Path(run_dir).resolve() if run_dir else None
        self.runs_root = Path(runs_root).resolve() if runs_root else None

    @classmethod
    def resolve_run(
        cls,
        root: Path,
        value: str | Path,
        runs_root: Path | None = None,
    ) -> Path:
        candidate = Path(value).expanduser()
        if candidate.exists():
            return candidate.resolve()
        if runs_root is not None:
            workspace_candidate = Path(runs_root).resolve() / str(value)
            if workspace_candidate.exists():
                return workspace_candidate
        return (Path(root).resolve() / "artifacts" / "evals" / str(value)).resolve()

    def start(
        self,
        artifact_path: Path,
        *,
        brief_path: Path | None = None,
        material_paths: list[Path] | None = None,
        rubric_version: str = "v0.2",
        render_visuals: bool = True,
    ) -> dict[str, Any]:
        if self.run_dir is None:
            run_id = f"eval-{now_iso().replace(':', '').replace('+', 'Z')}-{uuid4().hex[:8]}"
            base = self.runs_root or (self.root / "artifacts" / "evals")
            self.run_dir = base / run_id
        if self.state_path.exists():
            raise EvalError(f"Evaluation run already exists: {self.run_dir}")

        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.handoff_dir.mkdir(parents=True, exist_ok=True)
        prepared_dir = self.run_dir / "prepared"
        rubric = self._load_rubric(rubric_version)
        schema = self._load_judgement_schema()

        try:
            prepared = prepare_artifact(
                artifact_path,
                prepared_dir,
                render_visuals=render_visuals,
            )
        except ArtifactPreparationError as exc:
            raise EvalError(str(exc)) from exc

        brief = Path(brief_path).expanduser().resolve() if brief_path else None
        materials = [
            Path(path).expanduser().resolve() for path in (material_paths or [])
        ]
        missing_inputs = [
            str(path) for path in ([brief] if brief else []) + materials if not path.exists()
        ]
        if missing_inputs:
            raise EvalError(f"Evaluation input does not exist: {missing_inputs}")

        context_text = self._build_context_text(brief, materials)
        context_path = prepared_dir / "evaluation_context.txt"
        context_path.write_text(context_text, encoding="utf-8")
        write_json(self.run_dir / "rubric_snapshot.json", rubric)
        write_json(self.run_dir / "judgement_schema_snapshot.json", schema)
        write_json(self.run_dir / "prepared_artifact.json", prepared.to_dict())

        hard_gates = self._hard_gates(prepared.to_dict())
        write_json(self.run_dir / "deterministic_checks.json", hard_gates)

        state = {
            "schema": "e2e_eval_state.v1",
            "run_id": self.run_dir.name,
            "status": "running",
            "rubric_version": rubric["version"],
            "artifact_path": prepared.artifact_path,
            "artifact_format": prepared.format,
            "brief_path": str(brief) if brief else None,
            "material_paths": [str(path) for path in materials],
            "prepared_artifact_path": str(self.run_dir / "prepared_artifact.json"),
            "context_path": str(context_path),
            "hard_gates_path": str(self.run_dir / "deterministic_checks.json"),
            "current_job": "content",
            "jobs": {
                "content": {"status": "pending"},
                "visual": {"status": "pending"},
            },
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        write_json(self.state_path, state)
        prepared_job = self.prepare()
        return {
            "run_id": state["run_id"],
            "run_dir": str(self.run_dir),
            "state": state,
            "instruction": prepared_job,
            "hard_gates": hard_gates,
        }

    def status(self) -> dict[str, Any]:
        self._require_run()
        return read_json(self.state_path)

    def prepare(self) -> dict[str, Any]:
        state = self.status()
        if state["status"] == "completed":
            return {
                "status": "completed",
                "result_path": str(self.run_dir / "final_report.json"),
            }
        job = str(state.get("current_job") or "")
        if job not in _JOB_DIMENSIONS:
            raise EvalError(f"Unknown evaluation job: {job!r}")

        instruction_path = self.handoff_dir / f"instruction_{job}.md"
        output_path = self.handoff_dir / f"output_{job}.json"
        instruction_path.write_text(
            self._build_instruction(job, output_path),
            encoding="utf-8",
        )
        state["jobs"][job].update(
            {
                "status": "awaiting_host_output",
                "instruction_path": str(instruction_path),
                "output_path": str(output_path),
            }
        )
        state["updated_at"] = now_iso()
        write_json(self.state_path, state)
        return {
            "actor": f"{job}_judge",
            "job": job,
            "instruction_path": str(instruction_path),
            "output_path": str(output_path),
            "next_action": "host_execute_instruction_then_eval_submit",
        }

    def submit(self, output_file: Path | None = None) -> dict[str, Any]:
        state = self.status()
        if state["status"] == "completed":
            return {
                "status": "completed",
                "result_path": str(self.run_dir / "final_report.json"),
            }
        job = str(state.get("current_job") or "")
        if job not in _JOB_DIMENSIONS:
            raise EvalError(f"Unknown evaluation job: {job!r}")
        output_path = self.handoff_dir / f"output_{job}.json"
        if output_file:
            source = Path(output_file).expanduser().resolve()
            if not source.exists():
                raise EvalError(f"Judge output does not exist: {source}")
            output_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        if not output_path.exists():
            raise EvalError(f"Judge output does not exist: {output_path}")

        try:
            judgement = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise EvalError(f"Judge output is not valid JSON: {exc}") from exc
        self._validate_judgement(job, judgement)
        accepted_path = self.run_dir / f"judgement_{job}.json"
        write_json(accepted_path, judgement)
        state["jobs"][job].update(
            {
                "status": "accepted",
                "judgement_path": str(accepted_path),
                "completed_at": now_iso(),
            }
        )

        if job == "content":
            state["current_job"] = "visual"
            state["updated_at"] = now_iso()
            write_json(self.state_path, state)
            prepared = self.prepare()
            return {
                "status": "running",
                "completed_job": "content",
                "next_instruction": prepared,
            }

        report = self._aggregate()
        write_json(self.run_dir / "final_report.json", report)
        state["status"] = "completed"
        state["current_job"] = None
        state["result_path"] = str(self.run_dir / "final_report.json")
        state["completed_at"] = now_iso()
        state["updated_at"] = now_iso()
        write_json(self.state_path, state)
        return {
            "status": "completed",
            "result_path": state["result_path"],
            "report": report,
        }

    @property
    def state_path(self) -> Path:
        if self.run_dir is None:
            raise EvalError("Evaluation run directory is not initialized")
        return self.run_dir / "run_state.json"

    @property
    def handoff_dir(self) -> Path:
        if self.run_dir is None:
            raise EvalError("Evaluation run directory is not initialized")
        return self.run_dir / "handoff"

    def _require_run(self) -> None:
        if self.run_dir is None or not self.state_path.exists():
            raise EvalError(f"Evaluation run state not found: {self.run_dir}")

    def _load_rubric(self, version: str) -> dict[str, Any]:
        aliases = {
            "report-v0.3": "e2e_report_v0.3.json",
            "translation-v0.3": "e2e_translation_v0.3.json",
        }
        normalized = version if version.startswith("v") else f"v{version}"
        filename = aliases.get(version, f"e2e_material_{normalized}.json")
        path = self.root / "evals" / "rubrics" / filename
        if not path.exists():
            raise EvalError(f"E2E rubric version not found: {normalized} ({path})")
        rubric = read_json(path)
        dimensions = rubric.get("dimensions") or []
        weights = sum(float(item.get("weight", 0)) for item in dimensions)
        if abs(weights - 1.0) > 1e-9:
            raise EvalError(f"Rubric weights must sum to 1.0, got {weights}")
        return rubric

    def _load_judgement_schema(self) -> dict[str, Any]:
        path = self.root / "evals" / "schemas" / "e2e_judgement.v1.json"
        if not path.exists():
            raise EvalError(f"E2E judgement schema not found: {path}")
        return read_json(path)

    @staticmethod
    def _build_context_text(brief: Path | None, materials: list[Path]) -> str:
        sections: list[str] = []
        if brief:
            sections.extend(
                [
                    f"## Brief\nPath: {brief}",
                    extract_context_text(brief, limit=30000),
                ]
            )
        for index, path in enumerate(materials, start=1):
            sections.extend(
                [
                    f"## Raw material {index}\nPath: {path}",
                    extract_context_text(path, limit=18000),
                ]
            )
        if not sections:
            return (
                "No brief or raw materials were supplied. Judge only the final artifact, "
                "and lower confidence where source fidelity cannot be verified."
            )
        return "\n\n".join(sections)

    @staticmethod
    def _hard_gates(prepared: dict[str, Any]) -> dict[str, Any]:
        visual_count = len(prepared.get("visual_paths") or [])
        unit_count = int(prepared.get("unit_count") or 0)
        fmt = prepared.get("format")
        coverage_passed = (
            visual_count == unit_count if fmt in {"ppt", "html"} and unit_count else visual_count > 0
        )
        checks = [
            {
                "id": "artifact_nonempty",
                "passed": int(prepared.get("file_bytes") or 0) > 0,
                "blocking": True,
                "detail": f"file_bytes={prepared.get('file_bytes', 0)}",
            },
            {
                "id": "supported_format",
                "passed": prepared.get("format") in {"ppt", "document", "html"},
                "blocking": True,
                "detail": str(prepared.get("format")),
            },
            {
                "id": "visual_snapshots_ready",
                "passed": visual_count > 0,
                "blocking": True,
                "detail": f"visual_count={visual_count}",
            },
            {
                "id": "visual_coverage_complete",
                "passed": coverage_passed,
                "blocking": True,
                "detail": f"format={fmt}; unit_count={unit_count}; visual_count={visual_count}",
            },
            {
                "id": "text_extractable",
                "passed": Path(str(prepared.get("extracted_text_path", ""))).exists()
                and Path(str(prepared.get("extracted_text_path", ""))).stat().st_size > 0,
                "blocking": False,
                "detail": str(prepared.get("extracted_text_path", "")),
            },
        ]
        return {
            "schema": "e2e_deterministic_checks.v1",
            "passed": all(
                check["passed"] for check in checks if check.get("blocking")
            ),
            "checks": checks,
            "warnings": list(prepared.get("warnings") or []),
        }

    def _build_instruction(self, job: str, output_path: Path) -> str:
        state = self.status()
        rubric = read_json(self.run_dir / "rubric_snapshot.json")
        schema = read_json(self.run_dir / "judgement_schema_snapshot.json")
        prepared = read_json(self.run_dir / "prepared_artifact.json")
        dimensions = [
            item
            for item in rubric["dimensions"]
            if item.get("judge_role") == job
        ]

        lines = [
            f"# 汇报材料 E2E {job.title()} Judge",
            "",
            "你是独立评测 Agent。你没有参与候选材料生成，不读取生产 Agent 的自评、review、memory 或返工过程。",
            "只依据本轮冻结的 rubric 和给定输入评分，不创造新评价维度，也不替作者重写材料。",
            "",
            "## 评测对象",
            "",
            f"- 最终材料：`{prepared['artifact_path']}`",
            f"- 格式：`{prepared['format']}`",
            f"- 提取文本：`{prepared['extracted_text_path']}`",
            f"- Brief / raw material 摘要：`{state['context_path']}`",
        ]
        if state.get("brief_path"):
            lines.append(f"- 原始 brief：`{state['brief_path']}`")
        for path in state.get("material_paths") or []:
            lines.append(f"- 原始素材：`{path}`")

        if job == "content":
            lines.extend(
                [
                    "",
                    "## 本轮任务",
                    "",
                    "评估信息密度、Storyline、表达精炼三个维度。",
                    "必须对照 brief/raw material 与最终材料，判断已有材料是否被正确组织和表达。",
                    "不要因为页面看起来整洁就假定信息密度高；不要把 Agent 未创造新研究洞察本身作为扣分项。",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "## 视觉输入（必须实际查看）",
                    "",
                    f"- Contact sheet：`{prepared.get('contact_sheet_path') or '未生成'}`",
                    *[f"- 页面 {index}：`{path}`" for index, path in enumerate(prepared.get("visual_paths") or [], start=1)],
                    "",
                    "必须使用视觉/图片查看能力逐张检查所有页面截图；不得只根据提取文本或文件名评分。",
                    str(
                        dimensions[0]
                        .get("format_guidance", {})
                        .get(prepared["format"], "")
                    ),
                ]
            )

        lines.extend(
            [
                "",
                "## 冻结 Rubric",
                "",
                "```json",
                json.dumps(
                    {
                        "version": rubric["version"],
                        "scope": rubric["scope"],
                        "scale": rubric["scale"],
                        "dimensions": dimensions,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "```",
                "",
                "## 评分规则",
                "",
                "- 每个维度只能使用 0–5 分，允许 0.5 分刻度。",
                "- 必须提供具体页码/章节/模块证据，不能只写抽象感受。",
                "- issues 和 recommendations 必须直接对应本轮维度。",
                "- 评分判断材料当前质量，不因为“以后可以修改”而抬高分数。",
                "",
                "## 输出 Schema",
                "",
                "```json",
                json.dumps(schema, ensure_ascii=False, indent=2),
                "```",
                "",
                "## 输出操作",
                "",
                f"- `judge_role` 必须为 `{job}`。",
                f"- `rubric_version` 必须为 `{rubric['version']}`。",
                f"- `dimension_scores` 必须且只能包含：{self._job_dimensions(rubric, job)}。",
                f"- 只写严格 JSON 到 `{output_path}`，不要输出 Markdown 或解释。",
            ]
        )
        return "\n".join(lines) + "\n"

    def _validate_judgement(self, job: str, judgement: dict[str, Any]) -> None:
        schema = read_json(self.run_dir / "judgement_schema_snapshot.json")
        errors = validate(judgement, schema)
        if judgement.get("judge_role") != job:
            errors.append(
                f"$.judge_role: expected {job!r}, got {judgement.get('judge_role')!r}"
            )
        rubric = read_json(self.run_dir / "rubric_snapshot.json")
        if judgement.get("rubric_version") != rubric.get("version"):
            errors.append(
                "$.rubric_version: expected "
                f"{rubric.get('version')!r}, got {judgement.get('rubric_version')!r}"
            )
        scores = judgement.get("dimension_scores")
        if isinstance(scores, list):
            actual = [item.get("dimension_id") for item in scores if isinstance(item, dict)]
            rubric = read_json(self.run_dir / "rubric_snapshot.json")
            expected = self._job_dimensions(rubric, job)
            if sorted(actual) != sorted(expected) or len(actual) != len(set(actual)):
                errors.append(
                    f"$.dimension_scores: expected exactly {expected}, got {actual}"
                )
            for index, item in enumerate(scores):
                if not isinstance(item, dict):
                    continue
                if not item.get("evidence"):
                    errors.append(
                        f"$.dimension_scores[{index}].evidence: at least one concrete location is required"
                    )
                score = item.get("score")
                if not isinstance(score, (int, float)) or isinstance(score, bool):
                    continue
                if score < 0 or score > 5 or abs(score * 2 - round(score * 2)) > 1e-9:
                    errors.append(
                        f"$.dimension_scores[{index}].score: must be 0-5 in 0.5 increments"
                    )
        if job == "visual":
            prepared = read_json(self.run_dir / "prepared_artifact.json")
            expected_names = {
                Path(path).name for path in prepared.get("visual_paths") or []
            }
            inspected = judgement.get("inspected_visuals")
            inspected_names = {
                Path(str(path)).name for path in inspected or []
            } if isinstance(inspected, list) else set()
            missing = sorted(expected_names - inspected_names)
            if missing:
                errors.append(
                    "$.inspected_visuals: every rendered page must be listed; "
                    f"missing={missing}"
                )
        if errors:
            raise EvalError("Judge output validation failed:\n- " + "\n- ".join(errors))

    @staticmethod
    def _job_dimensions(rubric: dict[str, Any], job: str) -> list[str]:
        return [
            str(item["id"])
            for item in rubric.get("dimensions", [])
            if item.get("judge_role") == job
        ]

    def _aggregate(self) -> dict[str, Any]:
        rubric = read_json(self.run_dir / "rubric_snapshot.json")
        hard_gates = read_json(self.run_dir / "deterministic_checks.json")
        judgements = {
            role: read_json(self.run_dir / f"judgement_{role}.json")
            for role in ("content", "visual")
        }
        score_rows: dict[str, dict[str, Any]] = {}
        for role, judgement in judgements.items():
            for item in judgement["dimension_scores"]:
                score_rows[item["dimension_id"]] = {
                    **item,
                    "judge_role": role,
                }

        dimensions: list[dict[str, Any]] = []
        total = 0.0
        ranked_items: list[tuple[float, str, str]] = []
        for definition in rubric["dimensions"]:
            dimension_id = definition["id"]
            scored = score_rows[dimension_id]
            score = float(scored["score"])
            weight = float(definition["weight"])
            total += score * weight
            dimensions.append(
                {
                    "dimension_id": dimension_id,
                    "name": definition["name"],
                    "score": score,
                    "out_of": 5,
                    "weight": weight,
                    "weighted_score": round(score * weight, 3),
                    "rationale": scored["rationale"],
                    "evidence": scored["evidence"],
                    "issues": scored["issues"],
                    "recommendations": scored["recommendations"],
                    "judge_role": scored["judge_role"],
                }
            )
            priority = weight * (5.0 - score)
            for issue in scored["issues"]:
                ranked_items.append((priority, "issue", f"{definition['name']}：{issue}"))
            for recommendation in scored["recommendations"]:
                ranked_items.append(
                    (priority, "recommendation", f"{definition['name']}：{recommendation}")
                )

        ranked_items.sort(key=lambda row: (-row[0], row[2]))
        limit_issues = int(rubric.get("output_policy", {}).get("max_major_issues", 3))
        limit_recommendations = int(
            rubric.get("output_policy", {}).get("max_recommendations", 3)
        )
        issues = _unique_ranked(ranked_items, "issue", limit_issues)
        recommendations = _unique_ranked(
            ranked_items, "recommendation", limit_recommendations
        )
        total = round(total, 2)
        policy = rubric["release_policy"]
        min_score = min(item["score"] for item in dimensions)
        gates_passed = bool(hard_gates.get("passed"))
        if (
            gates_passed
            and total >= float(policy["formal_ready_threshold"])
            and min_score >= float(policy["minimum_dimension_score"])
        ):
            verdict = "formal_ready"
        elif gates_passed and total >= float(policy["internal_discussion_threshold"]):
            verdict = "needs_revision"
        else:
            verdict = "not_usable"

        state = self.status()
        return {
            "schema": "e2e_eval_report.v1",
            "run_id": state["run_id"],
            "artifact_path": state["artifact_path"],
            "artifact_format": state["artifact_format"],
            "rubric_version": rubric["version"],
            "scores": dimensions,
            "total_score": total,
            "total_out_of": 5,
            "normalized_score_100": round(total * 20, 1),
            "hard_gates": hard_gates,
            "verdict": verdict,
            "major_issues": issues,
            "recommendations": recommendations,
            "judge_assessments": {
                role: {
                    "confidence": judgement["confidence"],
                    "overall_assessment": judgement["overall_assessment"],
                }
                for role, judgement in judgements.items()
            },
            "created_at": now_iso(),
        }


def _unique_ranked(
    rows: list[tuple[float, str, str]],
    kind: str,
    limit: int,
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for _, row_kind, text in rows:
        if row_kind != kind or text in seen:
            continue
        result.append(text)
        seen.add(text)
        if len(result) >= limit:
            break
    return result
