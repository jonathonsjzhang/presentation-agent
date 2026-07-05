from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from presentation_agent.agent_profiles import LEGACY_CONTRACT_PROFILE
from presentation_agent.io import read_json
from presentation_agent.llm.adapters.mock import synthesize_from_schema
from presentation_agent.step import PipelineStepper, StepError, StepRunner

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_EXAMPLES = ROOT / "tests" / "fixtures" / "runtime_examples"


# Minimal artifact for step runner testing (argument_synthesis stage)
def _arg_artifact() -> dict:
    root = Path(__file__).resolve().parent.parent
    schema = read_json(
        root
        / "skills"
        / "argument_synthesis"
        / "schemas"
        / "argument_synthesis.v1.json"
    )
    artifact = synthesize_from_schema(schema)
    artifact["topic"] = "测试评估"
    artifact["core_question"] = "是否应该聚焦高价值场景？"
    artifact["core_thesis"] = "现有证据支持优先讨论高价值场景"
    artifact["expected_action"] = "确认战略讨论方向"
    artifact["key_arguments"][0]["id"] = "KA-01"
    artifact["key_arguments"][0]["evidence_refs"] = ["E1"]
    artifact["key_arguments"][0]["logic_chain"]["observations"] = ["E1"]
    artifact["evidence_bank"][0]["id"] = "E1"
    artifact["evidence_bank"][0]["source_unit_refs"] = ["SRC-1"]
    artifact["evidence_disposition"] = {
        "E1": {
            "status": "selected",
            "role": "direct_support",
            "claim_refs": ["KA-01"],
            "reason": "支撑核心判断",
        }
    }
    artifact["executive_summary"]["urgency_basis"] = None
    artifact["executive_summary"]["supporting_arguments"][0]["id"] = "KA-01"
    artifact["executive_summary"]["supporting_arguments"][0][
        "evidence_refs"
    ] = ["E1"]
    artifact["executive_summary"]["decision_request"][
        "rationale_claim_refs"
    ] = ["KA-01"]
    return artifact


