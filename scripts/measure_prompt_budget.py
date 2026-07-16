from __future__ import annotations

import argparse
import json
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
    "analysis",
    "storyline",
    "report",
    "format",
    "qa_preparation",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure compiled Worker prompt budgets.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--out")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    cases: list[dict[str, Any]] = []
    for agent_id in AGENTS:
        spec = _spec(root, agent_id)
        for case in CASES:
            package = compile_skill_package(root, spec, case, legacy_fallback=False)
            budget = dict(package.budget)
            cases.append(
                {
                    "agent_id": agent_id,
                    "name": case["name"],
                    "selected_capabilities": package.selected_capabilities,
                    "fingerprint": package.fingerprint,
                    "budget": budget,
                }
            )
    result = {"cases": cases}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)


def _spec(root: Path, agent_id: str) -> AgentSpec:
    config = read_json(root / "configs" / "agents.json")
    profile_id = str(config.get("active_contract_profile") or "v0_4")
    workers = config["contract_profiles"][profile_id]["workers"]
    return AgentSpec.from_dict(next(item for item in workers if item["id"] == agent_id))


if __name__ == "__main__":
    main()
