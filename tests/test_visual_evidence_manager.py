from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from presentation_agent.manager import ManagerAgentRuntime


ROOT = Path(__file__).resolve().parents[1]


class VisualEvidenceManagerRoutingTests(unittest.TestCase):
    def test_missing_evidence_data_returns_to_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            analysis_packet = {
                "task_id": "analysis-001",
                "agent_id": "analysis",
                "objective": "分析用户时长变化",
                "input_artifacts": ["raw-brief.json"],
                "acceptance_criteria": ["结论有证据"],
            }
            state = {
                "current_task": {
                    "task_id": "format-001",
                    "agent_id": "format",
                    "packet": {
                        "task_id": "format-001",
                        "agent_id": "format",
                        "objective": "生成文档",
                        "input_artifacts": ["report.json"],
                        "acceptance_criteria": ["文件可读"],
                    },
                },
                "tasks": [
                    {"agent_id": "analysis", "packet": analysis_packet},
                ],
                "worker_result": {
                    "artifact": {
                        "upstream_revision_requests": [
                            {
                                "target_agent": "evidence_harvester",
                                "blocking_level": "blocking",
                                "reason": "缺少完整历史时序数据",
                            }
                        ]
                    }
                },
            }
            (run_dir / "manager_state.json").write_text(
                json.dumps(state, ensure_ascii=False), encoding="utf-8"
            )
            runtime = ManagerAgentRuntime(
                ROOT,
                run_dir,
                run_dir / "data",
                contract_profile="v0_3",
            )
            runtime.output_path("acceptance").write_text(
                json.dumps(
                    {
                        "action": "revise",
                        "acceptance_report": {
                            "verdict": "revise",
                            "reason": "补齐可视化论据",
                            "revision_requirements": ["补齐完整历史数据"],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            decision = runtime.read_decision("acceptance")

            self.assertEqual(decision["task_packet"]["agent_id"], "analysis")
            self.assertEqual(
                decision["task_packet"]["input_artifacts"], ["raw-brief.json"]
            )
            self.assertIn(
                "缺少完整历史时序数据",
                decision["task_packet"]["revision_feedback"],
            )


if __name__ == "__main__":
    unittest.main()
