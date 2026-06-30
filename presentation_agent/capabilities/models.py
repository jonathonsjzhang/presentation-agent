from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class CapabilityError(ValueError):
    """Raised when a capability profile or bundle cannot be resolved safely."""


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    kind: str
    path: str
    select_when: dict[str, str] = field(default_factory=dict)
    applies_to: tuple[str, ...] = ()
    owns: tuple[str, ...] = ()
    incompatible_with: tuple[str, ...] = ()
    prompt_budget_tokens: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, path: str) -> "CapabilitySpec":
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            path=path,
            select_when={str(k): str(v) for k, v in data.get("select_when", {}).items()},
            applies_to=tuple(str(v) for v in data.get("applies_to", [])),
            owns=tuple(str(v) for v in data.get("owns", [])),
            incompatible_with=tuple(str(v) for v in data.get("incompatible_with", [])),
            prompt_budget_tokens=int(data.get("prompt_budget_tokens", 0)),
        )


@dataclass(frozen=True)
class CapabilitySelection:
    agent_id: str
    audience: str
    report_type: str
    output_format: str
    capability_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "audience": self.audience,
            "report_type": self.report_type,
            "output_format": self.output_format,
            "capability_ids": list(self.capability_ids),
        }
