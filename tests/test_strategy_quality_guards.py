from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from presentation_agent.agent_profiles import LEGACY_CONTRACT_PROFILE
from presentation_agent.connectors.registry import load_with_connector
from presentation_agent.context import ContextAssembler
from presentation_agent.io import read_json
from presentation_agent.machine_check import run_machine_checks
from presentation_agent.models import AgentSpec
from presentation_agent.review import ArtifactReviewer


ROOT = Path(__file__).resolve().parents[1]


def _spec(agent_id: str) -> AgentSpec:
    rows = read_json(ROOT / "configs" / "agents.json")["agents"]
    return AgentSpec.from_dict(next(row for row in rows if row["id"] == agent_id))


class StrategyQualityGuardTests(unittest.TestCase):
    def test_regression_contract_freezes_all_quality_dimensions(self) -> None:
        contract = read_json(
            ROOT / "evals" / "regression" / "strategy_quality_v1.json"
        )
        self.assertEqual(
            {case["id"] for case in contract["cases"]},
            {
                "REGR-E01",
                "REGR-E02",
                "REGR-A01",
                "REGR-A02",
                "REGR-R01",
                "REGR-R02",
                "REGR-D01",
                "REGR-C01",
            },
        )

    def test_connector_builds_stable_source_units(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "访谈.csv"
            path.write_text(
                "claim,evidence\n信任迁移,先用低风险任务测试\n复杂任务,连续修改37轮\n",
                encoding="utf-8",
            )
            loaded = load_with_connector(path, _spec("evidence_harvester"))

        units = loaded["source_units"]
        self.assertEqual(len(units), 2)
        self.assertTrue(all(unit["modality"] == "table" for unit in units))
        self.assertTrue(
            all(unit["source_unit_id"].startswith("SOURCE-") for unit in units)
        )
        self.assertEqual(loaded["source_unit_summary"]["unresolved"], 0)

    def test_argument_long_evidence_preview_blocks_readiness(self) -> None:
        assembler = ContextAssembler(
            ROOT, contract_profile=LEGACY_CONTRACT_PROFILE
        )
        large_evidence = [
            {"evidence_id": f"EV-{index}", "raw_content": "x" * 2500}
            for index in range(100)
        ]
        context = assembler.assemble(
            worker_id="argument_synthesis",
            report_charter={},
            manager_task={},
            raw_brief={"evidence_items": large_evidence},
            raw_brief_path=Path("/tmp/raw_brief.json"),
            artifacts=[],
        )
        self.assertEqual(context["input_readiness"]["status"], "blocked")
        self.assertEqual(
            context["input_readiness"]["blocking_issues"][0]["field"],
            "evidence_items",
        )

    def test_argument_roadmap_is_machine_blocked(self) -> None:
        rubrics = read_json(
            ROOT / "skills" / "argument_synthesis" / "rubrics.json"
        )["rubrics"]
        artifact = {
            "executive_summary": {
                "urgency_basis": None,
                "decision_request": {
                    "specificity_level": "execution_plan",
                    "recommended_direction": "2-4周完成评估并进入Q3路线图",
                },
                "decision_relevance": "支持管理层讨论",
            },
            "core_thesis": "建议形成路线图",
            "expected_action": "明确负责人和KPI",
            "key_arguments": [],
            "evidence_bank": [],
            "evidence_disposition": {},
        }
        objections = run_machine_checks(artifact, rubrics)
        ids = [objection.id for objection in objections]
        self.assertTrue(any(item.endswith("ARG-RECOMMENDATION-SCOPE") for item in ids))

    def test_historical_time_window_is_not_treated_as_roadmap(self) -> None:
        rubrics = read_json(
            ROOT / "skills" / "argument_synthesis" / "rubrics.json"
        )["rubrics"]
        artifact = {
            "executive_summary": {
                "urgency_basis": None,
                "decision_request": {
                    "specificity_level": "strategic_direction",
                    "recommended_direction": "聚焦高价值场景",
                },
                "decision_relevance": "支持管理层讨论",
            },
            "core_thesis": "过去3-6个月用户时长呈上升趋势",
            "expected_action": "确认分析方向",
            "key_arguments": [],
            "evidence_bank": [],
            "evidence_disposition": {},
        }
        objections = run_machine_checks(artifact, rubrics)
        self.assertFalse(
            any(item.id.endswith("ARG-RECOMMENDATION-SCOPE") for item in objections)
        )

    def test_disposition_must_cover_evidence_bank(self) -> None:
        rubrics = read_json(
            ROOT / "skills" / "argument_synthesis" / "rubrics.json"
        )["rubrics"]
        artifact = {
            "executive_summary": {
                "urgency_basis": None,
                "decision_request": {
                    "specificity_level": "strategic_direction",
                    "recommended_direction": "聚焦高价值场景",
                },
                "decision_relevance": "支持管理层讨论",
            },
            "core_thesis": "聚焦高价值场景",
            "expected_action": "确认方向",
            "key_arguments": [],
            "evidence_bank": [{"id": "E1"}],
            "evidence_disposition": {},
        }
        objections = run_machine_checks(artifact, rubrics)
        self.assertTrue(
            any(item.id.endswith("ARG-EVIDENCE-DISPOSITION") for item in objections)
        )

    def test_reviewer_snapshot_contains_evidence_index(self) -> None:
        snapshot = ArtifactReviewer._signal_snapshot(
            {
                "upstream_signal": {"topic": "测试"},
                "raw_brief": {
                    "source_units": [
                        {
                            "source_unit_id": "DOC1-P001",
                            "modality": "text",
                            "inspection_status": "inspected",
                        }
                    ],
                    "evidence_items": [
                        {
                            "evidence_id": "EV-001",
                            "type": "quote",
                            "source_unit_refs": ["DOC1-P001"],
                            "scope": "individual_case",
                        }
                    ],
                },
            }
        )
        self.assertEqual(snapshot["evidence_index"]["evidence_items"]["count"], 1)
        self.assertEqual(
            snapshot["evidence_index"]["source_units"]["items"][0][
                "source_unit_id"
            ],
            "DOC1-P001",
        )


if __name__ == "__main__":
    unittest.main()
