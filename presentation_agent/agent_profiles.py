from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from presentation_agent.io import read_json
from presentation_agent.models import AgentSpec


LEGACY_CONTRACT_PROFILE = "legacy.v0_2"


class AgentProfileError(ValueError):
    """Raised when an agent contract profile cannot be loaded."""


@dataclass(frozen=True)
class AgentProfile:
    """Resolved worker definitions for one runtime contract profile."""

    contract_profile: str
    config: dict[str, Any]
    profile_config: dict[str, Any]
    specs: dict[str, AgentSpec]
    ordered_specs: list[AgentSpec]


def load_agent_profile(
    root: Path,
    contract_profile: Optional[str] = None,
) -> AgentProfile:
    """Load the sole runtime view of worker specs and their canonical order.

    Omitting ``contract_profile`` follows ``active_contract_profile``.
    Compatibility profiles remain available only through an explicit profile
    selection.
    """

    config = read_json(root / "configs" / "agents.json")
    selected = contract_profile or str(
        config.get("active_contract_profile") or LEGACY_CONTRACT_PROFILE
    )

    if selected == LEGACY_CONTRACT_PROFILE:
        rows = config.get("agents", [])
        profile_config = config.get("pipeline", {})
        declared_order = profile_config.get("stages", [])
    else:
        profiles = config.get("contract_profiles", {})
        profile_config = profiles.get(selected)
        if not isinstance(profile_config, dict):
            available = ", ".join(sorted(profiles)) or "(none)"
            raise AgentProfileError(
                f"unknown contract profile {selected!r}; available: "
                f"{LEGACY_CONTRACT_PROFILE}, {available}"
            )
        rows = profile_config.get("workers", [])
        declared_order = profile_config.get("canonical_stages", [])
        extension_ids = set(profile_config.get("extension_workers", []))
        extension_overrides = profile_config.get(
            "extension_worker_overrides", {}
        )
        if extension_ids:
            rows = list(rows) + [
                {
                    **row,
                    **dict(extension_overrides.get(row.get("id"), {})),
                }
                for row in config.get("agents", [])
                if row.get("id") in extension_ids
            ]

    if not isinstance(rows, list) or not rows:
        raise AgentProfileError(f"contract profile {selected!r} has no workers")

    specs: dict[str, AgentSpec] = {}
    for row in rows:
        spec = AgentSpec.from_dict(row)
        if spec.id in specs:
            raise AgentProfileError(
                f"contract profile {selected!r} has duplicate worker {spec.id!r}"
            )
        specs[spec.id] = spec

    ordered_specs = [specs[item] for item in declared_order if item in specs]
    if not ordered_specs:
        ordered_specs = sorted(specs.values(), key=lambda spec: spec.stage)
    return AgentProfile(
        contract_profile=selected,
        config=config,
        profile_config=profile_config,
        specs=specs,
        ordered_specs=ordered_specs,
    )
