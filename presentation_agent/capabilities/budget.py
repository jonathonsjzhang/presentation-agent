from __future__ import annotations

from typing import Any


def estimate_tokens(value: Any) -> int:
    """Cheap, deterministic prompt-size estimate suitable for regressions."""
    text = value if isinstance(value, str) else str(value)
    return (len(text) + 3) // 4


def prompt_budget(*, instructions: str, rubrics: list[Any], schemas: dict[str, Any]) -> dict[str, int]:
    return {
        "instruction_chars": len(instructions),
        "instruction_tokens_estimate": estimate_tokens(instructions),
        "rubric_chars": len(str(rubrics)),
        "rubric_tokens_estimate": estimate_tokens(rubrics),
        "schema_chars": len(str(schemas)),
        "schema_tokens_estimate": estimate_tokens(schemas),
    }
