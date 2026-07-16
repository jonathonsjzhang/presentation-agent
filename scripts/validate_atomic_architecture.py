from __future__ import annotations

import json
import sys
import tempfile
from itertools import product
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from presentation_agent.capabilities.compiler import compile_skill_package
from presentation_agent.io import read_json
from presentation_agent.models import AgentSpec
from presentation_agent.renderers import render_material


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    config = read_json(root / "configs" / "capabilities.json")
    agents_config = read_json(root / "configs" / "agents.json")
    profile_id = str(agents_config.get("active_contract_profile") or "v0_4")
    profile = agents_config["contract_profiles"][profile_id]
    active = set(profile["canonical_stages"])
    specs = [
        AgentSpec.from_dict(row)
        for row in profile["workers"]
        if row["id"] in active
    ]

    compiled: list[dict[str, Any]] = []
    for spec, audience, report_type, output_format in product(
        specs,
        config["dimensions"]["audience"],
        config["dimensions"]["report_type"],
        config["dimensions"]["output_format"],
    ):
        package = compile_skill_package(
            root,
            spec,
            {
                "audience": audience,
                "report_type": report_type,
                "output_format": output_format,
            },
            legacy_fallback=False,
        )
        compiled.append({
            "agent_id": spec.id,
            "profile": [audience, report_type, output_format],
            "fingerprint": package.fingerprint,
            "legacy": package.legacy,
        })

    render_results: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as temp:
        out_dir = Path(temp)
        for output_format, unit_type in (
            ("ppt", "slide"),
            ("document", "document_section"),
            ("html", "html_module"),
        ):
            material = {
                "format": output_format,
                "topic": "Atomic architecture smoke test",
                "material_units": [{
                    "unit_id": "u1",
                    "unit_type": unit_type,
                    "headline": "原子能力架构可以按目标载体稳定生成正式材料",
                    "layout_or_structure": {"layout_type": "key_takeaway"},
                    "finalized_content": {
                        "primary_text": "Renderer smoke test",
                        "supporting_points": ["bundle 与 renderer 一致"],
                    },
                    "source_display": {"footer": "Source: deterministic smoke test"},
                }],
            }
            result = render_material(
                material,
                out_dir,
                expected_format=output_format,
                selected_capabilities=[f"format.{output_format}"],
            )
            render_results[output_format] = result.to_dict()

    failures = [
        row for row in compiled if row["legacy"] or not row["fingerprint"]
    ]
    render_failures = {
        key: value
        for key, value in render_results.items()
        if value["status"] != "rendered"
    }
    expected_bundle_count = (
        len(specs)
        * len(config["dimensions"]["audience"])
        * len(config["dimensions"]["report_type"])
        * len(config["dimensions"]["output_format"])
    )
    report = {
        "bundle_count": len(compiled),
        "expected_bundle_count": expected_bundle_count,
        "bundle_failures": failures,
        "render_results": render_results,
        "passed": len(compiled) == expected_bundle_count
        and not failures
        and not render_failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
