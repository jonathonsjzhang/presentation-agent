from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from presentation_agent.connectors.registry import load_with_connector
from presentation_agent.io import read_json
from presentation_agent.models import AgentSpec


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

if __name__ == "__main__":
    unittest.main()
