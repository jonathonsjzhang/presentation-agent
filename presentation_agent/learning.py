from __future__ import annotations

from pathlib import Path
import difflib
import json
import re
from typing import Any, Optional

from presentation_agent.io import append_jsonl, flatten_text, read_json
from presentation_agent.models import now_iso


class LearningEventStore:
    """Append-only learning events across agents.

    Agent-local ``learning_log.jsonl`` stays optimized for hot-memory upkeep.
    This project-level event stream keeps the broader facts: feedback, success
    patterns, version comparisons, dreaming, retrieval, and routing decisions.
    Most events should never enter prompts directly.
    """

    def __init__(self, root: Path, data_root: Optional[Path] = None) -> None:
        self.root = root
        self.data_root = data_root or (root / "data")
        self.path = self.data_root / "learning" / "events.jsonl"

    def append(
        self,
        *,
        event_type: str,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        source: str = "harness",
        payload: Optional[dict[str, Any]] = None,
    ) -> str:
        event_id = self._next_id()
        append_jsonl(
            self.path,
            {
                "id": event_id,
                "date": now_iso(),
                "event_type": event_type,
                "agent_id": agent_id,
                "run_id": run_id,
                "source": source,
                "payload": payload or {},
            },
        )
        return event_id

    def _next_id(self) -> str:
        if not self.path.exists():
            return "E-001"
        with self.path.open("r", encoding="utf-8") as f:
            count = sum(1 for line in f if line.strip())
        return f"E-{count + 1:03d}"


def compare_material_versions(before_path: Path, after_path: Path) -> dict[str, Any]:
    """Create a compact deterministic comparison summary for two materials."""
    before_text = _read_material_text(before_path)
    after_text = _read_material_text(after_path)
    before_lines = [line.strip() for line in before_text.splitlines() if line.strip()]
    after_lines = [line.strip() for line in after_text.splitlines() if line.strip()]
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    inserted: list[str] = []
    deleted: list[str] = []
    replaced: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            inserted.extend(after_lines[j1:j2])
        elif tag == "delete":
            deleted.extend(before_lines[i1:i2])
        elif tag == "replace":
            replaced.append(
                {
                    "before": " / ".join(before_lines[i1:i2])[:260],
                    "after": " / ".join(after_lines[j1:j2])[:260],
                }
            )
    return {
        "before_path": str(before_path),
        "after_path": str(after_path),
        "before_line_count": len(before_lines),
        "after_line_count": len(after_lines),
        "inserted_samples": inserted[:8],
        "deleted_samples": deleted[:8],
        "replaced_samples": replaced[:8],
        "change_tags": _infer_change_tags(inserted + [r["after"] for r in replaced]),
    }


def _read_material_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.dumps(read_json(path), ensure_ascii=False, indent=2)
    if suffix == ".docx":
        from presentation_agent.connectors.docx import extract_docx_paragraphs

        return "\n".join(extract_docx_paragraphs(path))
    if suffix in {".md", ".txt", ".html", ".csv"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    return flatten_text(path.read_text(encoding="utf-8", errors="ignore"))


def _infer_change_tags(samples: list[str]) -> list[str]:
    text = "\n".join(samples)
    tags: list[str] = []
    catalog = [
        ("标题|headline|title", "title_rewrite"),
        ("so what|所以|因此|意味着", "so_what"),
        ("行动|决策|资源|授权|action", "action_closure"),
        ("数据|口径|来源|证据", "evidence"),
        ("图表|趋势|分布|占比", "charting"),
        ("战略|高层|董事会|总办", "executive_framing"),
    ]
    for pattern, tag in catalog:
        if re.search(pattern, text, flags=re.IGNORECASE):
            tags.append(tag)
    return tags or ["content_revision"]
