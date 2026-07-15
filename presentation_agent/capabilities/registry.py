from __future__ import annotations

from pathlib import Path
from typing import Any

from presentation_agent.capabilities.models import CapabilityError, CapabilitySpec
from presentation_agent.io import read_json


class CapabilityRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.config = read_json(root / "configs" / "capabilities.json", default={})

    @property
    def runtime(self) -> dict[str, Any]:
        return dict(self.config.get("runtime", {}))

    def enabled_for(self, agent_id: str) -> bool:
        runtime = self.runtime
        return bool(runtime.get("enabled")) and agent_id in set(runtime.get("pilot_agents", []))

    def inventory(self, core_agents: list[str] | None = None) -> list[dict[str, Any]]:
        rows = [
            {
                "id": f"core.{agent_id}",
                "kind": "core",
                "applies_to": [agent_id],
                "path": str(self.root / "skills" / agent_id),
            }
            for agent_id in (core_agents or [])
        ]
        kind_paths = {
            "audience": "audience",
            "report_type": "report_type",
            "output_format": "format",
        }
        for dimension, values in self.config.get("dimensions", {}).items():
            package_kind = kind_paths[dimension]
            for value in values:
                spec, _ = self.atomic_capability(package_kind, str(value))
                rows.append(
                    {
                        "id": spec.id,
                        "kind": spec.kind,
                        "applies_to": list(spec.applies_to),
                        "owns": list(spec.owns),
                        "path": spec.path,
                    }
                )
        return rows

    def atomic_capability(self, kind: str, value: str) -> tuple[CapabilitySpec, dict[str, Any]]:
        package_dir = self.root / "skills" / "atomic" / kind / value
        manifest_path = package_dir / "manifest.json"
        if not manifest_path.exists():
            raise CapabilityError(f"Capability manifest not found: {manifest_path}")
        manifest = read_json(manifest_path)
        spec = CapabilitySpec.from_dict(manifest, path=str(package_dir))
        if spec.kind != kind:
            raise CapabilityError(
                f"Capability {spec.id} declares kind={spec.kind!r}, expected {kind!r}"
            )
        selection_key = "output_format" if kind == "format" else kind
        if spec.select_when.get(selection_key) != value:
            raise CapabilityError(
                f"Capability {spec.id} select_when does not match {selection_key}={value}"
            )
        return spec, {
            "instructions": (package_dir / "SKILL.md").read_text(encoding="utf-8")
            if (package_dir / "SKILL.md").exists()
            else "",
            "rules": read_json(package_dir / "rules.json", default={"rules": []}).get("rules", []),
            "tools": read_json(package_dir / "tools.json", default={"tools": []}).get("tools", []),
        }
