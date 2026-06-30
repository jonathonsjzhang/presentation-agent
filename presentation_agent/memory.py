from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Optional

from presentation_agent.io import append_jsonl, read_json, write_json
from presentation_agent.learning import LearningEventStore
from presentation_agent.models import Objection, now_iso

# Defaults; overridden at runtime by configs/agents.json state_policy when present.
DEFAULT_DREAM_INTERVAL = 10
DEFAULT_PROMOTION_THRESHOLD = 3
DEFAULT_SOFT_LIMIT = 30


def _is_substantive(problem: str, dimension: str, change: str, reason: str) -> bool:
    """Return True if the feedback contains real content, not just TBD/empty placeholders.

    A non-substantive entry is one where ALL text fields are empty, whitespace-only,
    or obvious placeholders (TBD / TODO / N/A / —). Such entries still get logged
    (for auditability) but are skipped by memory promotion so they never waste
    dream/lint cycles or dilute the hot state.
    """
    fields = [problem, dimension, change, reason]
    placeholder = {"tbd", "todo", "n/a", "na", "—", "-", "..."}
    meaningful = any(
        f.strip() and f.strip().lower() not in placeholder for f in fields
    )
    return meaningful


@dataclass
class MemoryItem:
    id: str
    dimension: str
    trigger: str
    trigger_type: str
    suggestion: str
    case_anchors: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    hit_count: int = 0
    last_triggered: Optional[str] = None
    owner: str = ""
    applies_to: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryItem":
        return cls(
            id=data["id"],
            dimension=data["dimension"],
            trigger=data["trigger"],
            trigger_type=data.get("trigger_type", "keyword"),
            suggestion=data["suggestion"],
            case_anchors=list(data.get("case_anchors", [])),
            links=list(data.get("links", [])),
            hit_count=int(data.get("hit_count", 0)),
            last_triggered=data.get("last_triggered"),
            owner=str(data.get("owner", "")),
            applies_to={
                str(key): [str(value) for value in values]
                for key, values in data.get("applies_to", {}).items()
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dimension": self.dimension,
            "trigger": self.trigger,
            "trigger_type": self.trigger_type,
            "suggestion": self.suggestion,
            "case_anchors": self.case_anchors,
            "links": self.links,
            "hit_count": self.hit_count,
            "last_triggered": self.last_triggered,
            "owner": self.owner,
            "applies_to": self.applies_to,
        }

    def matches(self, text: str) -> bool:
        if self.trigger_type == "keyword":
            keywords = [part.strip() for part in self.trigger.replace("|", ",").split(",")]
            return any(keyword and keyword in text for keyword in keywords)
        return self.trigger in text

    def compatible_with(self, active_capabilities: Optional[list[str]]) -> bool:
        if not active_capabilities:
            return True
        active = set(active_capabilities)
        if self.owner and self.owner not in active:
            return False
        values = {
            "worker": {
                item.removeprefix("core.")
                for item in active
                if item.startswith("core.")
            },
            "audience": {
                item.removeprefix("audience.")
                for item in active
                if item.startswith("audience.")
            },
            "report_type": {
                item.removeprefix("report.")
                for item in active
                if item.startswith("report.")
            },
            "format": {
                item.removeprefix("format.")
                for item in active
                if item.startswith("format.")
            },
        }
        for dimension, allowed in self.applies_to.items():
            allowed_set = set(allowed)
            if "*" in allowed_set:
                continue
            if not values.get(dimension, set()).intersection(allowed_set):
                return False
        return True


class MemoryStore:
    """Cold learning-log plus hot memory for one agent."""

    def __init__(self, root: Path, agent_id: str, data_root: Optional[Path] = None) -> None:
        self.root = root
        self.agent_id = agent_id
        self.data_root = data_root or (root / "data")
        self.agent_dir = self.data_root / "agents" / agent_id
        self.memory_path = self.agent_dir / "memory.json"
        self.log_path = self.agent_dir / "learning_log.jsonl"

    # -- thresholds (config-driven) --------------------------------------

    def _state_policy(self) -> dict[str, Any]:
        config = read_json(self.root / "configs" / "agents.json", default={})
        return config.get("state_policy", {}) if isinstance(config, dict) else {}

    def promotion_threshold(self) -> int:
        return int(self._state_policy().get("rubric_promotion_threshold", DEFAULT_PROMOTION_THRESHOLD))

    def soft_limit(self) -> int:
        return int(self._state_policy().get("memory_soft_limit", DEFAULT_SOFT_LIMIT))

    def dream_interval(self) -> int:
        return int(self._state_policy().get("memory_dream_interval", DEFAULT_DREAM_INTERVAL))

    def load_items(self) -> list[MemoryItem]:
        data = read_json(self.memory_path, default={"items": []})
        items: list[MemoryItem] = []
        for raw in data.get("items", []):
            normalized = dict(raw)
            if not normalized.get("owner"):
                normalized["owner"] = f"core.{self.agent_id}"
            if not normalized.get("applies_to"):
                normalized["applies_to"] = self._default_scope()
            items.append(MemoryItem.from_dict(normalized))
        return items

    def save_items(self, items: list[MemoryItem]) -> None:
        write_json(self.memory_path, {"items": [item.to_dict() for item in items]})

    def generation_guidance(
        self,
        dimensions: list[str],
        limit: int = 8,
        active_capabilities: Optional[list[str]] = None,
    ) -> list[str]:
        suggestions: list[str] = []
        for item in self.load_items():
            if not item.compatible_with(active_capabilities):
                continue
            if item.dimension in dimensions and item.suggestion not in suggestions:
                suggestions.append(item.suggestion)
            if len(suggestions) >= limit:
                break
        return suggestions

    def scan(
        self, text: str, active_capabilities: Optional[list[str]] = None
    ) -> list[MemoryItem]:
        items = self.load_items()
        by_id = {item.id: item for item in items}
        matched: dict[str, MemoryItem] = {}
        for item in items:
            if not item.compatible_with(active_capabilities):
                continue
            if item.matches(text):
                matched[item.id] = item
                for linked_id in item.links:
                    if (
                        linked_id in by_id
                        and by_id[linked_id].compatible_with(active_capabilities)
                    ):
                        matched[linked_id] = by_id[linked_id]
        return list(matched.values())

    def record_objections(self, run_id: str, objections: list[Objection]) -> list[str]:
        log_ids: list[str] = []
        for objection in objections:
            log_ids.append(
                self.record_feedback(
                    scope="agent",
                    dimension=objection.dimension,
                    trigger_scene=f"review:{run_id}",
                    problem=objection.message,
                    reason=objection.evidence,
                    change=objection.suggestion,
                    source="reviewer",
                )
            )
        return log_ids

    def record_feedback(
        self,
        *,
        scope: str,
        dimension: str,
        trigger_scene: str,
        problem: str,
        reason: str,
        change: str,
        source: str = "human",
        owner: Optional[str] = None,
        applies_to: Optional[dict[str, list[str]]] = None,
    ) -> str:
        log_id = self._next_log_id()
        # Guard against empty / placeholder feedback writing dead entries
        # into the learning-log that would waste dream/lint cycles downstream.
        substantive = _is_substantive(problem, dimension, change, reason)
        entry = {
            "id": log_id,
            "date": now_iso(),
            "scope": scope,
            "agent_id": self.agent_id,
            "dimension": dimension,
            "trigger_scene": trigger_scene,
            "problem": problem,
            "reason": reason,
            "change": change,
            "source": source,
            "links": [],
            "substantive": substantive,
            "owner": owner or f"core.{self.agent_id}",
            "applies_to": applies_to or self._default_scope(),
        }
        append_jsonl(self.log_path, entry)
        LearningEventStore(self.root, data_root=self.data_root).append(
            event_type="feedback",
            agent_id=self.agent_id,
            source=source,
            payload={
                "log_id": log_id,
                "scope": scope,
                "dimension": dimension,
                "trigger_scene": trigger_scene,
                "problem": problem,
                "reason": reason,
                "change": change,
                "substantive": substantive,
                "owner": entry["owner"],
                "applies_to": entry["applies_to"],
            },
        )
        if substantive:
            self._upsert_memory(
                log_id,
                dimension,
                problem,
                change,
                owner=entry["owner"],
                applies_to=entry["applies_to"],
            )
        self._maybe_auto_dream()
        return log_id

    def record_text_feedback(
        self,
        *,
        text: str,
        trigger_scene: str,
        source: str = "human-chat",
        dimension: Optional[str] = None,
        scope: str = "agent",
        owner: Optional[str] = None,
        applies_to: Optional[dict[str, list[str]]] = None,
    ) -> dict[str, Any]:
        parsed = self._parse_feedback_text(text, dimension=dimension)
        log_id = self.record_feedback(
            scope=scope,
            dimension=parsed["dimension"],
            trigger_scene=trigger_scene,
            problem=parsed["problem"],
            reason=parsed["reason"],
            change=parsed["change"],
            source=source,
            owner=owner,
            applies_to=applies_to,
        )
        parsed["log_id"] = log_id
        return parsed

    def record_success(
        self,
        *,
        dimension: str,
        trigger_scene: str,
        pattern: str,
        why_it_worked: str = "",
        source: str = "success",
        scope: str = "agent",
    ) -> str:
        """Record a reusable successful pattern, not only a correction."""
        return self.record_feedback(
            scope=scope,
            dimension=dimension,
            trigger_scene=trigger_scene,
            problem=f"成功模式：{pattern}",
            reason=why_it_worked,
            change=f"后续同类场景优先复用：{pattern}",
            source=source,
        )

    def record_comparison(
        self,
        *,
        dimension: str,
        trigger_scene: str,
        before_ref: str,
        after_ref: str,
        change_summary: str,
        lesson: str,
        source: str = "comparison",
        scope: str = "agent",
    ) -> str:
        """Record lessons distilled from version comparisons such as v1 -> final."""
        return self.record_feedback(
            scope=scope,
            dimension=dimension,
            trigger_scene=trigger_scene,
            problem=f"版本对比 {before_ref} -> {after_ref}: {change_summary}",
            reason="来自材料版本演化的反思，而不是单次错误反馈",
            change=lesson,
            source=source,
        )

    def _next_log_id(self) -> str:
        if not self.log_path.exists():
            return "L-001"
        with self.log_path.open("r", encoding="utf-8") as f:
            count = sum(1 for _ in f)
        return f"L-{count + 1:03d}"

    def _next_memory_id(self, items: list[MemoryItem]) -> str:
        max_seq = 0
        for item in items:
            if not item.id.startswith("M-"):
                continue
            try:
                max_seq = max(max_seq, int(item.id.split("-", 1)[1]))
            except ValueError:
                continue
        return f"M-{max_seq + 1:03d}"

    def _upsert_memory(
        self,
        log_id: str,
        dimension: str,
        trigger: str,
        suggestion: str,
        *,
        owner: str,
        applies_to: dict[str, list[str]],
    ) -> None:
        if not suggestion.strip():
            return
        items = self.load_items()
        for item in items:
            same_dimension = item.dimension == dimension
            same_suggestion = item.suggestion.strip() == suggestion.strip()
            same_scope = item.owner == owner and item.applies_to == applies_to
            if same_dimension and same_suggestion and same_scope:
                item.case_anchors.append(log_id)
                item.hit_count += 1
                item.last_triggered = now_iso()
                self.save_items(items)
                return

        related = [item.id for item in items if item.dimension == dimension][:3]
        new_item = MemoryItem(
            id=self._next_memory_id(items),
            dimension=dimension,
            trigger=trigger[:80],
            trigger_type="keyword",
            suggestion=suggestion.strip(),
            case_anchors=[log_id],
            links=related,
            hit_count=1,
            last_triggered=now_iso(),
            owner=owner,
            applies_to=applies_to,
        )
        for item in items:
            if item.id in related and new_item.id not in item.links:
                item.links.append(new_item.id)
        items.append(new_item)
        self.save_items(items)

    def _default_scope(self) -> dict[str, list[str]]:
        return {
            "worker": [self.agent_id],
            "audience": ["*"],
            "report_type": ["*"],
            "format": ["*"],
        }

    def _maybe_auto_dream(self) -> None:
        interval = self.dream_interval()
        if interval <= 0:
            return
        log_count = self._log_count()
        over_limit = len(self.load_items()) > self.soft_limit()
        if over_limit or (log_count > 0 and log_count % interval == 0):
            self.dream(apply=True, reason="auto_after_feedback")

    def _log_count(self) -> int:
        if not self.log_path.exists():
            return 0
        with self.log_path.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def _parse_feedback_text(self, text: str, dimension: Optional[str] = None) -> dict[str, str]:
        clean = " ".join(text.strip().split())
        if not clean:
            raise ValueError("feedback text is empty")
        inferred_dimension = dimension or self._infer_dimension(clean)
        markers = ["应该", "需要", "改成", "下次", "以后", "不要", "避免", "补充", "修正", "调整为", "改为"]
        marker_positions = [(clean.find(marker), marker) for marker in markers if clean.find(marker) >= 0]
        if marker_positions:
            pos, _marker = min(marker_positions, key=lambda pair: pair[0])
            problem = clean[:pos].strip("，。；;:： ")
            change = clean[pos:].strip("，。；;:： ")
        else:
            problem = clean
            change = f"后续遇到同类场景时，按人工反馈修正：{clean}"
        if not problem:
            problem = clean
        reason = ""
        reason_markers = ["因为", "否则", "不然", "原因是"]
        for marker in reason_markers:
            idx = clean.find(marker)
            if idx >= 0:
                reason = clean[idx:].strip("，。；;:： ")
                break
        return {
            "dimension": inferred_dimension,
            "problem": problem,
            "reason": reason,
            "change": change,
        }

    @staticmethod
    def _infer_dimension(text: str) -> str:
        catalog = [
            ("标题|leadline|结论|headline", "Leadline"),
            ("结构|storyline|逻辑|顺序|MECE|金字塔", "结构"),
            ("证据|数据|论据|口径|来源", "证据"),
            ("图表|可视化|chart|表格", "图表"),
            ("措辞|表达|话术|语气|绝对化", "表达"),
            ("版式|排版|格式|字号|颜色|PPT", "版式"),
            ("受众|董事会|战略|业务|外部", "受众适配"),
            ("行动|action|决策|资源|授权", "Action"),
        ]
        for pattern, dimension in catalog:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return dimension
        return "人工反馈"

    # -- dreaming: periodic memory consolidation ------------------------

    def dream(self, *, apply: bool = False, reason: str = "manual") -> dict[str, Any]:
        before = self.load_items()
        lint_report = self.lint()
        conflicts = self._potential_conflicts(before)
        summaries = self._dimension_summaries(before)
        maintenance: dict[str, Any] = {"applied": False}
        after = before
        if apply:
            maintenance = {"applied": True, **self.apply_lint()}
            after = self.load_items()
            summaries = self._dimension_summaries(after)

        report = {
            "agent_id": self.agent_id,
            "created_at": now_iso(),
            "reason": reason,
            "applied": apply,
            "before_count": len(before),
            "after_count": len(after),
            "lint": lint_report,
            "potential_conflicts": conflicts,
            "dimension_summaries": summaries,
            "maintenance": maintenance,
        }
        LearningEventStore(self.root).append(
            event_type="memory_dream",
            agent_id=self.agent_id,
            source="memory-store",
            payload={
                "reason": reason,
                "applied": apply,
                "before_count": len(before),
                "after_count": len(after),
                "conflict_count": len(conflicts),
            },
        )
        dream_dir = self.agent_dir / "memory_dreams"
        stamp = report["created_at"].replace(":", "").replace("+", "Z")
        report_path = dream_dir / f"dream_{stamp}.json"
        write_json(report_path, report)
        summary_path = self.agent_dir / "memory_summary.json"
        write_json(
            summary_path,
            {
                "agent_id": self.agent_id,
                "updated_at": report["created_at"],
                "item_count": len(after),
                "dimension_summaries": summaries,
                "potential_conflicts": conflicts,
                "latest_dream_report": str(report_path),
            },
        )
        report["report_path"] = str(report_path)
        report["summary_path"] = str(summary_path)
        return report

    def _dimension_summaries(self, items: list[MemoryItem]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[MemoryItem]] = {}
        for item in items:
            grouped.setdefault(item.dimension, []).append(item)
        summaries: dict[str, list[dict[str, Any]]] = {}
        for dimension, group in grouped.items():
            ranked = sorted(group, key=lambda item: (-item.hit_count, item.last_triggered or "", item.id))
            summaries[dimension] = [
                {
                    "memory_id": item.id,
                    "suggestion": item.suggestion,
                    "trigger": item.trigger,
                    "hit_count": item.hit_count,
                    "case_count": len(item.case_anchors),
                }
                for item in ranked[:8]
            ]
        return summaries

    def _potential_conflicts(self, items: list[MemoryItem]) -> list[dict[str, Any]]:
        by_key: dict[tuple[str, str], list[MemoryItem]] = {}
        for item in items:
            key = (item.dimension, self._normalize_memory_text(item.trigger))
            by_key.setdefault(key, []).append(item)
        conflicts: list[dict[str, Any]] = []
        for (dimension, trigger), group in by_key.items():
            suggestions = {self._normalize_memory_text(item.suggestion) for item in group}
            if len(group) > 1 and len(suggestions) > 1:
                conflicts.append(
                    {
                        "dimension": dimension,
                        "trigger": trigger,
                        "items": [item.id for item in group],
                        "suggestions": [item.suggestion for item in group],
                    }
                )
        return conflicts

    @staticmethod
    def _normalize_memory_text(text: str) -> str:
        return re.sub(r"\s+", "", text.strip().lower())

    # -- promotion: hot memory -> durable rubric -------------------------

    def promotion_candidates(self, threshold: Optional[int] = None) -> list[MemoryItem]:
        """Memory items hit often enough to deserve becoming a rubric.

        A high hit_count means this lesson keeps recurring across runs, so it
        should graduate from per-run hot memory into the agent's durable
        rubrics.json. Returns candidates only; applying is a separate, human-
        gated step (see apply_promotion).
        """
        limit = threshold if threshold is not None else self.promotion_threshold()
        return [item for item in self.load_items() if item.hit_count >= limit]

    def apply_promotion(self, item_ids: list[str]) -> dict[str, Any]:
        """Promote named memory items into their capability owner's rubrics.

        Human-in-the-loop by design: the caller decides which candidate ids to
        confirm. Each promoted item is appended as a new P1 rubric and removed
        from hot memory. Returns a report of what happened.
        """
        items = self.load_items()
        by_id = {item.id: item for item in items}
        promoted: list[str] = []
        skipped: list[str] = []
        skipped_scoped: list[str] = []
        paths: dict[str, str] = {}

        for item_id in item_ids:
            item = by_id.get(item_id)
            if item is None:
                skipped.append(item_id)
                continue
            if self._is_cross_scoped(item):
                skipped_scoped.append(item_id)
                continue
            rubrics_path = self._rubrics_path_for_owner(item.owner)
            rubrics_doc = read_json(rubrics_path, default={"rubrics": []})
            rubrics = list(rubrics_doc.get("rubrics", []))
            existing_ids = {
                row.get("id") for row in rubrics if isinstance(row, dict)
            }
            seq = self._next_promoted_rubric_seq(existing_ids)
            rubric_id = f"MEM-P1-{seq:03d}"
            rubric = {
                "id": rubric_id,
                "severity": "P1",
                "dimension": item.dimension,
                "criterion": item.suggestion,
                "check": f"产物不应再触发历史问题：{item.trigger}",
                "fail_examples": [],
                "fix": item.suggestion,
                "source": {
                    "promoted_from_memory": item.id,
                    "hit_count": item.hit_count,
                    "owner": item.owner,
                    "scope": item.applies_to,
                },
            }
            if not item.owner.startswith("core."):
                rubric["applies_to"] = [self.agent_id]
            rubrics.append(rubric)
            rubrics_doc["rubrics"] = rubrics
            write_json(rubrics_path, rubrics_doc)
            paths[item.id] = str(rubrics_path)
            promoted.append(item_id)

        if promoted:
            remaining = [it for it in items if it.id not in set(promoted)]
            self.save_items(remaining)

        unique_paths = list(dict.fromkeys(paths.values()))
        return {
            "promoted": promoted,
            "skipped": skipped,
            "skipped_scoped": skipped_scoped,
            "rubrics_path": unique_paths[0] if len(unique_paths) == 1 else "",
            "rubrics_paths": paths,
        }

    def promotion_target(self, item: MemoryItem) -> str:
        return str(self._rubrics_path_for_owner(item.owner))

    def _rubrics_path_for_owner(self, owner: str) -> Path:
        if owner.startswith("core."):
            return self.root / "skills" / owner.removeprefix("core.") / "rubrics.json"
        if owner.startswith("audience."):
            return self.root / "skills" / "atomic" / "audience" / owner.removeprefix("audience.") / "rubrics.json"
        if owner.startswith("report."):
            return self.root / "skills" / "atomic" / "report_type" / owner.removeprefix("report.") / "rubrics.json"
        if owner.startswith("format."):
            return self.root / "skills" / "atomic" / "format" / owner.removeprefix("format.") / "rubrics.json"
        raise ValueError(f"unsupported memory owner: {owner}")

    def _is_cross_scoped(self, item: MemoryItem) -> bool:
        owner_dimension = ""
        owner_value = ""
        if "." in item.owner:
            owner_dimension, owner_value = item.owner.split(".", 1)
        dimension_map = {
            "audience": "audience",
            "report": "report_type",
            "format": "format",
        }
        allowed_specific = {"worker"}
        if owner_dimension in dimension_map:
            allowed_specific.add(dimension_map[owner_dimension])
        for dimension, values in item.applies_to.items():
            specific = {value for value in values if value != "*"}
            if not specific:
                continue
            if dimension not in allowed_specific:
                return True
            if dimension == "worker" and specific != {self.agent_id}:
                return True
            if dimension != "worker" and owner_value and specific != {owner_value}:
                return True
        return False

    def _next_promoted_rubric_seq(self, existing_ids: set) -> int:
        seq = 1
        for rid in existing_ids:
            if isinstance(rid, str) and rid.startswith("MEM-P1-"):
                try:
                    seq = max(seq, int(rid.rsplit("-", 1)[1]) + 1)
                except ValueError:
                    continue
        return seq

    # -- lint: keep hot memory from bloating -----------------------------

    def lint(self, soft_limit: Optional[int] = None) -> dict[str, Any]:
        """Diagnose hot-memory health without changing anything.

        Reports three issues the apply step can fix:
          - over_limit: items beyond the soft limit, ranked for eviction
            (never-triggered and lowest hit_count first, then oldest).
          - orphan_links: links pointing at ids that no longer exist.
          - duplicates: same dimension + suggestion appearing more than once.
        """
        limit = soft_limit if soft_limit is not None else self.soft_limit()
        items = self.load_items()
        ids = {item.id for item in items}

        ranked = sorted(items, key=lambda it: (it.hit_count, it.last_triggered or ""))
        over_limit = [it.id for it in ranked[: max(0, len(items) - limit)]]

        orphan_links = {
            item.id: [lid for lid in item.links if lid not in ids]
            for item in items
            if any(lid not in ids for lid in item.links)
        }

        seen: dict[tuple, str] = {}
        duplicates: list[dict[str, str]] = []
        for item in items:
            key = (item.dimension, item.suggestion.strip())
            if key in seen:
                duplicates.append({"keep": seen[key], "duplicate": item.id})
            else:
                seen[key] = item.id

        return {
            "total": len(items),
            "soft_limit": limit,
            "over_limit": over_limit,
            "orphan_links": orphan_links,
            "duplicates": duplicates,
        }

    def apply_lint(self, soft_limit: Optional[int] = None) -> dict[str, Any]:
        """Execute the lint plan: evict over-limit items, drop orphan links,
        merge duplicates (keep the higher hit_count, fold case_anchors)."""
        report = self.lint(soft_limit=soft_limit)
        items = self.load_items()
        by_id = {item.id: item for item in items}

        # merge duplicates into the kept item
        drop_ids: set[str] = set()
        for pair in report["duplicates"]:
            keep, dup = by_id.get(pair["keep"]), by_id.get(pair["duplicate"])
            if not keep or not dup:
                continue
            if dup.hit_count > keep.hit_count:
                keep, dup = dup, keep
            keep.hit_count += dup.hit_count
            keep.case_anchors = list(dict.fromkeys(keep.case_anchors + dup.case_anchors))
            drop_ids.add(dup.id)

        drop_ids.update(report["over_limit"])

        survivors = [it for it in items if it.id not in drop_ids]
        survivor_ids = {it.id for it in survivors}
        for item in survivors:
            item.links = [lid for lid in item.links if lid in survivor_ids]

        self.save_items(survivors)
        return {
            "evicted": sorted(drop_ids),
            "remaining": len(survivors),
            "orphan_links_cleared": report["orphan_links"],
        }
