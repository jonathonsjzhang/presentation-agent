from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from presentation_agent.llm.schema import validate
from presentation_agent.machine_check import run_machine_checks
from presentation_agent.skill_package import load_skill_package


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v0_3"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for child in value.values():
            keys.update(all_keys(child))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for child in value:
            keys.update(all_keys(child))
        return keys
    return set()


def core_claim_nodes(storyline: dict[str, Any]) -> list[dict[str, Any]]:
    summary = storyline["executive_summary"]
    pyramid = storyline["message_pyramid"]
    nodes = [
        *summary["key_findings"],
        *summary["implications"],
        summary["expected_action"],
        pyramid["apex"],
        *pyramid["supporting_messages"],
    ]
    for section in storyline["report_outline"]["sections"]:
        nodes.append({
            "statement": section["section_thesis"],
            "finding_refs": section["finding_refs"],
            "evidence_refs": section["evidence_refs"],
        })
        nodes.extend(section["content_units"])
    return nodes


def evidence_by_finding(analysis: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for finding in analysis["findings"]:
        refs = {
            item["evidence_ref"]
            for item in finding["supporting_evidence"] + finding["counter_evidence"]
        }
        for explanation in finding["alternative_explanations"]:
            refs.update(explanation.get("evidence_refs", []))
        result[finding["finding_id"]] = refs
    return result


def upstream_request_errors(
    analysis: dict[str, Any],
    storyline: dict[str, Any],
) -> list[str]:
    blocking = analysis["evidence_execution"]["blocking_impact"] == "blocking"
    blocking = blocking or any(
        gap["blocking_level"] == "blocking" for gap in analysis["data_gaps"]
    )
    if not blocking:
        return []
    requests = storyline["upstream_revision_requests"]
    if not any(item["blocking_level"] == "blocking" for item in requests):
        return ["blocking evidence gap requires a blocking upstream revision request"]
    return []


class StorylineV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.analysis = read_json(FIXTURES / "analysis.v1.valid.json")
        self.storyline = read_json(FIXTURES / "storyline.v3.valid.json")
        self.analysis_schema = read_json(
            ROOT / "skills" / "analysis" / "schemas" / "analysis.v1.json"
        )
        self.storyline_schema = read_json(
            ROOT / "skills" / "storyline" / "schemas" / "storyline.v3.json"
        )
        self.rubrics = read_json(
            ROOT / "skills" / "storyline" / "rubrics.json"
        )["rubrics"]

    def test_independent_analysis_fixture_and_storyline_package_are_runnable(self) -> None:
        self.assertEqual(validate(self.analysis, self.analysis_schema), [])
        package = load_skill_package(ROOT, "storyline")
        self.assertTrue(package.exists)
        self.assertIn("一次输出", package.instructions)
        self.assertIn("upstream_revision_requests", package.instructions)
        self.assertIn("content units", package.instructions)
        self.assertNotIn("skills/storyline_design", package.instructions)
        self.assertEqual(len(package.rubrics), len(self.rubrics))
        self.assertIn("storyline.v3", package.schemas)

    def test_fixture_is_strict_storyline_v3_without_page_contract(self) -> None:
        self.assertEqual(validate(self.storyline, self.storyline_schema), [])
        forbidden = {
            "pages",
            "page",
            "page_no",
            "slides",
            "slide",
            "leadline",
            "layout",
            "chart_type",
            "visual_brief",
        }
        self.assertTrue(forbidden.isdisjoint(all_keys(self.storyline)))
        sections = self.storyline["report_outline"]["sections"]
        self.assertTrue(sections)
        self.assertTrue(all(section["content_units"] for section in sections))
        self.assertNotIn(
            "supporting_points",
            self.storyline_schema["properties"]["report_outline"]["properties"]
            ["sections"]["items"]["properties"],
        )

    def test_every_core_claim_references_real_analysis_findings_and_evidence(self) -> None:
        finding_ids = {item["finding_id"] for item in self.analysis["findings"]}
        allowed_evidence = evidence_by_finding(self.analysis)
        for node in core_claim_nodes(self.storyline):
            with self.subTest(statement=node["statement"]):
                refs = set(node["finding_refs"])
                self.assertTrue(refs)
                self.assertLessEqual(refs, finding_ids)
                permitted = set().union(*(allowed_evidence[ref] for ref in refs))
                self.assertLessEqual(set(node.get("evidence_refs", [])), permitted)

    def test_es_pyramid_sequence_and_outline_are_consistent(self) -> None:
        summary = self.storyline["executive_summary"]
        pyramid = self.storyline["message_pyramid"]
        self.assertEqual(summary["core_answer"], pyramid["apex"]["statement"])

        sections = self.storyline["report_outline"]["sections"]
        section_ids = [item["section_id"] for item in sections]

        seen: set[str] = set()
        for item in sections:
            self.assertLessEqual(set(item["depends_on"]), seen)
            seen.add(item["section_id"])

        section_finding_sets = [set(item["finding_refs"]) for item in sections]
        for message in pyramid["supporting_messages"]:
            self.assertTrue(
                any(set(message["finding_refs"]) <= refs for refs in section_finding_sets),
                message["message_id"],
            )

        coverage = self.storyline["editorial_decisions"]
        covered_ids = [item["finding_id"] for item in coverage]
        self.assertEqual(len(covered_ids), len(set(covered_ids)))
        self.assertEqual(
            set(covered_ids),
            {item["finding_id"] for item in self.analysis["findings"]},
        )

    def test_blocking_evidence_gap_requires_upstream_revision_request(self) -> None:
        insufficient = copy.deepcopy(self.analysis)
        insufficient["data_gaps"][0]["blocking_level"] = "blocking"
        missing_request = copy.deepcopy(self.storyline)
        self.assertTrue(upstream_request_errors(insufficient, missing_request))

        missing_request["upstream_revision_requests"].append({
            "request_type": "missing_evidence",
            "finding_refs": ["F-01"],
            "reason": "缺少控制初始意愿后的留存差异，无法支撑核心优先级判断。",
            "blocking_level": "blocking",
        })
        self.assertEqual(upstream_request_errors(insufficient, missing_request), [])
        self.assertEqual(validate(missing_request, self.storyline_schema), [])

    def test_machine_rubrics_accept_fixture_and_reject_page_shaped_output(self) -> None:
        self.assertEqual(
            [item for item in run_machine_checks(self.storyline, self.rubrics)
             if item.severity == "P0"],
            [],
        )
        page_shaped = copy.deepcopy(self.storyline)
        page_shaped["pages"] = [{"page_no": 1}]
        objections = run_machine_checks(page_shaped, self.rubrics)
        self.assertTrue(
            any(item.dimension == "storyline_v3_contract" for item in objections)
        )


if __name__ == "__main__":
    unittest.main()
