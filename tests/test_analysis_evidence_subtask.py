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
from presentation_agent.agent_profiles import load_agent_profile
from presentation_agent.connectors.registry import list_connectors, load_with_connector
from presentation_agent.connectors.table_profiler import profile_xlsx_sheets
from presentation_agent.io import read_json, write_json
from presentation_agent.launch import normalize_brief
from presentation_agent.manager import ManagerOrchestrator
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


class ManagerEvidenceIntakeTests(unittest.TestCase):
    def test_file_material_is_harvested_before_brief_and_reused_by_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "usage.csv"
            source.write_text(
                "date,app,hours\n2026-01-01,DS,12\n2026-01-02,DS,16\n",
                encoding="utf-8",
            )
            run_dir = temp / "run"
            run_dir.mkdir()
            brief = normalize_brief(
                {"topic": "DS 时长", "materials": [str(source)]}, ROOT, "v0_3"
            )
            brief_path = run_dir / "raw_brief.json"
            write_json(brief_path, brief)
            manager = ManagerOrchestrator(
                ROOT,
                run_dir,
                data_root=temp / "data",
                spawn_adapter="inline",
                contract_profile="v0_3",
            )

            intake = manager.initialize_run(brief_path)
            self.assertEqual(intake["actor"], "worker")
            self.assertTrue(intake["evidence_intake"])
            write_json(
                Path(intake["output_path"]),
                {
                    "items": [
                        {
                            "id": "EV-001",
                            "source_ref": "E1/usage/rows:1-2",
                            "content": "DS 时长从 12 增至 16。",
                        }
                    ],
                    "unresolved": [],
                },
            )
            intake_result = StepRunner(
                ROOT,
                run_dir / "evidence",
                data_root=temp / "data",
                contract_profile="v0_3",
            ).commit()
            self.assertEqual(intake_result["step"], "done")

            brief_gate = manager.record_worker_completed(intake_result)
            self.assertEqual(brief_gate["actor"], "human")
            self.assertEqual(brief_gate["gate"], "brief")
            self.assertEqual(brief_gate["evidence_options"][0]["value"], "EV-001")
            updated_brief = read_json(run_dir / "raw_brief.json")
            self.assertEqual(
                updated_brief["evidence_catalog"]["items"][0]["id"], "EV-001"
            )
            self.assertTrue(updated_brief["evidence_catalog"]["catalog_fingerprint"])
            self.assertEqual(
                updated_brief["source_manifest"][0]["content_hash"],
                updated_brief["evidence_catalog"]["source_manifest"][0]["content_hash"],
            )
            self.assertTrue(manager._evidence_catalog_reusable(updated_brief))
            source.write_text(
                "date,app,hours\n2026-01-01,DS,12\n2026-01-02,DS,18\n",
                encoding="utf-8",
            )
            self.assertFalse(manager._evidence_catalog_reusable(updated_brief))

            charter = read_json(FIXTURES / "report_charter.v2.valid.json")
            task = manager.workers.create_task(
                {
                    "task_id": "analysis-reuse",
                    "agent_id": "analysis",
                    "objective": "分析 DS 时长",
                    "input_artifacts": [str(run_dir / "raw_brief.json")],
                },
                charter,
                run_dir / "raw_brief.json",
                review_subagents_enabled=False,
            )
            StepRunner(
                ROOT,
                Path(task["task_dir"]),
                data_root=temp / "data",
                contract_profile="v0_3",
            ).prepare()
            analysis_state = read_json(Path(task["task_dir"]) / "run_state.json")
            self.assertEqual(analysis_state.get("evidence_spawn_count", 0), 0)
            self.assertEqual(
                analysis_state["evidence_decision"]["action"],
                "reuse_existing_catalog",
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
            {
                "raw_materials": [
                    {
                        "material_id": "M-1",
                        "text": "UNIQUE_RAW_MATERIAL_42",
                    }
                ]
            }
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
        instruction = Path(analysis["instruction_path"]).read_text(
            encoding="utf-8"
        )
        self.assertIn("UNIQUE_RAW_MATERIAL_42", instruction)
        self.assertIn("SU-1", instruction)

    def test_evidence_subtask_resolves_nested_relative_material_path(self) -> None:
        source_dir = self.tmp / "brief-source"
        source_dir.mkdir()
        (source_dir / "usage.csv").write_text(
            "claim,evidence\n频次提升,DS 从 5 次提升到 8 次\n单次提升,DS 从 1.7 分钟提升到 2.0 分钟\n",
            encoding="utf-8",
        )
        raw_brief_path = source_dir / "brief.json"
        raw_brief_path.write_text("{}", encoding="utf-8")

        runner, task_dir = self._runner(
            {
                "raw_materials": [
                    {
                        "material_id": "usage",
                        "path": "usage.csv",
                        "description": "DS 使用频次和单次时长摘要",
                    }
                ],
                "material_refs": [
                    {
                        "source_id": "raw_brief",
                        "artifact_path": str(raw_brief_path),
                    }
                ],
            }
        )

        first = runner.prepare()

        evidence_input = read_json(Path(first["input_path"]))
        self.assertTrue(evidence_input["material_resolution"]["complete"])
        material = evidence_input["raw_materials"][0]
        self.assertEqual(material["parse_status"], "parsed")
        self.assertEqual(material["source_type"], "csv")
        self.assertEqual(material["source_unit_summary"]["total"], 2)
        self.assertEqual(len(material["source_units"]), 2)
        self.assertTrue(Path(material["parsed_artifact_path"]).exists())
        self.assertEqual(evidence_input["evidence_index"][0]["id"], "E1")
        self.assertEqual(evidence_input["evidence_index"][0]["source_type"], "csv")
        self.assertTrue(evidence_input["evidence_index"][0]["data_assets"])

    def test_evidence_subtask_profiles_large_csv_without_inlining_all_rows(self) -> None:
        source_dir = self.tmp / "brief-source"
        source_dir.mkdir()
        rows = ["date,DS,豆包"]
        for day in range(1, 101):
            rows.append(f"2026-01-{((day - 1) % 30) + 1:02d},{day},{day / 2}")
        (source_dir / "usage.csv").write_text("\n".join(rows), encoding="utf-8")
        raw_brief_path = source_dir / "brief.json"
        raw_brief_path.write_text("{}", encoding="utf-8")

        runner, _ = self._runner(
            {
                "raw_materials": [
                    {
                        "material_id": "usage",
                        "path": "usage.csv",
                        "description": "DS 与豆包历史使用时长",
                    }
                ],
                "material_refs": [
                    {
                        "source_id": "raw_brief",
                        "artifact_path": str(raw_brief_path),
                    }
                ],
            }
        )

        first = runner.prepare()

        evidence_input = read_json(Path(first["input_path"]))
        material = evidence_input["raw_materials"][0]
        self.assertEqual(material["source_unit_summary"]["total"], 100)
        self.assertEqual(material["source_unit_summary"]["inlined"], 50)
        self.assertEqual(material["source_units_omitted"], 50)
        self.assertNotIn("tables", material)
        self.assertIn("data_profile", material)
        self.assertTrue(material["data_assets"][0]["chart_ready"])

        sidecar = read_json(Path(material["parsed_artifact_path"]))
        self.assertEqual(sidecar["tables"][0]["row_count"], 100)
        self.assertEqual(len(sidecar["source_units"]), 100)
        record = evidence_input["evidence_index"][0]
        self.assertEqual(record["id"], "E1")
        self.assertIn("chart_generation", record["downstream_use"])
        self.assertTrue(record["key_findings"])

    def test_committed_evidence_catalog_injects_chart_assets_for_analysis(self) -> None:
        source_dir = self.tmp / "brief-source"
        source_dir.mkdir()
        (source_dir / "usage.csv").write_text(
            "date,DS,豆包\n2026-01-01,8,9\n2026-01-02,12,10\n2026-01-03,16,11\n",
            encoding="utf-8",
        )
        raw_brief_path = source_dir / "brief.json"
        raw_brief_path.write_text("{}", encoding="utf-8")

        runner, task_dir = self._runner(
            {
                "raw_materials": [
                    {
                        "material_id": "usage",
                        "path": "usage.csv",
                        "description": "DS 与豆包历史使用时长",
                    }
                ],
                "material_refs": [
                    {
                        "source_id": "raw_brief",
                        "artifact_path": str(raw_brief_path),
                    }
                ],
            }
        )

        first = runner.prepare()
        write_json(
            Path(first["output_path"]),
            {
                "items": [
                    {
                        "id": "E-usage",
                        "source_ref": "E1",
                        "content": "DS 使用时长上升",
                    }
                ],
                "unresolved": [],
            },
        )

        runner.commit()

        injected = read_json(task_dir / "input.json")
        self.assertIn("evidence_index", injected)
        self.assertIn("evidence_assets", injected)
        asset = injected["evidence_assets"][0]
        self.assertTrue(asset["chart_ready"])
        self.assertEqual(asset["chart_data"]["chart_type"], "line")
        self.assertEqual(asset["chart_data"]["series"][0]["name"], "DS")
        self.assertEqual(asset["chart_data"]["series"][0]["values"][-1], 16.0)

    def test_doc_connector_is_registered_for_legacy_word_inputs(self) -> None:
        connectors = list_connectors()
        doc_connector = next(
            item for item in connectors if item["name"] == "doc_reader"
        )
        self.assertIn(".doc", doc_connector["suffixes"])

    def test_json_txt_and_markdown_connectors_are_registered_and_readable(self) -> None:
        connectors = {item["name"]: item for item in list_connectors()}
        self.assertEqual(connectors["json_reader"]["suffixes"], [".json"])
        self.assertEqual(connectors["text_reader"]["suffixes"], [".txt", ".md"])
        spec = load_agent_profile(ROOT, "v0_3").support_specs["evidence_harvester"]

        json_path = self.tmp / "usage.json"
        write_json(
            json_path,
            {
                "rows": [
                    {"date": "2026-01-01", "app": "DS", "hours": 12},
                    {"date": "2026-01-02", "app": "DS", "hours": 16},
                ]
            },
        )
        loaded_json = load_with_connector(json_path, spec)
        self.assertEqual(loaded_json["source_type"], "json")
        self.assertEqual(len(loaded_json["source_units"]), 2)
        self.assertEqual(loaded_json["data_profile"]["tables"][0]["row_count"], 2)

        txt_path = self.tmp / "notes.txt"
        txt_path.write_text("第一条访谈。\n\n第二条访谈。", encoding="utf-8")
        loaded_txt = load_with_connector(txt_path, spec)
        self.assertEqual(loaded_txt["source_type"], "txt")
        self.assertEqual(len(loaded_txt["source_units"]), 2)

        md_path = self.tmp / "brief.md"
        md_path.write_text("# 研究摘要\n\n关键发现。", encoding="utf-8")
        loaded_md = load_with_connector(md_path, spec)
        self.assertEqual(loaded_md["topic"], "研究摘要")
        self.assertEqual(len(loaded_md["source_units"]), 2)

    def test_table_profiler_detects_wide_time_series(self) -> None:
        profile = profile_xlsx_sheets(
            [
                {
                    "name": "usage",
                    "rows": [
                        ["App", "2026-01-01", "2026-01-02", "2026-01-03"],
                        ["DeepSeek", "8", "10", "16"],
                        ["豆包", "9", "9.5", "10"],
                    ],
                }
            ]
        )

        candidate = profile["tables"][0]["time_series_candidates"][0]
        self.assertEqual(candidate["orientation"], "wide")
        self.assertEqual(candidate["series_label_column"], "App")
        self.assertIn("DeepSeek", profile["key_findings"][0])
        self.assertIn("16", profile["key_findings"][0])

    def test_evidence_schema_drift_is_advisory_when_catalog_is_consumable(self) -> None:
        runner, task_dir = self._runner(
            {
                "raw_materials": [
                    {"material_id": "M-1", "text": "source text"}
                ]
            }
        )
        first = runner.prepare()
        write_json(
            Path(first["output_path"]),
            {
                "schema": "evidence_catalog.v1",
                "source_units": [
                    {
                        "source_unit_id": "SU-1",
                        "file": "source.xlsx",
                        "description": "usage metric",
                    }
                ],
                "evidence_items": [
                    {
                        "evidence_id": "E-1",
                        "type": "quantitative_metric",
                        "description": "DAU increased",
                    }
                ],
                "source_unit_disposition": [],
                "coverage_summary": {"total_source_units": 1},
            },
        )

        analysis = runner.commit()

        self.assertEqual(analysis["step"], "gen")
        catalog = read_json(
            task_dir
            / "subtasks"
            / "evidence_harvester"
            / "evidence_catalog.json"
        )
        self.assertEqual(catalog["agent_id"], "evidence_harvester")
        self.assertEqual(catalog["unresolved"], [])
        self.assertTrue(catalog["schema_warnings"])
        review = read_json(
            task_dir / "subtasks" / "evidence_harvester" / "review.json"
        )
        self.assertEqual(review["mode"], "advisory")
        self.assertTrue(review["schema_warnings"])

    def test_evidence_minimum_gate_still_blocks_non_array_payloads(self) -> None:
        runner, _ = self._runner(
            {"raw_materials": [{"material_id": "M-1"}]}
        )
        first = runner.prepare()
        write_json(
            Path(first["output_path"]),
            {
                "items": {},
            },
        )

        with self.assertRaisesRegex(Exception, "最小可消费门禁"):
            runner.commit()

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
        self.assertEqual(
            review["reviewer"],
            "schema_gate_only+schema_advisory",
        )
        self.assertEqual(review["objections"], [])

    def test_worker_schema_errors_are_advisory_in_loop_first_mode(self) -> None:
        runner, task_dir = self._runner({"analysis_objective": "test"})
        runner.max_revision_rounds = 0
        generation = runner.prepare()
        artifact = json.loads(
            (FIXTURES / "analysis.v1.valid.json").read_text(encoding="utf-8")
        )
        artifact.pop("findings")
        write_json(Path(generation["output_path"]), artifact)
        review = runner.commit()
        write_json(Path(review["output_path"]), {"objections": []})

        done = runner.commit()

        state = read_json(task_dir / "run_state.json")
        self.assertEqual(done["status"], "pending_human_review")
        self.assertEqual(state["next_action"], "await_human_decision")
        self.assertFalse(state["p0_open"])
        self.assertTrue(state["p1_open"])

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
