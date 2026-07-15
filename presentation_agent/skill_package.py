from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from presentation_agent.io import read_json


@dataclass(frozen=True)
class SkillPackage:
    agent_id: str
    path: Path
    instructions: str = ""
    schemas: dict[str, Any] = field(default_factory=dict)
    selected_capabilities: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    context_requirements: list[str] = field(default_factory=list)
    fingerprint: str = ""
    budget: dict[str, Any] = field(default_factory=dict)
    legacy: bool = True

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "path": str(self.path),
            "exists": self.exists,
            "instructions": self.instructions,
            "schemas": self.schemas,
            "selected_capabilities": self.selected_capabilities,
            "tools": self.tools,
            "context_requirements": self.context_requirements,
            "fingerprint": self.fingerprint,
            "budget": self.budget,
            "legacy": self.legacy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillPackage":
        return cls(
            agent_id=str(data["agent_id"]),
            path=Path(str(data["path"])),
            instructions=str(data.get("instructions", "")),
            schemas=dict(data.get("schemas", {})),
            selected_capabilities=list(data.get("selected_capabilities", [])),
            tools=list(data.get("tools", [])),
            context_requirements=list(data.get("context_requirements", [])),
            fingerprint=str(data.get("fingerprint", "")),
            budget=dict(data.get("budget", {})),
            legacy=bool(data.get("legacy", True)),
        )


def load_skill_package(root: Path, agent_id: str) -> SkillPackage:
    package_dir = root / "skills" / agent_id
    instructions_path = package_dir / "SKILL.md"
    schemas_dir = package_dir / "schemas"

    instructions = instructions_path.read_text(encoding="utf-8") if instructions_path.exists() else ""
    schemas: dict[str, Any] = {}
    if schemas_dir.exists():
        for schema_path in sorted(schemas_dir.glob("*.json")):
            schemas[schema_path.stem] = read_json(schema_path)

    return SkillPackage(
        agent_id=agent_id,
        path=package_dir,
        instructions=instructions,
        schemas=schemas,
    )
