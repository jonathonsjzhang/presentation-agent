from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from presentation_agent.agent_profiles import load_agent_profile
from presentation_agent.cli import build_parser
from presentation_agent.failures import classify_failure
from presentation_agent.io import read_json
from presentation_agent.llm.schema import validate
from presentation_agent.launch import normalize_brief
from presentation_agent.manager import ManagerOrchestrator
from presentation_agent.material_resolver import resolve_raw_materials
from presentation_agent.step import StepError, StepRunner


ROOT = Path(__file__).resolve().parents[1]


class V04SimplifiedFlowTests(unittest.TestCase):
    def test_confirmed_brief_dispatches_analysis_without_manager_planning_turn(self) -> None:
        brief = normalize_brief(
            {"topic": "AI 产品复访", "user_intent": "解释复访变化"},
            ROOT,
            "v0_4",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            brief_path = run_dir / "raw_brief.json"
            brief_path.write_text(
                json.dumps(brief, ensure_ascii=False), encoding="utf-8"
            )
            manager = ManagerOrchestrator(ROOT, run_dir, contract_profile="v0_4")
            manager.initialize_run(brief_path)
            manager.record_human_feedback(
                json.dumps(
                    {
                        "research_purpose": "解释复访变化",
                        "research_direction": "判断结构变化是否为主因",
                        "high_confidence_evidence": [],
                        "brief_confirmed": True,
                    },
                    ensure_ascii=False,
                )
            )
            result = manager.approve()
            self.assertEqual(result["actor"], "worker")
            self.assertEqual(result["task"]["agent_id"], "analysis")
            self.assertTrue((run_dir / "report_charter.json").is_file())

    def test_v04_is_markdown_first_without_removing_worker_methods(self) -> None:
        profile = load_agent_profile(ROOT)
        self.assertEqual(profile.contract_profile, "v0_4")
        for agent_id in ("analysis", "storyline", "report", "qa_preparation"):
            self.assertEqual(
                profile.specs[agent_id].output_contract["artifact_format"],
                "markdown",
            )
        analysis_skill = (ROOT / "skills/analysis/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("证据综合与候选论点设计者", analysis_skill)
        self.assertIn("候选论点金字塔", analysis_skill)
        self.assertIn("共享 findings pool", analysis_skill)
        self.assertIn("不是最终报告的不同章节", analysis_skill)
        self.assertIn("## 提交前检查", analysis_skill)
        self.assertIn("Finding 完整性", analysis_skill)
        self.assertIn("证据与判断强度", analysis_skill)
        self.assertIn("候选论点完整性", analysis_skill)
        self.assertIn("## Workflow", analysis_skill)
        self.assertIn("analysis.md", analysis_skill)
        storyline_skill = (ROOT / "skills/storyline/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## 提交前检查", storyline_skill)
        self.assertIn("可独立读懂", storyline_skill)
        self.assertIn("可独立理解的微型论证", storyline_skill)
        self.assertIn("用户选择不构成新增证据", storyline_skill)
        self.assertIn("必要前提", storyline_skill)
        self.assertIn("完整复述 `core_answer`", storyline_skill)
        self.assertIn("内容完整性在本阶段定稿", storyline_skill)
        self.assertIn("Report 无需重组、补写或恢复核心答案", storyline_skill)
        self.assertNotIn("250–350", storyline_skill)
        report_skill = (ROOT / "skills/report/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## 提交前检查", report_skill)
        self.assertIn("Storyline 已定稿", report_skill)
        self.assertIn("Executive Summary 保真", report_skill)
        self.assertIn("Report 阶段不重新设定摘要字数", report_skill)
        self.assertIn("不得把它重新编辑成标签式 Takeaway bullets", report_skill)
        self.assertNotIn("250–350", report_skill)
        format_skill = (ROOT / "skills/format/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## 提交前检查", format_skill)
        self.assertIn("视觉必要性", format_skill)
        self.assertIn("原语与数据形状", format_skill)
        self.assertIn("after_heading", format_skill)
        self.assertIn("Format 不承担语义修复", format_skill)

    def test_step_runner_commits_canonical_markdown_and_tiny_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            input_path = run_dir / "input.json"
            input_path.write_text(
                json.dumps(
                    {
                        "contract_profile": "v0_4",
                        "brief": {"topic": "测试主题"},
                        "raw_brief": {"topic": "测试主题"},
                        "report_charter": {"topic": "测试主题"},
                        "manager_task": {"agent_id": "analysis", "objective": "完成分析"},
                        "input_readiness": {"status": "ready"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (run_dir / "run_state.json").write_text(
                json.dumps(
                    {
                        "run_id": "v04-analysis",
                        "task_id": "analysis-1",
                        "agent_id": "analysis",
                        "agent_name": "分析",
                        "stage": 1,
                        "status": "running",
                        "current_step": "init",
                        "round_index": 0,
                        "input_path": str(input_path),
                        "produced_artifacts": [],
                        "history": [],
                        "p0_open": [],
                        "p1_open": [],
                        "contract_profile": "v0_4",
                        "review_subagents_enabled": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            runner = StepRunner(ROOT, run_dir, contract_profile="v0_4")
            prepared = runner.prepare()
            self.assertTrue(prepared["output_path"].endswith(".md"))
            markdown = """# Analysis

## 核心发现

核心判断来自完整材料比较，并保留证据边界。这里补充足够的分析文字，使内容可以独立阅读，也能让下一阶段理解观点与依据之间的关系。

## 竞争性解释与边界

替代解释仍然存在，当前只把判断写到证据能够支持的强度。

## 候选论点组

### 方案 A：聚焦结构变化

主论点与两个分论点共同回答研究问题，并说明适用场景和取舍。

### 方案 B：聚焦能力约束

另一组完整主张保留不同的决策张力。

## 核心视觉证据候选

核心比较可以直接呈现，帮助读者判断两组论点的证据基础。

## 待验证问题

仍需验证样本代表性与外部变化。
"""
            Path(prepared["output_path"]).write_text(markdown, encoding="utf-8")
            result = runner.commit()
            self.assertEqual(result["status"], "pending_human_review")
            receipt = read_json(run_dir / "artifact.json")
            self.assertEqual(receipt["schema"], "markdown_artifact.v1")
            self.assertEqual(receipt["artifact_kind"], "analysis")
            self.assertTrue((run_dir / "analysis.md").is_file())
            self.assertNotIn("content_markdown", receipt)

    def test_format_preflight_rejects_renderer_incompatible_chart(self) -> None:
        with self.assertRaisesRegex(StepError, "视觉预检未通过"):
            StepRunner._validate_v04_format_plan(
                {
                    "visuals": [
                        {
                            "type": "chart",
                            "title": "不完整图表",
                            "source_refs": ["E1"],
                            "data": {"categories": ["A", "B"]},
                        }
                    ]
                }
            )

    def test_format_schema_rejects_chart_without_renderer_data_shape(self) -> None:
        schema = read_json(ROOT / "skills/format/schemas/format_plan.v1.json")
        invalid = {
            "visuals": [
                {
                    "type": "chart",
                    "title": "缺失数值",
                    "source_refs": ["E1"],
                    "data": {"categories": ["A", "B"]},
                }
            ]
        }
        self.assertTrue(validate(invalid, schema))
        valid = {
            "visuals": [
                {
                    "type": "chart",
                    "title": "完整图表",
                    "source_refs": ["E1"],
                    "data": {
                        "chart_type": "bar",
                        "categories": ["A", "B"],
                        "values": [1, 2],
                    },
                }
            ]
        }
        self.assertEqual(validate(valid, schema), [])

    def test_format_schema_allows_runtime_projection_before_preflight(self) -> None:
        schema = read_json(ROOT / "skills/format/schemas/format_plan.v1.json")
        unresolved = {
            "visuals": [
                {
                    "type": "chart",
                    "title": "由证据资产物化",
                    "source_refs": ["E1:T1-usage"],
                }
            ]
        }
        self.assertEqual(validate(unresolved, schema), [])
        with self.assertRaisesRegex(StepError, "视觉预检未通过"):
            StepRunner._validate_v04_format_plan(unresolved)

    def test_format_schema_rejects_non_native_matrix_size(self) -> None:
        schema = read_json(ROOT / "skills/format/schemas/format_plan.v1.json")
        invalid = {
            "visuals": [
                {
                    "type": "matrix",
                    "title": "不是 2×2",
                    "source_refs": ["E1"],
                    "data": {"dimensions": ["A", "B", "C", "D", "E"]},
                }
            ]
        }
        self.assertTrue(validate(invalid, schema))

    def test_structured_failure_signature_is_stable_for_numeric_drift(self) -> None:
        first = classify_failure(
            "Format 视觉预检未通过：visual 1 的 chart data 不完整",
            stage="format",
        )
        second = classify_failure(
            "Format 视觉预检未通过：visual 2 的 chart data 不完整",
            stage="format",
        )
        self.assertEqual(first["error_code"], "invalid_data_shape")
        self.assertEqual(first["signature"], second["signature"])

    def test_post_render_visual_failure_is_owned_by_runtime(self) -> None:
        failure = classify_failure(
            "Renderer 视觉质量检查未通过：渲染图像接近空白",
            stage="format",
        )
        self.assertEqual(failure["error_code"], "visual_quality_failure")
        self.assertEqual(failure["responsible_stage"], "runtime")
        self.assertEqual(failure["repair_scope"], "renderer")

    def test_same_worker_failure_revises_once_then_circuit_breaks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run"
            task_dir = run_dir / "tasks" / "analysis-1_analysis"
            task_dir.mkdir(parents=True)
            input_path = task_dir / "input.json"
            input_path.write_text(
                json.dumps(
                    {
                        "contract_profile": "v0_4",
                        "brief": {"topic": "test"},
                        "raw_brief": {"topic": "test"},
                        "report_charter": {"topic": "test"},
                        "manager_task": {"agent_id": "analysis"},
                    }
                ),
                encoding="utf-8",
            )
            (task_dir / "run_state.json").write_text(
                json.dumps(
                    {
                        "agent_id": "analysis",
                        "agent_name": "Analysis",
                        "stage": 1,
                        "status": "running",
                        "current_step": "awaiting_gen_output",
                        "round_index": 0,
                        "input_path": str(input_path),
                        "produced_artifacts": [],
                        "history": [],
                        "p0_open": [],
                        "p1_open": [],
                        "contract_profile": "v0_4",
                    }
                ),
                encoding="utf-8",
            )
            state = {
                "version": "manager_state.v2",
                "contract_profile": "v0_4",
                "current_actor": "worker",
                "current_task": {
                    "task_id": "analysis-1",
                    "agent_id": "analysis",
                    "task_dir": str(task_dir),
                    "status": "dispatched",
                },
                "tasks": [],
                "accepted_artifacts": [],
                "spawn_adapter": "inline",
            }
            (run_dir / "manager_state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )
            manager = ManagerOrchestrator(ROOT, run_dir, contract_profile="v0_4")
            first = manager.record_worker_failure(StepError("missing required field 'x'"))
            self.assertEqual(first["step"], "revise")
            self.assertTrue(first["retry_same_task"])
            second = manager.record_worker_failure(StepError("missing required field 'x'"))
            self.assertEqual(second["status"], "blocked_repeated_failure")
            self.assertEqual(second["structured_error"]["error_code"], "contract_validation")

    def test_explicit_stage_revision_preserves_manager_choice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            (run_dir / "manager_state.json").write_text(
                json.dumps(
                    {
                        "contract_profile": "v0_4",
                        "current_actor": "human",
                        "human_gate": "final",
                        "status": "awaiting_final_approval",
                        "tasks": [],
                        "accepted_artifacts": [],
                    }
                ),
                encoding="utf-8",
            )
            manager = ManagerOrchestrator(ROOT, run_dir, contract_profile="v0_4")
            with patch.object(manager, "_dispatch", return_value={"actor": "worker"}) as dispatch:
                manager.revise_stage("report", "压缩正文")
            packet = dispatch.call_args.args[1]
            self.assertEqual(packet["agent_id"], "report")
            self.assertEqual(packet["revision_feedback"], ["压缩正文"])

    def test_v04_report_overflow_opens_page_budget_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            task_dir = run_dir / "tasks" / "report-1_report"
            task_dir.mkdir(parents=True)
            artifact_path = task_dir / "artifact.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema": "markdown_artifact.v1",
                        "agent_id": "report",
                        "artifact_kind": "report",
                        "content_path": str(task_dir / "report.md"),
                    }
                ),
                encoding="utf-8",
            )
            audit = {
                "stage": "report_preflight",
                "requested_body_page_limit": 3,
                "maximum_body_page_limit": 4,
                "body_page_count": 5,
                "passed": False,
                "requires_user_decision": True,
            }
            task = {
                "task_id": "report-1",
                "agent_id": "report",
                "task_dir": str(task_dir),
                "artifact_path": str(artifact_path),
                "status": "worker_completed",
            }
            state = {
                "version": "manager_state.v2",
                "contract_profile": "v0_4",
                "current_actor": "worker",
                "current_task": task,
                "tasks": [task],
                "accepted_artifacts": [],
                "project_state": {
                    "delivery_budget": {
                        "body_page_limit": 3,
                        "maximum_body_page_limit": 4,
                    }
                },
                "worker_result": {
                    "artifact_path": str(artifact_path),
                    "artifact": {"body_budget_audit": audit},
                },
                "spawn_adapter": "inline",
            }
            (run_dir / "manager_state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )
            manager = ManagerOrchestrator(ROOT, run_dir, contract_profile="v0_4")

            gate = manager._record_v04_worker_completed(state, task)

            self.assertEqual(gate["gate"], "page_budget")
            self.assertEqual(gate["page_budget_audit"]["body_page_count"], 5)
            self.assertEqual(
                [item["value"] for item in gate["questions"][0]["options"]],
                ["放宽", "收窄"],
            )

    def test_v04_page_budget_relaxation_persists_approved_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            task = {"task_id": "report-1", "agent_id": "report"}
            audit = {
                "stage": "report_preflight",
                "requested_body_page_limit": 3,
                "maximum_body_page_limit": 4,
                "body_page_count": 5,
                "passed": False,
                "requires_user_decision": True,
            }
            state = {
                "version": "manager_state.v2",
                "contract_profile": "v0_4",
                "current_actor": "human",
                "human_gate": "page_budget",
                "status": "awaiting_page_budget_decision",
                "current_task": task,
                "tasks": [task],
                "accepted_artifacts": [],
                "project_state": {
                    "delivery_budget": {
                        "body_page_limit": 3,
                        "maximum_body_page_limit": 4,
                    }
                },
                "pending_decision": {
                    "action": "dispatch",
                    "page_budget_audit": audit,
                },
            }
            (run_dir / "manager_state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )
            (run_dir / "state.json").write_text(
                json.dumps({"delivery_budget": state["project_state"]["delivery_budget"]}),
                encoding="utf-8",
            )
            manager = ManagerOrchestrator(ROOT, run_dir, contract_profile="v0_4")
            with patch.object(
                manager,
                "_record_v04_worker_completed",
                return_value={"actor": "worker"},
            ) as resumed:
                result = manager.record_human_feedback("放宽")

            self.assertEqual(result["actor"], "worker")
            resumed.assert_called_once()
            persisted = read_json(run_dir / "state.json")["delivery_budget"]
            self.assertEqual(persisted["maximum_body_page_limit"], 5)
            self.assertEqual(persisted["user_approved_body_page_limit"], 5)

    def test_continue_and_revise_commands_are_public_cli(self) -> None:
        continued = build_parser().parse_args(
            ["report", "continue", "--run", "run-id"]
        )
        self.assertEqual(continued.report_command, "continue")
        revised = build_parser().parse_args(
            [
                "report",
                "revise",
                "--run",
                "run-id",
                "--stage",
                "format",
                "--feedback",
                "图表不清楚",
            ]
        )
        self.assertEqual(revised.stage, "format")

    def test_continue_consumes_ready_worker_output_until_human_gate(self) -> None:
        brief = normalize_brief(
            {"topic": "AI 产品复访", "user_intent": "解释复访变化"},
            ROOT,
            "v0_4",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            brief_path = run_dir / "raw_brief.json"
            brief_path.write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
            manager = ManagerOrchestrator(ROOT, run_dir, contract_profile="v0_4")
            manager.initialize_run(brief_path)
            manager.record_human_feedback(
                json.dumps(
                    {
                        "research_purpose": "解释复访变化",
                        "research_direction": "判断结构变化是否为主因",
                        "high_confidence_evidence": [],
                        "brief_confirmed": True,
                    },
                    ensure_ascii=False,
                )
            )
            instruction = manager.approve()
            Path(instruction["instruction"]["output_path"]).write_text(
                """# Analysis

## 核心发现

当前证据表明结构变化值得优先验证，但仍需保留样本边界。这里补充完整分析文字，使下游能够理解判断、依据和决策含义。

## 竞争性解释与边界

外部环境和口径变化仍是可能的替代解释。

## 候选论点组

### 方案 A：聚焦结构变化

主论点和两个分论点共同回答研究问题。

### 方案 B：聚焦能力约束

保留另一个具有决策张力的完整解释。

## 核心视觉证据候选

核心比较可以直接呈现，帮助读者判断两组论点的证据基础。

## 待验证问题

需要继续验证样本代表性。
""",
                encoding="utf-8",
            )
            result = manager.continue_until_boundary()
            self.assertEqual(result["actor"], "human")
            self.assertEqual(result["gate"], "worker_result")
            self.assertEqual(manager.status()["state"]["failure_streak"], 0)

    def test_publish_deliverables_creates_stable_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run"
            run_dir.mkdir()
            source = run_dir / "tasks" / "format" / "report.docx"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"docx-placeholder")
            manager = ManagerOrchestrator(ROOT, run_dir, contract_profile="v0_4")
            published = manager._publish_deliverables([str(source)])
            self.assertEqual(len(published), 1)
            self.assertTrue(Path(published[0]).is_file())
            self.assertEqual(Path(published[0]).parent, run_dir / "deliverables")

    def test_directory_intake_reports_unsupported_files(self) -> None:
        profile = load_agent_profile(ROOT, "v0_4")
        spec = profile.support_specs["evidence_harvester"]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "notes.txt").write_text("有效材料", encoding="utf-8")
            (root / "rubric.py").write_text("RULE = 1", encoding="utf-8")
            _, summary = resolve_raw_materials(
                [{"path": str(root)}],
                spec=spec,
                base_dirs=[root],
            )
        self.assertFalse(summary["complete"])
        self.assertEqual(summary["unresolved_materials"], 1)
        self.assertTrue(summary["unsupported_files"][0].endswith("rubric.py"))


if __name__ == "__main__":
    unittest.main()
