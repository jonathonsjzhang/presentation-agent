from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from presentation_agent.io import flatten_text
from presentation_agent.memory import MemoryItem, MemoryStore
from presentation_agent.models import AgentSpec


@dataclass(frozen=True)
class RetrievedMemory:
    item: MemoryItem
    score: float
    reason: str

    def to_prompt_line(self) -> str:
        return f"[{self.item.id}/{self.item.dimension}] {self.item.suggestion}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.item.id,
            "dimension": self.item.dimension,
            "suggestion": self.item.suggestion,
            "trigger": self.item.trigger,
            "hit_count": self.item.hit_count,
            "owner": self.item.owner,
            "applies_to": self.item.applies_to,
            "score": round(self.score, 3),
            "reason": self.reason,
        }


class MemoryRetriever:
    """Small deterministic retrieval layer for attention-safe memory injection."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def retrieve(
        self,
        *,
        spec: AgentSpec,
        input_data: dict[str, Any],
        global_state: dict[str, Any],
        dimensions: list[str],
        limit: int = 6,
        active_capabilities: list[str] | None = None,
    ) -> list[RetrievedMemory]:
        text = "\n".join(
            [
                flatten_text(input_data),
                flatten_text(global_state),
                spec.name,
                spec.description,
                " ".join(spec.rubrics),
            ]
        )
        context_tokens = self._tokens(text)
        preferred = set(dimensions)

        scored: list[RetrievedMemory] = []
        for item in self.store.load_items():
            if not item.compatible_with(active_capabilities):
                continue
            score = 0.0
            reasons: list[str] = []
            if item.dimension in preferred:
                score += 3.0
                reasons.append("dimension")
            trigger_hits = self._keyword_hits(item.trigger, text, context_tokens)
            if trigger_hits:
                score += 1.4 * trigger_hits
                reasons.append("trigger")
            suggestion_hits = self._keyword_hits(item.suggestion, text, context_tokens)
            if suggestion_hits:
                score += 0.7 * suggestion_hits
                reasons.append("suggestion")
            if item.hit_count:
                score += min(item.hit_count, 5) * 0.25
                reasons.append("hit_count")
            if not score:
                continue
            scored.append(RetrievedMemory(item=item, score=score, reason="+".join(reasons)))

        scored.sort(key=lambda row: (-row.score, -row.item.hit_count, row.item.id))
        return scored[:limit]

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]{2,}", text)
            if token.strip()
        }

    def _keyword_hits(self, value: str, text: str, tokens: set[str]) -> int:
        hits = 0
        for part in re.split(r"[,，|；;、\s]+", value or ""):
            keyword = part.strip()
            if len(keyword) < 2:
                continue
            if keyword in text or keyword.lower() in tokens:
                hits += 1
        return hits
