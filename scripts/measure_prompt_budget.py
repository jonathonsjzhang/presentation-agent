from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from presentation_agent.capabilities.compiler import compile_skill_package
from presentation_agent.io import read_json
from presentation_agent.models import AgentSpec


CASES = [
    {"name": "board_deep_dive_ppt", "audience": "board", "report_type": "deep_dive", "output_format": "ppt"},
    {
        "name": "business_progress_document",
        "audience": "business_team",
        "report_type": "business_progress",
        "output_format": "document",
    },
    {"name": "external_quick_sync_html", "audience": "external", "report_type": "quick_sync", "output_format": "html"},
]
AGENTS = [
    "argument_synthesis",
    "storyline_design",
    "page_filling",
    "format",
    "qa_preparation",
    "speaker_script",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure compiled Worker prompt budgets.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--baseline-ref", default="main")
    parser.add_argument("--out")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    baselines = {
        agent_id: _baseline(root, args.baseline_ref, agent_id) for agent_id in AGENTS
    }
    cases: list[dict[str, Any]] = []
    for agent_id in AGENTS:
        spec = _spec(root, agent_id)
        baseline = baselines[agent_id]
        for case in CASES:
            package = compile_skill_package(root, spec, case, legacy_fallback=False)
            budget = dict(package.budget)
            if baseline:
                budget["instruction_reduction_pct"] = _reduction(
                    baseline["instruction_chars"], budget["instruction_chars"]
                )
                budget["rubric_reduction_pct"] = _reduction(
                    baseline["rubric_chars"], budget["rubric_chars"]
                )
            cases.append(
                {
                    "agent_id": agent_id,
                    "name": case["name"],
                    "selected_capabilities": package.selected_capabilities,
                    "fingerprint": package.fingerprint,
                    "budget": budget,
                }
            )
    result = {"baselines": baselines, "cases": cases}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)


def _spec(root: Path, agent_id: str) -> AgentSpec:
    agents = read_json(root / "configs" / "agents.json")["agents"]
    return AgentSpec.from_dict(next(item for item in agents if item["id"] == agent_id))


def _baseline(root: Path, ref: str, agent_id: str) -> dict[str, int]:
    skill = _git_show(root, ref, f"skills/{agent_id}/SKILL.md")
    rubrics_raw = _git_show(root, ref, f"skills/{agent_id}/rubrics.json")
    if skill is None or rubrics_raw is None:
        return {}
    return {
        "instruction_chars": len(skill),
        "rubric_chars": len(rubrics_raw),
    }


def _git_show(root: Path, ref: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def _reduction(before: int, after: int) -> float:
    return round((before - after) / before * 100, 1) if before else 0.0


if __name__ == "__main__":
    main()
