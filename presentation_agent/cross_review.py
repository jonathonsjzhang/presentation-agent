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
        upstream = self._load_upstream_artifact(state)
        if not upstream:
            return self._result("pass", [], "no upstream artifact")

        checks = {
            "storyline_design": self._check_storyline,
            "page_filling": self._check_page_filling,
            "format": self._check_format,
            "qa_preparation": self._check_qa,
            "speaker_script": self._check_speaker_script,
        }
        checker = checks.get(agent_id)
        if not checker:
            return self._result("pass", [], "no cross-stage rule for this stage")
        return checker(upstream, artifact)

    def _load_upstream_artifact(self, state: dict[str, Any]) -> Optional[dict[str, Any]]:
        input_path = state.get("input_path")
        if not input_path:
            return None
        path = Path(str(input_path))
        if not path.exists():
            return None
        data = read_json(path, default={})
        return data if isinstance(data, dict) else None

    def _check_storyline(self, upstream: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        current_text = flatten_text(artifact)
        for key in ("core_conclusion", "expected_action"):
            value = str(upstream.get(key) or "").strip()
            if value and value not in current_text:
                issues.append({
                    "severity": "P1",
                    "dimension": "cross_stage_consistency",
                    "message": f"storyline 可能未显式承接上游 {key}",
                    "suggested_owner": "storyline_design",
                })
        issues.extend(self._execution_amplification_issues(upstream, artifact, "storyline_design"))
        return self._result("warn" if issues else "pass", issues, "storyline upstream alignment checked")

    def _check_page_filling(self, upstream: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        current_text = flatten_text(artifact)
        missing_titles = []
        for page in upstream.get("pages", []) if isinstance(upstream.get("pages"), list) else []:
            leadline = str(page.get("leadline") or page.get("title") or "").strip() if isinstance(page, dict) else ""
            if leadline and leadline not in current_text:
                missing_titles.append(leadline)
        if missing_titles:
            issues.append({
                "severity": "P1",
                "dimension": "cross_stage_consistency",
                "message": f"page_filling 可能丢失或改写 {len(missing_titles)} 个受保护的 storyline leadline",
                "evidence": missing_titles[:3],
                "suggested_owner": "page_filling",
            })
        issues.extend(self._execution_amplification_issues(upstream, artifact, "page_filling"))
        return self._result("warn" if issues else "pass", issues, "page filling storyline retention checked")

    def _check_format(self, upstream: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        current_text = flatten_text(artifact)
        if "source_notes" in upstream and "source" not in current_text and "来源" not in current_text:
            issues.append({
                "severity": "P1",
                "dimension": "source_retention",
                "message": "format 产物可能未保留上游 source_notes / 来源说明",
                "suggested_owner": "format",
            })
        if "open_questions" in upstream and "open" not in current_text and "待补" not in current_text:
            issues.append({
                "severity": "P1",
                "dimension": "open_question_retention",
                "message": "format 产物可能未保留上游 open_questions / 待补问题",
                "suggested_owner": "format",
            })
        issues.extend(self._execution_amplification_issues(upstream, artifact, "format"))
        return self._result("warn" if issues else "pass", issues, "format retention checked")

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
        upstream_text = flatten_text(upstream)
        current_text = flatten_text(artifact)
        risk_markers = [word for word in ("风险", "risk", "open_questions", "待补") if word in upstream_text]
        if risk_markers and not any(word in current_text for word in ("风险", "追问", "question", "answer")):
            return self._result("warn", [{
                "severity": "P1",
                "dimension": "risk_coverage",
                "message": "Q&A 可能未覆盖正式材料中的风险或待补问题",
                "suggested_owner": "qa_preparation",
            }], "qa risk coverage checked")
        return self._result("pass", [], "qa risk coverage checked")

    def _check_speaker_script(self, upstream: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
        upstream_text = flatten_text(upstream)
        current_text = flatten_text(artifact)
        if "target_action" in upstream_text and "action" not in current_text and "行动" not in current_text:
            return self._result("warn", [{
                "severity": "P1",
                "dimension": "action_closure",
                "message": "逐字稿可能未回到正式材料的目标 action",
                "suggested_owner": "speaker_script",
            }], "speaker script action closure checked")
        return self._result("pass", [], "speaker script alignment checked")

    @staticmethod
    def _result(status: str, issues: list[dict[str, Any]], note: str) -> dict[str, Any]:
        return {
            "version": "cross_stage_review.v1",
            "status": status,
            "issues": issues,
            "note": note,
        }
