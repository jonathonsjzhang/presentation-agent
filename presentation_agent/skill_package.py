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
            "rubrics": self.rubrics,
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
            rubrics=list(data.get("rubrics", [])),
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
    rubrics_path = package_dir / "rubrics.json"
    schemas_dir = package_dir / "schemas"

    instructions = instructions_path.read_text(encoding="utf-8") if instructions_path.exists() else ""
    reference_bundle = _load_reference_bundle(package_dir)
    if reference_bundle:
        instructions = (
            f"{instructions.rstrip()}\n\n"
            "===== BUNDLED REFERENCES（运行时已注入，无需读取本地路径） =====\n"
            f"{reference_bundle}"
        )
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


def _load_reference_bundle(package_dir: Path) -> str:
    """Load only references explicitly opted into the generation prompt.

    Generic LLM adapters cannot open local paths mentioned by SKILL.md. A small
    package-owned manifest therefore makes progressive disclosure executable
    and keeps unrelated examples out of the prompt.
    """
    manifest = read_json(
        package_dir / "reference_manifest.json",
        default={"generation": []},
    )
    files = manifest.get("generation", [])
    if not isinstance(files, list):
        raise ValueError("reference_manifest.json generation must be an array")

    package_root = package_dir.resolve()
    sections: list[str] = []
    for relative in files:
        target = (package_dir / str(relative)).resolve()
        try:
            target.relative_to(package_root)
        except ValueError as exc:
            raise ValueError(f"reference escapes skill package: {relative}") from exc
        if not target.is_file():
            raise ValueError(f"reference not found: {relative}")
        text = target.read_text(encoding="utf-8").strip()
        sections.append(f"\n## Reference: {relative}\n{text}")

    bundle = "\n".join(sections).strip()
    max_chars = int(manifest.get("max_chars", 12000))
    if len(bundle) > max_chars:
        raise ValueError(
            f"reference bundle exceeds max_chars: {len(bundle)} > {max_chars}"
        )
    return bundle
