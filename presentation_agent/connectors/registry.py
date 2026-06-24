from __future__ import annotations

from pathlib import Path

from presentation_agent.connectors.base import Connector, ConnectorContext
from presentation_agent.connectors.csv import CsvConnector
from presentation_agent.connectors.docx import DocxConnector
from presentation_agent.connectors.xlsx import XlsxConnector
from presentation_agent.models import AgentSpec


_CONNECTORS: tuple[Connector, ...] = (
    DocxConnector(),
    CsvConnector(),
    XlsxConnector(),
)


def connector_for(path: Path, spec: AgentSpec) -> Connector:
    context = ConnectorContext.from_spec(spec)
    for connector in _CONNECTORS:
        if connector.supports(path, context):
            return connector
    supported = ", ".join(sorted({suffix for connector in _CONNECTORS for suffix in connector.suffixes}))
    raise ValueError(f"Unsupported input for {spec.id}: {path} (registered suffixes: {supported})")


def load_with_connector(path: Path, spec: AgentSpec) -> dict:
    context = ConnectorContext.from_spec(spec)
    connector = connector_for(path, spec)
    return connector.load(path, context)


def list_connectors() -> list[dict[str, object]]:
    return [
        {"name": connector.name, "suffixes": list(connector.suffixes)}
        for connector in _CONNECTORS
    ]