class TestStepRunner(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = Path(__file__).resolve().parent.parent
        global_state_dir = self.root / "data" / "global"
        global_state_dir.mkdir(parents=True, exist_ok=True)
        self.global_state_bak = None
        gs_path = global_state_dir / "state.json"
        if gs_path.exists():
            self.global_state_bak = gs_path.read_text(encoding="utf-8")
        gs_path.write_text("{}", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self.global_state_bak is not None:
            gs_path = self.root / "data" / "global" / "state.json"
            gs_path.write_text(self.global_state_bak, encoding="utf-8")

    def _init_stage_dir(self, agent_id="argument_synthesis") -> Path:
        stage_dir = self.tmp / f"stage_1_{agent_id}"
        stage_dir.mkdir(parents=True, exist_ok=True)
        (stage_dir / "handoff").mkdir(parents=True, exist_ok=True)
        import json as _json
        from presentation_agent.models import now_iso
        run_state = {
            "run_id": f"{agent_id}-test",
            "agent_id": agent_id,
            "agent_name": "测试agent",
            "stage": 1,
            "status": "init",
            "current_step": "init",
            "round_index": 0,
            "max_revision_rounds": 2,
            "contract_profile": LEGACY_CONTRACT_PROFILE,
            "input_path": str(RUNTIME_EXAMPLES / "raw_brief.json"),
            "output_dir": str(stage_dir),
            "p0_open": [],
            "p1_open": [],
            "produced_artifacts": [],
            "history": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        (stage_dir / "run_state.json").write_text(
            _json.dumps(run_state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return stage_dir

    # ---- status -------------------------------------------------------------

    def test_status_init(self):
        stage_dir = self._init_stage_dir()
        runner = StepRunner(self.root, stage_dir)
        s = runner.status()
        self.assertEqual(s["current_step"], "init")
        self.assertEqual(s["agent_id"], "argument_synthesis")

    def test_pre_profile_legacy_stage_is_inferred_on_resume(self):
        stage_dir = self._init_stage_dir()
        run_state_path = stage_dir / "run_state.json"
        run_state = json.loads(run_state_path.read_text(encoding="utf-8"))
        run_state.pop("contract_profile")
        run_state_path.write_text(
            json.dumps(run_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        runner = StepRunner(self.root, stage_dir)

        self.assertEqual(
            runner.contract_profile,
            LEGACY_CONTRACT_PROFILE,
        )

    # ---- prepare ------------------------------------------------------------

    def test_prepare_gen(self):
        stage_dir = self._init_stage_dir()
        runner = StepRunner(self.root, stage_dir)
        r = runner.prepare()
        self.assertEqual(r["step"], "gen")
        self.assertTrue((stage_dir / "handoff" / "instruction_gen.md").exists())

    def test_storyline_prepare_persists_compiled_skill_bundle(self):
        stage_dir = self._init_stage_dir("storyline_design")
        runner = StepRunner(self.root, stage_dir)
        runner.prepare()

        compiled_path = stage_dir / "compiled_skill_package.json"
        self.assertTrue(compiled_path.exists())
        compiled = json.loads(compiled_path.read_text(encoding="utf-8"))
        self.assertEqual(
            compiled["selected_capabilities"],
            [
                "core.storyline_design",
                "audience.exec_office",
                "report.deep_dive",
                "format.ppt",
            ],
        )
        first_fingerprint = compiled["fingerprint"]
        run_state = json.loads((stage_dir / "run_state.json").read_text(encoding="utf-8"))
        self.assertIn("generation_round_0", run_state["prompt_budget"])
        self.assertGreater(
            run_state["prompt_budget"]["generation_round_0"]["total_tokens_estimate"],
            0,
        )

        resumed = StepRunner(self.root, stage_dir)
        resumed_compiled = json.loads(compiled_path.read_text(encoding="utf-8"))
        self.assertEqual(resumed.skill_package.fingerprint, first_fingerprint)
        self.assertEqual(resumed_compiled["fingerprint"], first_fingerprint)

    def test_prepare_twice_errors(self):
        stage_dir = self._init_stage_dir()
        runner = StepRunner(self.root, stage_dir)
        runner.prepare()
        with self.assertRaises(StepError):
            runner.prepare()

    def test_prepare_after_done_errors(self):
        stage_dir = self._init_stage_dir()
        runner = StepRunner(self.root, stage_dir)
        runner.prepare()  # gen
        self._write_output(stage_dir, "output_gen.json", _arg_artifact())
        runner.commit()  # gen commit -> review
        self._write_output(stage_dir, "output_review.json", {"objections": []})
        r = runner.commit()  # review commit -> done
        self.assertEqual(r["step"], "done")
        with self.assertRaises(StepError):
            runner.prepare()

    # ---- commit: gen --------------------------------------------------------

    def test_gen_review_done_flow(self):
        stage_dir = self._init_stage_dir()
        runner = StepRunner(self.root, stage_dir)
        runner.prepare()
        self._write_output(stage_dir, "output_gen.json", _arg_artifact())
        r = runner.commit()
        self.assertEqual(r["step"], "review")
        self._write_output(stage_dir, "output_review.json", {"objections": []})
        r = runner.commit()
        self.assertEqual(r["step"], "done")
        self.assertEqual(r["status"], "pending_human_review")
        self.assertTrue((stage_dir / "artifact.json").exists())

    def test_commit_before_prepare_errors(self):
        stage_dir = self._init_stage_dir()
        runner = StepRunner(self.root, stage_dir)
        with self.assertRaises(StepError):
            runner.commit()

    def test_commit_missing_output_errors(self):
        stage_dir = self._init_stage_dir()
        runner = StepRunner(self.root, stage_dir)
        runner.prepare()
        with self.assertRaises(StepError):
            runner.commit()

    def test_commit_bad_json_errors(self):
        stage_dir = self._init_stage_dir()
        runner = StepRunner(self.root, stage_dir)
        runner.prepare()
        (stage_dir / "handoff" / "output_gen.json").write_text("not json", encoding="utf-8")
        with self.assertRaises(StepError):
            runner.commit()

    # ---- revise loop --------------------------------------------------------

    def test_p0_triggers_revise(self):
        stage_dir = self._init_stage_dir()
        runner = StepRunner(self.root, stage_dir)
        runner.prepare()
        self._write_output(stage_dir, "output_gen.json", _arg_artifact())
        runner.commit()  # gen -> review
        # host reports a P0
        self._write_output(stage_dir, "output_review.json", {
            "objections": [
                {"rubric_id": "X", "severity": "P0", "dimension": "逻辑", "message": "遗漏关键维度", "suggestion": "补充"}
            ]
        })
        r = runner.commit()  # review -> revise (auto-prepare)
        self.assertEqual(r["step"], "revise")
        self.assertTrue((stage_dir / "handoff" / "instruction_revise.md").exists())
        # host writes revised artifact, commit again
        self._write_output(stage_dir, "output_revise.json", _arg_artifact())
        r = runner.commit()  # revise -> review
        self.assertEqual(r["step"], "review")

    # ---- schema gate --------------------------------------------------------

    def test_schema_gate_catches_missing_fields(self):
        """Even if host says no objections, schema gate adds P0s."""
        stage_dir = self._init_stage_dir()
        runner = StepRunner(self.root, stage_dir)
        runner.prepare()
        bad = {"schema": "argument_synthesis.v1", "agent_id": "argument_synthesis"}
        self._write_output(stage_dir, "output_gen.json", bad)
        runner.commit()
        # commit auto-prepares review; host says clean
        self._write_output(stage_dir, "output_review.json", {"objections": []})
        r = runner.commit()
        # schema gate should have added P0s -> revise, not done
        self.assertNotEqual(r["step"], "done")

    # ---- abort --------------------------------------------------------------

    def test_abort(self):
        stage_dir = self._init_stage_dir()
        runner = StepRunner(self.root, stage_dir)
        runner.prepare()
        r = runner.abort()
        self.assertEqual(r["status"], "aborted")
        s = runner.status()
        self.assertEqual(s["current_step"], "done")

    # ---- helpers ------------------------------------------------------------

    @staticmethod
    def _write_output(stage_dir: Path, filename: str, data: dict) -> None:
        path = stage_dir / "handoff" / filename
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class TestPipelineStepper(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = Path(__file__).resolve().parent.parent

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_and_advance_full_chain(self):
        import shutil

        brief_path = RUNTIME_EXAMPLES / "raw_brief.json"
        shutil.copy2(str(brief_path), str(self.tmp / "raw_brief.json"))
        stepper = PipelineStepper(
            self.root,
            self.tmp,
            contract_profile=LEGACY_CONTRACT_PROFILE,
        )
        stage1 = stepper.init_pipeline(self.tmp / "raw_brief.json")
        self.assertEqual(stage1["agent_id"], "argument_synthesis")
        resumed = PipelineStepper(self.root, self.tmp)
        self.assertEqual(
            resumed.contract_profile,
            LEGACY_CONTRACT_PROFILE,
        )

        # Now simulate stage 1 done by creating its artifact.json
        sd1 = Path(stage1["stage_dir"])
        import json as _json
        sd1.mkdir(parents=True, exist_ok=True)
        artifact = {"schema": "argument_synthesis.v1", "agent_id": "argument_synthesis"}
        (sd1 / "artifact.json").write_text(
            _json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        stage2 = stepper.advance_stage()
        self.assertEqual(stage2["agent_id"], "storyline_design")
        # Verify stage 2's run_state points at stage 1's artifact
        rs2 = (Path(stage2["stage_dir"]) / "run_state.json").read_text(encoding="utf-8")
        self.assertIn("artifact.json", rs2)

        # Simulate stage 2 done, advance through all 6 workers
        sd2 = Path(stage2["stage_dir"])
        sd2.mkdir(parents=True, exist_ok=True)
        (sd2 / "artifact.json").write_text("{}", encoding="utf-8")

        for _ in range(3, 7):
            s = stepper.advance_stage()
            self.assertIsNotNone(s["agent_id"])
            sd = Path(s["stage_dir"])
            sd.mkdir(parents=True, exist_ok=True)
            (sd / "artifact.json").write_text("{}", encoding="utf-8")

        ps = stepper.pipeline_status()
        self.assertEqual(len(ps["stages"]), 6)

    def test_advance_without_artifact_errors(self):
        import shutil

        brief_path = RUNTIME_EXAMPLES / "raw_brief.json"
        shutil.copy2(str(brief_path), str(self.tmp / "raw_brief.json"))
        stepper = PipelineStepper(
            self.root,
            self.tmp,
            contract_profile=LEGACY_CONTRACT_PROFILE,
        )
        stepper.init_pipeline(self.tmp / "raw_brief.json")
        with self.assertRaises(StepError):
            stepper.advance_stage()

    def test_pipeline_status(self):
        import shutil

        brief_path = RUNTIME_EXAMPLES / "raw_brief.json"
        shutil.copy2(str(brief_path), str(self.tmp / "raw_brief.json"))
        stepper = PipelineStepper(
            self.root,
            self.tmp,
            contract_profile=LEGACY_CONTRACT_PROFILE,
        )
        stepper.init_pipeline(self.tmp / "raw_brief.json")
        ps = stepper.pipeline_status()
        self.assertEqual(ps["current_stage"], 1)
        self.assertEqual(len(ps["stages"]), 6)
        self.assertEqual(ps["stages"][0]["status"], "init")


if __name__ == "__main__":
    unittest.main()
