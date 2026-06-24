from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol

Purpose = Literal["generate", "review", "stop_check"]


class SchemaValidationError(ValueError):
    """Raised when an LLM payload does not satisfy the expected JSON schema."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors) if errors else "schema validation failed")


@dataclass(frozen=True)
class LLMRequest:
    """A single call into the model layer.

    The harness only ever speaks to LLMClient through this request shape, so it
    stays agnostic to whether the model is a CLI subprocess, an in-session host
    model, or a recorded mock.
    """

    system: str
    user: str
    purpose: Purpose = "generate"
    schema: Optional[dict[str, Any]] = None
    schema_name: str = ""
    agent_id: str = ""
    round_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    """Result of a model call after JSON extraction and schema validation."""

    data: dict[str, Any]
    raw_text: str
    provider: str
    purpose: Purpose
    attempts: int = 1
    usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "purpose": self.purpose,
            "attempts": self.attempts,
            "usage": self.usage,
        }


class LLMAdapter(Protocol):
    """A concrete model channel: cli / inline / mock.

    An adapter only needs to turn a request into raw text. JSON extraction and
    schema validation are handled centrally by LLMClient, so every adapter
    benefits from the same guarantees.
    """

    kind: str

    def generate(self, request: LLMRequest) -> str:
        ...
