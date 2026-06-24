"""Input connectors for presentation-agent skills."""

from presentation_agent.connectors.base import Connector, ConnectorContext
from presentation_agent.connectors.registry import connector_for, list_connectors, load_with_connector

__all__ = [
    "Connector",
    "ConnectorContext",
    "connector_for",
    "list_connectors",
    "load_with_connector",
]
