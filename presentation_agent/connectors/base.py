from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from presentation_agent.models import AgentSpec


@dataclass(frozen=True)
class ConnectorContext:
    """Target-agent context passed to input connectors."""

    agent_id: str
    agent_name: str
    input_schema: str
    output_schema: str
    accepted_material_formats: tuple[str, ...]
    declared_connectors: tuple[str, ...]

    @classmethod
    def from_spec(cls, spec: AgentSpec) -> "ConnectorContext":
        input_contract = spec.input_contract or {}
        harness = spec.harness or {}
        return cls(
            agent_id=spec.id,
            agent_name=spec.name,
            input_schema=spec.input_schema,
            output_schema=spec.output_schema,
            accepted_material_formats=tuple(input_contract.get("accepted_material_formats", [])),
            declared_connectors=tuple(harness.get("connectors", [])),
        )


class Connector(Protocol):
    """File intake adapter used by skill input preparation."""

    name: str
    suffixes: tuple[str, ...]

    def supports(self, path: Path, context: ConnectorContext) -> bool:
        ...

    def load(self, path: Path, context: ConnectorContext) -> dict[str, Any]:
        ...


class SuffixConnector:
    """Base implementation for connectors selected by file extension."""

    name = "suffix_connector"
    suffixes: tuple[str, ...] = ()

    def supports(self, path: Path, context: ConnectorContext) -> bool:
        return path.suffix.lower() in self.suffixes
