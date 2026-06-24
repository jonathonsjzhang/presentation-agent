from __future__ import annotations

from typing import Any, Protocol

from presentation_agent.models import AgentSpec, Objection


class SkillContext(dict):
    """Runtime context passed into skills."""


class Skill(Protocol):
    id: str

    def generation_dimensions(self) -> list[str]:
        ...

    def run(self, spec: AgentSpec, input_data: dict[str, Any], context: SkillContext) -> dict[str, Any]:
        ...

    def revise(
        self,
        spec: AgentSpec,
        input_data: dict[str, Any],
        previous_artifact: dict[str, Any],
        objections: list[Objection],
        context: SkillContext,
    ) -> dict[str, Any]:
        ...

