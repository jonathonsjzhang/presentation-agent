from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from presentation_agent.llm.types import LLMRequest


class MockAdapter:
    """Offline model channel for tests, CI, and loop development.

    Resolution order for a request:
    1. A recorded fixture file matching purpose + agent_id (exact replay).
    2. A purpose-only fixture.
    3. A synthesized minimal payload that satisfies request.schema, so the loop
       can run end to end without any real model.
    """

    kind = "mock"

    def __init__(self, fixtures_dir: Optional[Path] = None) -> None:
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else None

    def generate(self, request: LLMRequest) -> str:
        fixture = self._load_fixture(request)
        if fixture is not None:
            return json.dumps(fixture, ensure_ascii=False)
        # A mock reviewer must default to "clean pass" (no objections), otherwise
        # schema-synthesis would fabricate a placeholder P0 and block the loop.
        if request.purpose == "review":
            return '```json\n{"objections": []}\n```'
        # A mock stop_checker must default to "can_stop=true", otherwise
        # schema-synthesis produces False (boolean default) and blocks every test.
        if request.purpose == "stop_check":
            return '```json\n{"can_stop": true, "confidence": "high"}\n```'
        synthesized = synthesize_from_schema(request.schema or {})
        return "```json\n" + json.dumps(synthesized, ensure_ascii=False, indent=2) + "\n```"

    def _load_fixture(self, request: LLMRequest) -> Optional[dict[str, Any]]:
        if not self.fixtures_dir or not self.fixtures_dir.exists():
            return None
        candidates = []
        if request.agent_id:
            candidates.append(f"{request.purpose}__{request.agent_id}.json")
        candidates.append(f"{request.purpose}.json")
        for name in candidates:
            path = self.fixtures_dir / name
            if path.exists():
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
        return None


def synthesize_from_schema(schema: dict[str, Any]) -> Any:
    """Build the smallest value that satisfies a (subset) JSON schema.

    Honors const/enum/type/properties/required/items. Required object fields are
    always emitted; optional fields are skipped to keep payloads minimal.
    """
    if not schema:
        return {}

    if "const" in schema:
        return schema["const"]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((t for t in schema_type if t != "null"), schema_type[0])

    if schema_type == "object" or "properties" in schema:
        result: dict[str, Any] = {}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        for key, subschema in properties.items():
            if key in required and isinstance(subschema, dict):
                result[key] = synthesize_from_schema(subschema)
        return result

    if schema_type == "array":
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            return [synthesize_from_schema(item_schema)]
        return []

    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0
    if schema_type == "boolean":
        return False
    if schema_type == "null":
        return None
    return "TBD"
