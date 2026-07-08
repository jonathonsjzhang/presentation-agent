from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Optional

from presentation_agent.io import flatten_text, read_json


class CrossStageReviewer:
    """Lightweight cross-stage consistency checks for ManagerController.

    This first version is intentionally conservative: it records warnings and
    possible blocks, but never rewrites artifacts or advances/rolls back stages.
    """

    def __init__(self, root: Path, run_dir: Path) -> None:
        self.root = root
        self.run_dir = run_dir

    def review_stage(self, stage_dir: Path) -> dict[str, Any]:
        state_path = stage_dir / "run_state.json"
        artifact_path = stage_dir / "artifact.json"
        if not state_path.exists() or not artifact_path.exists():
            return self._result("pass", [], "stage artifact is not ready")

        state = read_json(state_path, default={})
        agent_id = str(state.get("agent_id") or "")
        if state.get("current_step") != "done":
            return self._result("pass", [], "stage is not done")

        artifact = read_json(artifact_path, default={})
        upstream = self._load_upstream_artifact(state, agent_id)
        if not upstream:
            return self._result("pass", [], "no upstream artifact")

        checks = {
            "storyline": self._check_analysis_to_storyline,
            "report": self._check_storyline_to_report,
            "format": self._check_report_to_format,
            "qa_preparation": self._check_qa,
        }
        checker = checks.get(agent_id)
        if not checker:
            return self._result("pass", [], "no cross-stage rule for this stage")
        return checker(upstream, artifact)

    def _check_analysis_to_storyline(
        self, upstream: dict[str, Any], artifact: dict[str, Any]
    ) -> dict[str, Any]:
        finding_ids = self._ids(upstream.get("findings"), "id")
        referenced = self._collect_ref_values(artifact, {"finding_refs"})
        unsupported_refs = sorted(referenced - finding_ids)
        issues: list[dict[str, Any]] = []
        if unsupported_refs:
            issues.append(self._issue(
                "P0", "unsupported_viewpoint",
                "Storyline 引用了 Analysis 中不存在的 finding",
                {"unknown_finding_refs": unsupported_refs},
                "storyline",
            ))
        return self._result(
            "block" if issues else "pass",
            issues,
            "storyline finding references checked; full finding coverage is intentionally not required",
        )

    def _check_storyline_to_report(
        self, upstream: dict[str, Any], artifact: dict[str, Any]
    ) -> dict[str, Any]:
        markdown = str(artifact.get("report_markdown") or "")
        headings = [
            str(row.get("heading") or "")
            for row in upstream.get("sections") or []
            if isinstance(row, dict)
        ]
        missing = [heading for heading in headings if heading and heading not in markdown]
        issues = []
        if missing:
            issues.append(self._issue(
                "P1", "storyline_heading_literal",
                "Report 未逐字保留部分 Storyline heading；若只是为可读性压缩标题，不应阻断流程",
                {"missing_headings": missing},
                "report",
            ))
        return self._result(
            "pass",
            issues,
            "approved storyline heading literals checked as a non-blocking signal",
        )

    def _check_report_to_format(
        self, upstream: dict[str, Any], artifact: dict[str, Any]
    ) -> dict[str, Any]:
        markdown = str(upstream.get("report_markdown") or "")
        headings = {
            line[3:].strip()
            for line in markdown.splitlines()
            if line.startswith("## ")
        }
        unknown = sorted({
            str(row.get("section_heading") or "")
            for row in artifact.get("visuals") or []
            if isinstance(row, dict)
            and row.get("section_heading") not in headings
        })
        issues = []
        if unknown:
            issues.append(self._issue(
                "P0", "visual_section_mapping",
                "Format visual 指向报告中不存在的章节",
                {"unknown_headings": unknown},
                "format",
            ))
        return self._result(
            "block" if issues else "pass",
            issues,
            "visual-to-manuscript section mapping checked",
        )

    def _load_upstream_artifact(
        self, state: dict[str, Any], agent_id: str
    ) -> Optional[dict[str, Any]]:
        input_path = state.get("input_path")
        if not input_path:
            return None
        path = Path(str(input_path))
        if not path.exists():
            return None
        data = read_json(path, default={})
        if not isinstance(data, dict):
            return None
        if data.get("schema") != "worker_context.v1":
            return data
        alias = {
            "storyline": "analysis",
            "report": "storyline",
            "format": "report",
            "qa_preparation": "report",
        }.get(agent_id)
        canonical = data.get(alias) if alias else None
        return canonical if isinstance(canonical, dict) else None

    @staticmethod
    def _execution_amplification_issues(
        upstream: dict[str, Any],
        artifact: dict[str, Any],
        owner: str,
    ) -> list[dict[str, Any]]:
        patterns = [
            r"(?:未来|在)?\s*\d+\s*[-–~至]\s*\d+\s*(?:周|月|季度|年)(?:内)?\s*(?:完成|推进|实现|上线|评估|落地)",
            r"\bQ[1-4]\b.{0,8}(?:路线图|完成|推进|上线|落地)",
            r"\bH[12]\b.{0,8}(?:路线图|完成|推进|上线|落地)",
            r"路线图|甘特图|里程碑|KPI|负责人|成立.{0,8}(?:团队|小组)",
        ]
        upstream_text = flatten_text(upstream)
        current_text = flatten_text(artifact)
        upstream_hits = {
            match.group(0)
            for pattern in patterns
            for match in re.finditer(pattern, upstream_text, flags=re.IGNORECASE)
        }
        current_hits = {
            match.group(0)
            for pattern in patterns
            for match in re.finditer(pattern, current_text, flags=re.IGNORECASE)
        }
        added = sorted(current_hits - upstream_hits)
        if not added:
            return []
        return [{
            "severity": "P0",
            "dimension": "recommendation_scope",
            "message": f"{owner} 新增了上游不存在的执行化细节",
            "evidence": added[:5],
            "suggested_owner": owner,
        }]

    def _check_qa(self, upstream: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
        upstream_markdown = str(upstream.get("report_markdown") or "").strip()
        current_markdown = str(artifact.get("report_markdown") or "").strip()
        issues: list[dict[str, Any]] = []
        if not current_markdown.startswith(upstream_markdown):
            issues.append(self._issue(
                "P0",
                "qa_rewrites_report",
                "Q&A 只能在报告末尾追加追问清单，不应改写既有正文",
                {},
                "qa_preparation",
            ))
        appended = current_markdown[len(upstream_markdown):].strip()
        question_markers = ("?", "？")
        if not appended or "追问" not in appended or not any(
            marker in appended for marker in question_markers
        ):
            issues.append(self._issue(
                "P1",
                "missing_question_list",
                "Q&A 未在报告末尾追加可识别的深度追问清单",
                {},
                "qa_preparation",
            ))
        return self._result(
            "block" if any(issue["severity"] == "P0" for issue in issues) else "warn" if issues else "pass",
            issues,
            "qa appended-question section checked",
        )

    @staticmethod
    def _result(status: str, issues: list[dict[str, Any]], note: str) -> dict[str, Any]:
        return {
            "version": "cross_stage_review.v1",
            "status": status,
            "issues": issues,
            "note": note,
        }

    @staticmethod
    def _ids(rows: Any, key: str) -> set[str]:
        return {
            str(row[key]) for row in rows or []
            if isinstance(row, dict) and row.get(key)
        }

    @classmethod
    def _collect_ref_values(cls, value: Any, keys: set[str]) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for key, child in value.items():
                if key in keys:
                    if isinstance(child, list):
                        found.update(str(item) for item in child)
                    elif child:
                        found.add(str(child))
                else:
                    found.update(cls._collect_ref_values(child, keys))
        elif isinstance(value, list):
            for child in value:
                found.update(cls._collect_ref_values(child, keys))
        return found

    @staticmethod
    def _normalized_text(value: Any) -> str:
        return re.sub(r"[\s，。；：、,.；:（）()]+", "", flatten_text(value)).lower()

    @classmethod
    def _caveat_preserved(cls, caveat: str, target_text: str) -> bool:
        normalized = cls._normalized_text(caveat)
        if normalized in target_text:
            return True
        # Deterministic risk-marker fallback permits wording changes while
        # requiring the same epistemic boundary to remain explicit.
        marker_groups = (
            ("因果", "因果"),
            ("非随机", "非随机"),
            ("访谈", "访谈"),
            ("样本", "样本"),
            ("不能", "不能"),
            ("待验证", "待验证"),
        )
        markers = [target for source, target in marker_groups if source in normalized]
        if "机制探索" in normalized:
            markers.append("机制")
        return bool(markers) and all(marker in target_text for marker in markers)

    @staticmethod
    def _numbers(value: Any) -> set[str]:
        return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", flatten_text(value)))

    @staticmethod
    def _issue(
        severity: str,
        dimension: str,
        message: str,
        evidence: Any,
        owner: str,
    ) -> dict[str, Any]:
        return {
            "severity": severity,
            "dimension": dimension,
            "message": message,
            "evidence": evidence,
            "suggested_owner": owner,
        }
