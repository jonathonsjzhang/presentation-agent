from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from presentation_agent.io import read_json
from presentation_agent.llm.adapters import CLIAdapter, InlineAdapter, MockAdapter
from presentation_agent.llm.client import LLMClient
from presentation_agent.llm.types import LLMAdapter, Purpose

_DEFAULT_CONFIG: dict[str, Any] = {
    "default_provider": "mock",
    "providers": {
        "mock": {"kind": "mock"},
    },
    "purpose_overrides": {},
}


def load_llm_config(root: Path) -> dict[str, Any]:
    """Load configs/llm.json, falling back to a mock-only default.

    The default keeps A1/A2 runnable with zero external dependency: the loop can
    be exercised end to end before any real model is wired in.
    """
    config = read_json(root / "configs" / "llm.json", default=_DEFAULT_CONFIG)
    config.setdefault("default_provider", "mock")
    config.setdefault("providers", {"mock": {"kind": "mock"}})
    config.setdefault("purpose_overrides", {})
    return config


def build_adapter(
    spec: dict[str, Any],
    root: Path,
    handoff_path: Optional[Path] = None,
) -> LLMAdapter:
    kind = spec.get("kind", "mock")
    if kind == "mock":
        fixtures = spec.get("fixtures_dir")
        fixtures_dir = (root / fixtures) if fixtures else None
        return MockAdapter(fixtures_dir=fixtures_dir)
    if kind == "cli":
        return CLIAdapter(
            command=spec["command"],
            args=spec.get("args", []),
            timeout=int(spec.get("timeout", 180)),
            cwd=spec.get("cwd"),
            stdout_format=spec.get("stdout_format", "text"),
            result_field=spec.get("result_field", "result"),
        )
    if kind == "inline":
        path = handoff_path or (Path(spec["handoff_path"]) if spec.get("handoff_path") else None)
        return InlineAdapter(handoff_path=path)
    raise ValueError(f"unknown llm provider kind: {kind!r}")


def build_llm_client(
    root: Path,
    purpose: Purpose = "generate",
    provider_override: Optional[str] = None,
    handoff_path: Optional[Path] = None,
) -> LLMClient:
    """Resolve a provider for a purpose and return a ready LLMClient.

    Resolution: explicit override > purpose_overrides[purpose] > default_provider.
    """
    config = load_llm_config(root)
    provider = (
        provider_override
        or config.get("purpose_overrides", {}).get(purpose)
        or config.get("default_provider", "mock")
    )
    providers = config.get("providers", {})
    if provider not in providers:
        raise ValueError(
            f"provider {provider!r} not defined in configs/llm.json (have: {sorted(providers)})"
        )
    adapter = build_adapter(providers[provider], root, handoff_path=handoff_path)
    max_retries = int(config.get("max_retries", 1))
    return LLMClient(adapter=adapter, max_retries=max_retries)
