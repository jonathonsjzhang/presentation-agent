from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from presentation_agent.analysis import (
    EvidenceAction,
    decide_evidence,
)
from presentation_agent.io import read_json, write_json
from presentation_agent.spawn import SpawnRequest
from presentation_agent.step import StepRunner


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v0_3"


class AnalysisEvidenceDecisionTests(unittest.TestCase):
    def test_existing_catalog_is_reused_even_when_raw_materials_exist(self) -> None:
        decision = decide_evidence(
            evidence_catalog={
                "schema": "evidence_catalog.v1",
                "evidence_items": [],
            },
            raw_materials=[{"material_id": "M-01"}],
            evidence_catalog_ref="artifacts/evidence_catalog.json",
        )

        self.assertEqual(
            decision.action,
            EvidenceAction.REUSE_EXISTING_CATALOG,
        )
        self.assertFalse(decision.should_invoke)
        self.assertFalse(decision.invoked)
        self.assertEqual(decision.invocation_reason, "reused_existing_catalog")
        self.assertEqual(
            decision.evidence_catalog_ref,
            "artifacts/evidence_catalog.json",
        )
        self.assertIsNone(decision.evidence_gap)

    def test_v03_raw_material_fixture_marks_exactly_one_invocation(self) -> None:
        fixture = json.loads(
            (
                FIXTURES
                / "golden_cases"
                / "mixed_deep_dive"
                / "input.json"
            ).read_text(encoding="utf-8")
        )

        decision = decide_evidence(
            evidence_catalog=None,
            raw_materials=fixture["materials"],
        )

        self.assertEqual(decision.action, EvidenceAction.INVOKE_ONCE)
        self.assertTrue(decision.should_invoke)
        self.assertTrue(decision.invoked)
        self.assertEqual(
            decision.invocation_reason,
            "raw_materials_without_catalog",
        )
        self.assertEqual(decision.max_invocations_this_round, 1)
        self.assertIsNone(decision.evidence_gap)

    def test_no_material_records_blocking_evidence_gap_without_invocation(self) -> None:
        decision = decide_evidence(
            evidence_catalog=None,
            raw_materials=[],
        )

        self.assertEqual(decision.action, EvidenceAction.RECORD_EVIDENCE_GAP)
        self.assertFalse(decision.should_invoke)
        self.assertFalse(decision.invoked)
        self.assertEqual(decision.invocation_reason, "no_raw_materials")
        self.assertIn("blocked", decision.evidence_gap or "")
        self.assertEqual(decision.max_invocations_this_round, 1)

    def test_none_raw_materials_follows_the_same_gap_path(self) -> None:
        decision = decide_evidence(
            evidence_catalog=None,
            raw_materials=None,
        )
        self.assertEqual(decision.action, EvidenceAction.RECORD_EVIDENCE_GAP)

    def test_inputs_are_not_mutated(self) -> None:
        catalog = {"schema": "evidence_catalog.v1"}
        materials = [{"material_id": "M-01"}]
        decide_evidence(
            evidence_catalog=catalog,
            raw_materials=materials,
        )
        self.assertEqual(catalog, {"schema": "evidence_catalog.v1"})
        self.assertEqual(materials, [{"material_id": "M-01"}])

    def test_invalid_input_types_fail_closed(self) -> None:
        with self.assertRaises(TypeError):
            decide_evidence(
                evidence_catalog=[],
                raw_materials=None,
            )
        with self.assertRaises(TypeError):
            decide_evidence(
                evidence_catalog=None,
                raw_materials="not-a-material-list",
            )


class AnalysisEvidenceRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.data_root = self.tmp / "data"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _catalog(*, unresolved: bool = False) -> dict:
        return {
            "agent_id": "evidence_harvester",
            "schema": "evidence_catalog.v1",
            "source_units": [],
            "evidence_items": [],
            "source_unit_disposition": {},
            "unresolved_units": (
                [{"source_unit_id": "SU-1", "reason": "unreadable"}]
                if unresolved
                else []
            ),
            "coverage_summary": {
                "total_source_units": 0,
                "captured_units": 0,
                "excluded_units": 0,
                "unresolved_units": 1 if unresolved else 0,
                "complete": not unresolved,
            },
        }

    def _runner(
        self,
        input_data: dict,
        *,
        review_subagents_enabled: bool = True,
    ) -> tuple[StepRunner, Path]:
        task_dir = self.tmp / f"task-{len(list(self.tmp.glob('task-*')))}"
        task_dir.mkdir()
        input_path = task_dir / "input.json"
        write_json(input_path, input_data)
        write_json(
            task_dir / "run_state.json",
            {
                "run_id": task_dir.name,
                "contract_profile": "v0_3",
                "agent_id": "analysis",
                "agent_name": "分析",
                "stage": 1,
                "status": "init",
                "current_step": "init",
                "round_index": 0,
                "input_path": str(input_path),
                "output_dir": str(task_dir),
                "p0_open": [],
                "p1_open": [],
                "produced_artifacts": [],
                "history": [],
                "review_subagents_enabled": review_subagents_enabled,
            },
        )
        return (
            StepRunner(
                ROOT,
                task_dir,
                data_root=self.data_root,
                contract_profile="v0_3",
            ),
            task_dir,
        )

    def test_existing_catalog_goes_directly_to_analysis(self) -> None:
        runner, task_dir = self._runner(
            {
                "evidence_catalog": self._catalog(),
                "raw_materials": [{"material_id": "M-1"}],
            }
        )
        prepared = runner.prepare()
        self.assertEqual(prepared["step"], "gen")
        state = read_json(task_dir / "run_state.json")
        self.assertEqual(state.get("evidence_spawn_count", 0), 0)
        self.assertEqual(
            state["evidence_decision"]["action"], "reuse_existing_catalog"
        )

    def test_no_material_records_gap_without_subtask(self) -> None:
        runner, task_dir = self._runner({"analysis_objective": "test"})
        prepared = runner.prepare()
        self.assertEqual(prepared["step"], "gen")
        state = read_json(task_dir / "run_state.json")
        self.assertEqual(
            state["evidence_decision"]["action"], "record_evidence_gap"
        )
        self.assertFalse((task_dir / "subtasks").exists())

    def test_raw_materials_spawn_once_resume_and_inject_catalog(self) -> None:
        runner, task_dir = self._runner(
            {"raw_materials": [{"material_id": "M-1", "text": "source"}]}
        )
        first = runner.prepare()
        self.assertEqual(first["step"], "evidence")
        self.assertEqual(first["agent_id"], "evidence_harvester")
        self.assertIn("subtasks/evidence_harvester", first["subtask_dir"])
        normalized = SpawnRequest(
            task_dir=task_dir,
            agent_id="analysis",
            role="worker",
            instruction_path=Path(first["instruction_path"]),
            output_path=Path(first["output_path"]),
            input_path=task_dir / "input.json",
        )
        self.assertEqual(normalized.agent_id, "evidence_harvester")
        self.assertEqual(normalized.task_dir, Path(first["subtask_dir"]))

        resumed = StepRunner(
            ROOT,
            task_dir,
            data_root=self.data_root,
            contract_profile="v0_3",
        )
        with self.assertRaisesRegex(Exception, "请先 commit"):
            resumed.prepare()
        self.assertEqual(
            read_json(task_dir / "run_state.json")["evidence_spawn_count"], 1
        )

        write_json(Path(first["output_path"]), self._catalog(unresolved=True))
        analysis = resumed.commit()
        self.assertEqual(analysis["step"], "gen")
        state = read_json(task_dir / "run_state.json")
        self.assertEqual(state["evidence_spawn_count"], 1)
        injected = read_json(task_dir / "input.json")
        self.assertEqual(injected["evidence_catalog"]["schema"], "evidence_catalog.v1")
        self.assertTrue(Path(state["evidence_catalog_ref"]).exists())
        self.assertTrue(
            (task_dir / "subtasks" / "evidence_harvester" / "review.json").exists()
        )

    def test_blocking_unresolved_evidence_returns_analysis_blocked(self) -> None:
        runner, _ = self._runner({"analysis_objective": "test"})
        generation = runner.prepare()
        artifact = json.loads(
            (FIXTURES / "analysis.v1.valid.json").read_text(encoding="utf-8")
        )
        artifact["material_readiness"]["status"] = "blocked"
        artifact["evidence_execution"]["blocking_impact"] = "blocking"
        write_json(Path(generation["output_path"]), artifact)
        review = runner.commit()
        write_json(Path(review["output_path"]), {"objections": []})
        done = runner.commit()
        self.assertEqual(done["status"], "blocked")

    def test_schema_only_mode_skips_reviewer_subagent_but_keeps_gate(self) -> None:
        runner, task_dir = self._runner(
            {"analysis_objective": "test"},
            review_subagents_enabled=False,
        )
        generation = runner.prepare()
        artifact = json.loads(
            (FIXTURES / "analysis.v1.valid.json").read_text(encoding="utf-8")
        )
        write_json(Path(generation["output_path"]), artifact)

        done = runner.commit()

        self.assertEqual(done["step"], "done")
        self.assertEqual(done["review_mode"], "schema_only")
        self.assertFalse(
            (task_dir / "handoff" / "instruction_review.md").exists()
        )
        review = read_json(task_dir / "review_round_0.json")
        self.assertEqual(review["reviewer"], "schema_gate_only")
        self.assertEqual(review["objections"], [])

    def test_default_mode_still_prepares_independent_reviewer(self) -> None:
        runner, _ = self._runner({"analysis_objective": "test"})
        generation = runner.prepare()
        artifact = json.loads(
            (FIXTURES / "analysis.v1.valid.json").read_text(encoding="utf-8")
        )
        write_json(Path(generation["output_path"]), artifact)

        review = runner.commit()

        self.assertEqual(review["step"], "review")
        self.assertTrue(Path(review["instruction_path"]).exists())

    def test_revise_is_followed_by_a_fresh_independent_review(self) -> None:
        runner, _ = self._runner({"analysis_objective": "test"})
        generation = runner.prepare()
        artifact = json.loads(
            (FIXTURES / "analysis.v1.valid.json").read_text(encoding="utf-8")
        )
        write_json(Path(generation["output_path"]), artifact)
        review = runner.commit()
        write_json(
            Path(review["output_path"]),
            {
                "objections": [
                    {
                        "severity": "P0",
                        "rubric_id": "test-revise",
                        "dimension": "logic",
                        "message": "需要返工验证",
                        "evidence": "unit test",
                        "suggestion": "修正后重新审查",
                    }
                ]
            },
        )

        revise = runner.commit()
        self.assertEqual(revise["step"], "revise")
        write_json(Path(revise["output_path"]), artifact)

        second_review = runner.commit()
        self.assertEqual(second_review["step"], "review")
        self.assertEqual(second_review["round_index"], 1)
        self.assertTrue(Path(second_review["instruction_path"]).exists())


if __name__ == "__main__":
    unittest.main()
