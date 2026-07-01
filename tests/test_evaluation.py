from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from presentation_agent.evaluation.adapters import (
    extract_context_text,
    infer_format,
    prepare_artifact,
)
from presentation_agent.evaluation.runner import EvalError, EvaluationRunner
from presentation_agent.io import write_json


ROOT = Path(__file__).resolve().parents[1]


def _score(dimension: str, score: float) -> dict:
    return {
        "dimension_id": dimension,
        "score": score,
        "rationale": f"{dimension} scored from concrete artifact evidence",
        "evidence": [
            {
                "location": "page 1",
                "observation": f"observed evidence for {dimension}",
            }
        ],
        "issues": [f"{dimension} still has one material issue"],
        "recommendations": [f"improve {dimension} using the cited page"],
    }


def _judgement(role: str) -> dict:
    dimensions = (
        [
            _score("information_density", 4.0),
            _score("storyline", 3.5),
            _score("expression", 4.0),
        ]
        if role == "content"
        else [_score("information_presentation", 3.0)]
    )
    return {
        "schema": "e2e_judgement.v1",
        "judge_role": role,
        "rubric_version": "v0.2",
        "dimension_scores": dimensions,
        "overall_assessment": f"{role} assessment",
        "confidence": "high",
        "inspected_visuals": ["page-001.png"] if role == "visual" else [],
    }


class ArtifactAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_infer_supported_formats(self) -> None:
        self.assertEqual(infer_format(Path("x.pptx")), "ppt")
        self.assertEqual(infer_format(Path("x.docx")), "document")
        self.assertEqual(infer_format(Path("x.html")), "html")

    def test_prepare_html_without_visual_runtime(self) -> None:
        html = self.tmp / "candidate.html"
        html.write_text(
            "<html><body><section class='unit'><h1>结论先行</h1>"
            "<p>已有材料支持这一判断。</p></section></body></html>",
            encoding="utf-8",
        )
        prepared = prepare_artifact(
            html,
            self.tmp / "prepared",
            render_visuals=False,
        )
        self.assertEqual(prepared.format, "html")
        self.assertEqual(prepared.unit_count, 1)
        self.assertIn("结论先行", Path(prepared.extracted_text_path).read_text(encoding="utf-8"))
        self.assertEqual(prepared.visual_paths, [])

    def test_context_json_is_pretty_printed(self) -> None:
        path = self.tmp / "brief.json"
        path.write_text('{"audience":"board","decision_goal":"approve"}', encoding="utf-8")
        text = extract_context_text(path)
        self.assertIn('"audience": "board"', text)


class EvaluationRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.html = self.tmp / "candidate.html"
        self.html.write_text(
            "<html><body><section class='unit'><h1>核心结论</h1>"
            "<p>证据与业务含义。</p></section></body></html>",
            encoding="utf-8",
        )
        self.brief = self.tmp / "brief.json"
        self.brief.write_text(
            json.dumps(
                {
                    "audience": "board",
                    "decision_goal": "确认资源优先级",
                    "output_format": "html",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.runner = EvaluationRunner(ROOT, run_dir=self.tmp / "run")

    def test_host_driven_round_trip_and_aggregation(self) -> None:
        started = self.runner.start(
            self.html,
            brief_path=self.brief,
            render_visuals=False,
        )
        self.assertEqual(started["state"]["current_job"], "content")
        self.assertFalse(started["hard_gates"]["passed"])

        content_output = Path(started["instruction"]["output_path"])
        write_json(content_output, _judgement("content"))
        advanced = self.runner.submit()
        self.assertEqual(advanced["next_instruction"]["job"], "visual")

        visual_output = Path(advanced["next_instruction"]["output_path"])
        write_json(visual_output, _judgement("visual"))
        completed = self.runner.submit()
        self.assertEqual(completed["status"], "completed")
        report = completed["report"]
        self.assertEqual(report["total_score"], 3.65)
        self.assertEqual(report["normalized_score_100"], 73.0)
        self.assertEqual(report["verdict"], "not_usable")
        self.assertEqual(len(report["scores"]), 4)
        self.assertLessEqual(len(report["major_issues"]), 3)

    def test_rejects_wrong_dimension_set(self) -> None:
        started = self.runner.start(self.html, render_visuals=False)
        bad = _judgement("content")
        bad["dimension_scores"] = bad["dimension_scores"][:2]
        write_json(Path(started["instruction"]["output_path"]), bad)
        with self.assertRaises(EvalError):
            self.runner.submit()

    def test_rejects_non_half_step_score(self) -> None:
        started = self.runner.start(self.html, render_visuals=False)
        bad = _judgement("content")
        bad["dimension_scores"][0]["score"] = 3.7
        write_json(Path(started["instruction"]["output_path"]), bad)
        with self.assertRaises(EvalError):
            self.runner.submit()


if __name__ == "__main__":
    unittest.main()
