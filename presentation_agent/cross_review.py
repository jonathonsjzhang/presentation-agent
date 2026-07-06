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
            "speaker_script": self._check_speaker_script,
        }
        checker = checks.get(agent_id)
        if not checker:
            return self._result("pass", [], "no cross-stage rule for this stage")
        return checker(upstream, artifact)

    def _check_analysis_to_storyline(
        self, upstream: dict[str, Any], artifact: dict[str, Any]
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        finding_ids = self._ids(upstream.get("findings"), "finding_id")
        coverage = artifact.get("editorial_decisions", [])
        covered = [
            str(row.get("finding_id"))
            for row in coverage
            if isinstance(row, dict) and row.get("finding_id")
        ]
        advisory_fids = {
            str(fid)
            for request in artifact.get("upstream_revision_requests", [])
            if isinstance(request, dict)
            and request.get("blocking_level") == "advisory"
            for fid in request.get("finding_refs", [])
        }
        all_missing = finding_ids - set(covered)
        missing = sorted(all_missing - advisory_fids)
        advisory_missing = sorted(all_missing & advisory_fids)
        duplicate = sorted({item for item in covered if covered.count(item) > 1})
        unknown = sorted(set(covered) - finding_ids)
        if missing or duplicate or unknown:
            issues.append(self._issue(
                "P0", "finding_coverage",
                "Analysis findings 未被 Storyline 恰好登记一次",
                {"missing": missing, "duplicate": duplicate, "unknown": unknown},
                "storyline",
            ))
        if advisory_missing:
            issues.append(self._issue(
                "P1", "advisory_finding_coverage",
                "Advisory upstream revision 对应 finding 未登记 editorial disposition",
                {"advisory_missing": advisory_missing},
                "storyline",
            ))

        referenced = self._collect_ref_values(
            artifact, {"finding_refs", "finding_id"}
        )
        unsupported_refs = sorted(referenced - finding_ids)
        if unsupported_refs:
            issues.append(self._issue(
                "P0", "unsupported_viewpoint",
                "Storyline 新增了 Analysis 无法支持的 viewpoint / claim",
                {
                    "unknown_finding_refs": unsupported_refs,
                },
                "storyline",
            ))
        return self._result(
            "block" if any(row["severity"] == "P0" for row in issues) else "pass",
            issues,
            "analysis finding coverage and viewpoint support checked",
        )

    def _check_storyline_to_report(
        self, upstream: dict[str, Any], artifact: dict[str, Any]
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []

        # Build the set of finding IDs covered by advisory upstream_revision_requests.
        # The Storyline has already acknowledged these as data-limited gaps that
        # cannot be resolved with current materials.  When the Report inevitably
        # cannot perfectly preserve every ref / caveat for these findings, the gap
        # should be a P1 warning, not a pipeline-blocking P0.
        revision_requests = upstream.get("upstream_revision_requests", [])
        advisory_fids: set[str] = set()
        for req in revision_requests:
            if isinstance(req, dict) and req.get("blocking_level") == "advisory":
                for fid in req.get("finding_refs", []):
                    advisory_fids.add(str(fid))

        outline = upstream.get("report_outline", {}).get("sections", [])
        report_sections = artifact.get("section_manifest", [])
        expected = self._ids(outline, "section_id")
        actual = self._ids(report_sections, "section_id")
        if expected != actual:
            issues.append(self._issue(
                "P0", "section_coverage", "Report section coverage 不完整",
                {
                    "missing": sorted(expected - actual),
                    "unexpected": sorted(actual - expected),
                },
                "report",
            ))

        report_by_id = {
            str(row.get("section_id")): row
            for row in report_sections if isinstance(row, dict)
        }
        changed_headings = []
        missing_finding_refs: dict[str, list[str]] = {}
        advisory_missing_finding_refs: dict[str, list[str]] = {}
        missing_caveats: dict[str, list[str]] = {}
        advisory_missing_caveats: dict[str, list[str]] = {}
        for source in outline if isinstance(outline, list) else []:
            if not isinstance(source, dict):
                continue
            section_id = str(source.get("section_id") or "")
            target = report_by_id.get(section_id, {})
            if source.get("heading") != target.get("heading"):
                changed_headings.append(section_id)
            source_refs = set(map(str, source.get("finding_refs", [])))
            target_refs = set(map(str, target.get("finding_refs", [])))
            missing = source_refs - target_refs
            if missing:
                adv = missing & advisory_fids
                non_adv = missing - advisory_fids
                if adv:
                    advisory_missing_finding_refs[section_id] = sorted(adv)
                if non_adv:
                    missing_finding_refs[section_id] = sorted(non_adv)
            # Caveats are declared explicitly in section_manifest.caveats,
            # inherited verbatim from the storyline outline.  Direct field
            # comparison replaces the previous full-text scan, which was
            # fragile when the report_markdown rephrased boundary wording.
            source_caveats = set(
                str(c).strip() for c in source.get("caveats", []) if c
            )
            target_caveats = set(
                str(c).strip() for c in target.get("caveats", []) if c
            )
            absent = source_caveats - target_caveats
            if absent:
                # A caveat is "advisory-related" when its text references a
                # finding ID that belongs to an advisory revision request.
                adv_caveats = [
                    c for c in absent
                    if any(fid in str(c) for fid in advisory_fids)
                ]
                non_adv_caveats = [c for c in absent if c not in adv_caveats]
                if adv_caveats:
                    advisory_missing_caveats[section_id] = adv_caveats
                if non_adv_caveats:
                    missing_caveats[section_id] = non_adv_caveats

        if changed_headings or missing_finding_refs or missing_caveats:
            issues.append(self._issue(
                "P0", "storyline_fidelity",
                "Report 未保真承接 Storyline 的章节 / claim / caveat",
                {
                    "changed_headings": changed_headings,
                    "missing_finding_refs": missing_finding_refs,
                    "missing_caveats": missing_caveats,
                },
                "report",
            ))

        if advisory_missing_finding_refs or advisory_missing_caveats:
            issues.append(self._issue(
                "P1", "storyline_fidelity_advisory",
                "Report 中与 Storyline 已标注 advisory gap 的 finding 相关的 "
                "refs/caveats 未完整保留（数据限制已知，核心结论仍可成立，非阻断）",
                {
                    "advisory_missing_finding_refs": advisory_missing_finding_refs,
                    "advisory_missing_caveats": advisory_missing_caveats,
                },
                "report",
            ))

        return self._result(
            "block" if any(row.get("severity") == "P0" for row in issues) else "pass",
            issues,
            "storyline section coverage and fidelity checked",
        )

    def _check_report_to_format(
        self, upstream: dict[str, Any], artifact: dict[str, Any]
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        target = str(artifact.get("delivery_target") or "document")
        section_ids = self._ids(upstream.get("section_manifest"), "section_id")
        claim_ids = self._collect_ref_values(
            upstream.get("section_manifest", []), {"claim_ids"}
        )
        omitted_refs = {
            str(row.get("source_ref"))
            for row in artifact.get("omitted_content_register", [])
            if isinstance(row, dict) and row.get("source_ref")
        }
        mapped_sections = set(map(str, artifact.get("source_section_ids", [])))
        mapped_claims = set(map(str, artifact.get("source_claim_ids", [])))
        unit_section_refs = self._collect_ref_values(
            artifact.get("delivery_units", []), {"source_section_ids"}
        )
        unit_claim_refs = self._collect_ref_values(
            artifact.get("delivery_units", []), {"source_claim_ids"}
        )
        missing_sections = section_ids - mapped_sections
        missing_claims = claim_ids - mapped_claims
        sections_without_unit = section_ids - unit_section_refs
        claims_without_unit = claim_ids - unit_claim_refs
        mapping_evidence = {
            "missing_sections": sorted(
                missing_sections
            ),
            "missing_claims": sorted(
                missing_claims
            ),
            "unmapped_unit_sections": sorted(unit_section_refs - section_ids),
            "unmapped_unit_claims": sorted(unit_claim_refs - claim_ids),
            "sections_without_unit": sorted(
                sections_without_unit
            ),
            "claims_without_unit": sorted(
                claims_without_unit
            ),
        }
        if any(mapping_evidence.values()):
            issues.append(self._issue(
                "P0", "section_claim_mapping",
                "Format 的 section / claim mapping 不完整或越界",
                mapping_evidence, "format",
            ))

        protected = upstream.get("format_handoff", {}).get(
            "protected_caveats", []
        )
        preservation = artifact.get("caveat_preservation", [])
        preserved = {
            str(row.get("source_caveat"))
            for row in preservation
            if isinstance(row, dict)
            and row.get("status") in {"preserved", "reworded_equivalent"}
            and row.get("destination_unit_ids")
        }
        missing_caveats = sorted(set(map(str, protected)) - preserved)
        evidence_refs = self._collect_ref_values(
            upstream.get("section_manifest", []), {"evidence_refs"}
        )
        format_evidence_refs = self._collect_ref_values(
            {
                "delivery_units": artifact.get("delivery_units", []),
                "visual_assets": artifact.get("visual_assets", []),
            },
            {"source_evidence_refs"},
        )
        missing_evidence_refs = evidence_refs - format_evidence_refs

        known_omission_refs = (
            section_ids
            | claim_ids
            | evidence_refs
            | self._ids(upstream.get("source_registry"), "source_id")
        )
        unknown_omission_refs = omitted_refs - known_omission_refs
        retention = {
            "missing_evidence_refs": sorted(missing_evidence_refs),
            "unknown_evidence_refs": sorted(
                format_evidence_refs - evidence_refs
            ),
            "missing_caveats": missing_caveats,
            "forbidden_omissions": sorted(omitted_refs),
            "unknown_omission_refs": sorted(unknown_omission_refs),
        }
        if any(retention.values()):
            issues.append(self._issue(
                "P0", "content_retention",
                "Format 未完整保留数字、来源或 caveat",
                retention, "format",
            ))
        return self._result(
            "block" if any(row.get("severity") == "P0" for row in issues) else "pass",
            issues,
            f"report Markdown mapping and {target} content fidelity checked",
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
            "qa_preparation": "formatted_material",
            "speaker_script": "qa_pack",
        }.get(agent_id)
        canonical = data.get(alias) if alias else None
        if (
            agent_id == "speaker_script"
            and not isinstance(canonical, dict)
        ):
            canonical = data.get("formatted_material")
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
