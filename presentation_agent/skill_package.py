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
    rubrics: list[str] = field(default_factory=list)
    schemas: dict[str, Any] = field(default_factory=dict)

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "path": str(self.path),
            "exists": self.exists,
            "instructions": self.instructions,
            "rubrics": self.rubrics,
            "schemas": self.schemas,
        }


def load_skill_package(root: Path, agent_id: str) -> SkillPackage:
    package_dir = root / "skills" / agent_id
    instructions_path = package_dir / "SKILL.md"
    rubrics_path = package_dir / "rubrics.json"
    schemas_dir = package_dir / "schemas"

    instructions = instructions_path.read_text(encoding="utf-8") if instructions_path.exists() else ""
    rubrics_data = read_json(rubrics_path, default={"rubrics": []})
    schemas: dict[str, Any] = {}
    if schemas_dir.exists():
        for schema_path in sorted(schemas_dir.glob("*.json")):
            schemas[schema_path.stem] = read_json(schema_path)

    return SkillPackage(
        agent_id=agent_id,
        path=package_dir,
        instructions=instructions,
        rubrics=list(rubrics_data.get("rubrics", [])),
        schemas=schemas,
    )

