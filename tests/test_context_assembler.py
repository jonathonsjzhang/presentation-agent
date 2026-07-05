from __future__ import annotations

import unittest
from pathlib import Path

from presentation_agent.agent_profiles import LEGACY_CONTRACT_PROFILE
from presentation_agent.context import ContextAssembler


ROOT = Path(__file__).resolve().parents[1]


class ContextAssemblerTests(unittest.TestCase):
    def test_projects_required_fields_without_flattening_artifacts(self) -> None:
        assembler = ContextAssembler(
            ROOT, contract_profile=LEGACY_CONTRACT_PROFILE
        )
        artifact_path = Path("/tmp/argument.json")
        context = assembler.assemble(
            worker_id="storyline_design",
            report_charter={"topic": "权威主题", "audience": "board"},
            manager_task={"task_id": "story-1"},
            raw_brief={"topic": "原始主题", "raw_note": "按需读取"},
            raw_brief_path=Path("/tmp/raw_brief.json"),
            artifacts=[(
                artifact_path,
                {
                    "schema": "argument_synthesis.v1",
                    "agent_id": "argument_synthesis",
                    "topic": "上游主题",
                    "core_thesis": "核心判断",
                    "evidence_bank": [{"id": "E1"}],
                    "internal_debug_trace": "不应内联",
                },
            )],
        )

        self.assertEqual(context["schema"], "worker_context.v1")
        self.assertEqual(context["report_charter"]["topic"], "权威主题")
        self.assertNotIn("core_thesis", context)
        source = context["inputs"]["argument_synthesis"]
        self.assertEqual(source["inline_fields"]["core_thesis"], "核心判断")
        self.assertNotIn("internal_debug_trace", source["inline_fields"])
        self.assertEqual(context["raw_brief"]["topic"], "原始主题")
        self.assertNotIn("raw_note", context["raw_brief"])
        self.assertEqual(context["material_refs"][0]["source_id"], "raw_brief")
        self.assertEqual(
            context["material_refs"][1]["omitted_fields"],
            ["schema", "agent_id", "internal_debug_trace"],
        )
        self.assertEqual(context["upstream_signal"]["topic"], "上游主题")
        self.assertEqual(context["upstream_signal"]["core_thesis"], "核心判断")

    def test_duplicate_source_ids_receive_stable_suffixes(self) -> None:
        assembler = ContextAssembler(
            ROOT, contract_profile=LEGACY_CONTRACT_PROFILE
        )
        context = assembler.assemble(
            worker_id="storyline_design",
            report_charter={},
            manager_task={},
            raw_brief={},
            artifacts=[
                (Path("/tmp/a.json"), {"agent_id": "argument_synthesis"}),
                (Path("/tmp/b.json"), {"agent_id": "argument_synthesis"}),
            ],
        )

        self.assertEqual(
            list(context["inputs"]),
            ["argument_synthesis", "argument_synthesis_2"],
        )

    def test_unknown_worker_fails_open_with_namespaced_full_artifact(self) -> None:
        assembler = ContextAssembler(
            ROOT, contract_profile=LEGACY_CONTRACT_PROFILE
        )
        context = assembler.assemble(
            worker_id="future_worker",
            report_charter={},
            manager_task={},
            raw_brief={},
            artifacts=[(Path("/tmp/future.json"), {"schema": "future.v1", "value": 1})],
        )

        self.assertEqual(
            context["inputs"]["future_v1"]["inline_fields"]["value"],
            1,
        )
        self.assertEqual(context["material_refs"], [])

    def test_large_required_field_uses_preview_and_file_reference(self) -> None:
        assembler = ContextAssembler(
            ROOT, contract_profile=LEGACY_CONTRACT_PROFILE
        )
        large_pages = [{"title": f"page-{index}", "body": "x" * 5000} for index in range(4)]
        context = assembler.assemble(
            worker_id="page_filling",
            report_charter={},
            manager_task={},
            raw_brief={},
            artifacts=[(
                Path("/tmp/storyline.json"),
                {"agent_id": "storyline_design", "pages": large_pages},
            )],
        )

        pages = context["inputs"]["storyline_design"]["inline_fields"]["pages"]
        self.assertEqual(pages["_projection"], "list_preview")
        self.assertEqual(pages["item_count"], 4)
        self.assertEqual(len(pages["preview"]), 3)
        self.assertEqual(
            context["material_refs"][0]["projected_fields"],
            ["pages"],
        )

    def test_page_filling_keeps_granular_evidence_above_default_limit(self) -> None:
        assembler = ContextAssembler(
            ROOT, contract_profile=LEGACY_CONTRACT_PROFILE
        )
        evidence = [
            {"id": f"E-{index}", "detail": "x" * 1000}
            for index in range(20)
        ]
        context = assembler.assemble(
            worker_id="page_filling",
            report_charter={},
            manager_task={},
            raw_brief={"evidence_bank": evidence},
            raw_brief_path=Path("/tmp/raw_brief.json"),
            artifacts=[],
        )

        self.assertEqual(context["raw_brief"]["evidence_bank"], evidence)
        self.assertFalse(
            any(
                ref["source_id"] == "raw_brief"
                for ref in context["material_refs"]
            )
        )

    def test_format_keeps_full_page_contract_above_default_limit(self) -> None:
        assembler = ContextAssembler(
            ROOT, contract_profile=LEGACY_CONTRACT_PROFILE
        )
        pages = [
            {
                "page_no": index,
                "page_takeaway": f"结论-{index}",
                "body": "x" * 5000,
            }
            for index in range(10)
        ]
        context = assembler.assemble(
            worker_id="format",
            report_charter={},
            manager_task={},
            raw_brief={},
            artifacts=[(
                Path("/tmp/page_content.json"),
                {"agent_id": "page_filling", "pages": pages},
            )],
        )

        inline_pages = context["inputs"]["page_filling"]["inline_fields"]["pages"]
        self.assertEqual(inline_pages, pages)


if __name__ == "__main__":
    unittest.main()
