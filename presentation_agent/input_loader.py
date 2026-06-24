from __future__ import annotations

from pathlib import Path
from typing import Any

from presentation_agent.connectors.registry import load_with_connector
from presentation_agent.io import read_json
from presentation_agent.models import AgentSpec


def load_agent_input(path: Path, spec: AgentSpec) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return read_json(path)
    return load_with_connector(path, spec)
