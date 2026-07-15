from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

Severity = Literal["P0", "P1"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    stage: int
    skill: str
    input_schema: str
    output_schema: str
    memory_dimensions: list[str]
    max_revision_rounds: int = 2
    description: str = ""
    previous_agent_id: str | None = None
    next_agent_id: str | None = None
    input_contract: dict[str, Any] = field(default_factory=dict)
    output_contract: dict[str, Any] = field(default_factory=dict)
    loop_policy: dict[str, Any] = field(default_factory=dict)
    state_contract: dict[str, Any] = field(default_factory=dict)
    harness: dict[str, Any] = field(default_factory=dict)
    optional_features: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentSpec":
        return cls(
            id=data["id"],
            name=data["name"],
            stage=int(data["stage"]),
            skill=data["skill"],
            input_schema=data["input_schema"],
            output_schema=data["output_schema"],
            memory_dimensions=list(data.get("memory_dimensions", [])),
            max_revision_rounds=int(data.get("max_revision_rounds", 2)),
            description=str(data.get("description", "")),
            previous_agent_id=data.get("previous_agent_id"),
            next_agent_id=data.get("next_agent_id"),
            input_contract=dict(data.get("input_contract", {})),
            output_contract=dict(data.get("output_contract", {})),
            loop_policy=dict(data.get("loop", {})),
            state_contract=dict(data.get("state", {})),
            harness=dict(data.get("harness", {})),
            optional_features=dict(data.get("optional_features", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "stage": self.stage,
            "skill": self.skill,
            "description": self.description,
            "previous_agent_id": self.previous_agent_id,
            "next_agent_id": self.next_agent_id,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "input_contract": self.input_contract,
            "output_contract": self.output_contract,
            "memory_dimensions": self.memory_dimensions,
            "max_revision_rounds": self.max_revision_rounds,
            "loop": self.loop_policy,
            "state": self.state_contract,
            "harness": self.harness,
            "optional_features": self.optional_features,
        }


@dataclass(frozen=True)
class Objection:
    id: str
    severity: Severity
    dimension: str
    message: str
    evidence: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "dimension": self.dimension,
            "message": self.message,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class ReviewReport:
    reviewer: str
    objections: list[Objection]

    @property
    def p0(self) -> list[Objection]:
        return [obj for obj in self.objections if obj.severity == "P0"]

    @property
    def p1(self) -> list[Objection]:
        return [obj for obj in self.objections if obj.severity == "P1"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewer": self.reviewer,
            "p0_count": len(self.p0),
            "p1_count": len(self.p1),
            "objections": [obj.to_dict() for obj in self.objections],
        }


@dataclass(frozen=True)
class StopDecision:
    can_stop: bool
    reason: str
    checked_at: str = field(default_factory=now_iso)
    llm_assessment: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "can_stop": self.can_stop,
            "reason": self.reason,
            "checked_at": self.checked_at,
        }
        if self.llm_assessment is not None:
            d["llm_assessment"] = self.llm_assessment
        return d
