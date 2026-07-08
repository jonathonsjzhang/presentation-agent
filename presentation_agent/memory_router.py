from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from presentation_agent.io import read_json
from presentation_agent.learning import LearningEventStore
from presentation_agent.memory import MemoryStore


@dataclass(frozen=True)
class MemoryRoute:
    target_agent_id: str
    dimension: str
    reason: str
    confidence: float
    capability_owner: str = ""
    scope: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_agent_id": self.target_agent_id,
            "dimension": self.dimension,
            "reason": self.reason,
            "confidence": self.confidence,
            "capability_owner": self.capability_owner,
            "scope": self.scope,
        }


class MemoryRouter:
    """Route feedback to a Worker and the narrowest reusable capability owner."""

    ROUTES: list[tuple[str, str, tuple[str, ...], str]] = [
        ("manager", "调度", ("manager", "流程", "调度", "阶段", "顺序", "先给", "摘要", "确认", "返工", "回到上游", "以后都", "每次都", "验收", "放过", "通过"), "任务定义、调度或验收反馈"),
        ("analysis", "分析", ("发现", "finding", "证据强度", "数据分析", "反证", "替代解释", "置信度", "假设", "口径"), "分析发现、证据强度或解释反馈"),
        ("storyline", "结构", ("论点", "结论", "标题", "leadline", "故事线", "storyline", "结构", "塔尖", "主线", "executive summary"), "故事线、核心主张或结构反馈"),
        ("report", "报告内容", ("正文", "章节", "段落", "论证链", "来源标注", "引用", "报告", "claim", "caveat"), "报告正文、论证或来源反馈"),
        ("format", "可读性", ("版式", "格式", "ppt", "html", "docx", "视觉", "可读性", "排版", "模板"), "载体格式或可读性反馈"),
        ("qa_preparation", "风险", ("追问", "q&a", "qa", "风险", "回答", "质疑", "挑战问题"), "Q&A 或风险反馈"),
    ]

    def __init__(self, root: Path, data_root: Optional[Path] = None) -> None:
        self.root = root
        self.data_root = data_root or (root / "data")

    def route(
        self,
        *,
        text: str,
        current_agent_id: Optional[str] = None,
        explicit_dimension: Optional[str] = None,
        active_capabilities: Optional[list[str]] = None,
    ) -> MemoryRoute:
        normalized = text.lower()
        best: Optional[MemoryRoute] = None
        for agent_id, dimension, keywords, reason in self._route_rows(
            current_agent_id, active_capabilities
        ):
            hits = sum(1 for keyword in keywords if keyword.lower() in normalized)
            if not hits:
                continue
            candidate = MemoryRoute(
                target_agent_id=agent_id,
                dimension=explicit_dimension or dimension,
                reason=reason,
                confidence=min(0.95, 0.55 + hits * 0.15),
                **self._capability_scope(text, agent_id, active_capabilities),
            )
            if (
                best is None
                or candidate.confidence > best.confidence
                or (
                    candidate.confidence == best.confidence
                    and candidate.target_agent_id == current_agent_id
                )
            ):
                best = candidate
        if best:
            return best
        fallback = current_agent_id or "manager"
        return MemoryRoute(
            target_agent_id=fallback,
            dimension=explicit_dimension or "反馈",
            reason="未命中特定路由规则，回落到当前阶段或 manager",
            confidence=0.35,
            **self._capability_scope(text, fallback, active_capabilities),
        )

    def routes(
        self,
        *,
        text: str,
        current_agent_id: Optional[str] = None,
        explicit_dimension: Optional[str] = None,
        active_capabilities: Optional[list[str]] = None,
    ) -> list[MemoryRoute]:
        normalized = text.lower()
        matches: dict[str, MemoryRoute] = {}
        for agent_id, dimension, keywords, reason in self._route_rows(
            current_agent_id, active_capabilities
        ):
            hits = sum(1 for keyword in keywords if keyword.lower() in normalized)
            if not hits:
                continue
            route = MemoryRoute(
                target_agent_id=agent_id,
                dimension=explicit_dimension or dimension,
                reason=reason,
                confidence=min(0.95, 0.55 + hits * 0.15),
                **self._capability_scope(text, agent_id, active_capabilities),
            )
            previous = matches.get(agent_id)
            if previous is None or route.confidence > previous.confidence:
                matches[agent_id] = route
        if not matches:
            return [self.route(
                text=text,
                current_agent_id=current_agent_id,
                explicit_dimension=explicit_dimension,
                active_capabilities=active_capabilities,
            )]
        return sorted(matches.values(), key=lambda item: item.confidence, reverse=True)

    @classmethod
    def _route_rows(
        cls,
        current_agent_id: Optional[str],
        active_capabilities: Optional[list[str]],
    ) -> list[tuple[str, str, tuple[str, ...], str]]:
        """Return the single v0.3 owner table."""
        return cls.ROUTES

    def route_from_run_state(
        self,
        *,
        text: str,
        run_state_path: Optional[Path],
        explicit_dimension: Optional[str] = None,
    ) -> MemoryRoute:
        current_agent_id = None
        active_capabilities: list[str] = []
        if run_state_path and run_state_path.exists():
            state = read_json(run_state_path, default={})
            current_agent_id = state.get("agent_id")
            active_capabilities = list(state.get("selected_capabilities", []))
        return self.route(
            text=text,
            current_agent_id=current_agent_id,
            explicit_dimension=explicit_dimension,
            active_capabilities=active_capabilities,
        )

    def record_text_feedback(
        self,
        *,
        text: str,
        trigger_scene: str,
        run_state_path: Optional[Path] = None,
        explicit_dimension: Optional[str] = None,
        scope: str = "agent",
        source: str = "human-chat-auto-route",
    ) -> dict[str, Any]:
        route = self.route_from_run_state(
            text=text,
            run_state_path=run_state_path,
            explicit_dimension=explicit_dimension,
        )
        parsed = MemoryStore(
            self.root, route.target_agent_id, data_root=self.data_root
        ).record_text_feedback(
            text=text,
            trigger_scene=trigger_scene,
            source=source,
            dimension=route.dimension,
            scope=scope,
            owner=route.capability_owner,
            applies_to=route.scope,
        )
        self._record_route(route, parsed["log_id"], run_state_path, False)
        return {"route": route.to_dict(), "parsed": parsed}

    def record_text_feedback_multi(
        self,
        *,
        text: str,
        trigger_scene: str,
        run_state_path: Optional[Path] = None,
        explicit_dimension: Optional[str] = None,
        scope: str = "agent",
        source: str = "human-chat-auto-route",
    ) -> dict[str, Any]:
        current_agent_id = None
        active_capabilities: list[str] = []
        if run_state_path and run_state_path.exists():
            state = read_json(run_state_path, default={})
            current_agent_id = state.get("agent_id")
            active_capabilities = list(state.get("selected_capabilities", []))
        routes = self.routes(
            text=text,
            current_agent_id=current_agent_id,
            explicit_dimension=explicit_dimension,
            active_capabilities=active_capabilities,
        )
        records = []
        for route in routes:
            parsed = MemoryStore(
                self.root, route.target_agent_id, data_root=self.data_root
            ).record_text_feedback(
                text=text,
                trigger_scene=trigger_scene,
                source=source,
                dimension=route.dimension,
                scope=scope,
                owner=route.capability_owner,
                applies_to=route.scope,
            )
            self._record_route(route, parsed["log_id"], run_state_path, len(routes) > 1)
            records.append({"route": route.to_dict(), "parsed": parsed})
        return {
            "routes": [record["route"] for record in records],
            "records": records,
            "route": records[0]["route"],
            "parsed": records[0]["parsed"],
        }

    def _record_route(
        self,
        route: MemoryRoute,
        log_id: str,
        run_state_path: Optional[Path],
        multi_target: bool,
    ) -> None:
        LearningEventStore(self.root, data_root=self.data_root).append(
            event_type="memory_route",
            agent_id=route.target_agent_id,
            source="memory_router",
            payload={
                "route": route.to_dict(),
                "log_id": log_id,
                "run_state_path": str(run_state_path) if run_state_path else "",
                "multi_target": multi_target,
            },
        )

    @staticmethod
    def _capability_scope(
        text: str,
        agent_id: str,
        active_capabilities: Optional[list[str]],
    ) -> dict[str, Any]:
        lowered = text.lower()
        active = set(active_capabilities or [])
        catalogs = {
            "audience": {
                "board": ("董事会", "board"),
                "exec_office": ("总办", "办公会", "exec"),
                "strategy_lead": ("战略负责人", "strategy"),
                "business_team": ("业务团队", "业务负责人"),
                "external": ("外部", "公开分享", "external"),
            },
            "report_type": {
                "deep_dive": ("深度分析", "专题分析", "deep dive"),
                "business_progress": ("业务进展", "进展汇报", "progress"),
                "quick_sync": ("快速同步", "信息同步", "quick sync"),
            },
            "format": {
                "ppt": ("ppt", "幻灯片"),
                "document": ("docx", "word", "文档"),
                "html": ("html", "网页"),
            },
        }
        prefixes = {
            "audience": "audience.",
            "report_type": "report.",
            "format": "format.",
        }
        active_values: dict[str, str] = {}
        for dimension, prefix in prefixes.items():
            selected = [
                item.removeprefix(prefix)
                for item in active
                if item.startswith(prefix)
            ]
            if len(selected) == 1:
                active_values[dimension] = selected[0]
        mentioned: dict[str, str] = {}
        for dimension, values in catalogs.items():
            for value, keywords in values.items():
                if any(keyword in lowered for keyword in keywords):
                    mentioned[dimension] = value
                    break

        if agent_id == "format" and (
            mentioned.get("format") or active_values.get("format")
        ):
            owner = f"format.{mentioned.get('format') or active_values['format']}"
        elif "audience" in mentioned:
            owner = f"audience.{mentioned['audience']}"
        elif "report_type" in mentioned:
            owner = f"report.{mentioned['report_type']}"
        elif "format" in mentioned:
            owner = f"format.{mentioned['format']}"
        else:
            owner = f"core.{agent_id}"
        scoped_values = {
            "audience": "*",
            "report_type": "*",
            "format": "*",
        }
        scoped_values.update(mentioned)
        if owner.startswith("audience."):
            scoped_values["audience"] = owner.removeprefix("audience.")
        elif owner.startswith("report."):
            scoped_values["report_type"] = owner.removeprefix("report.")
        elif owner.startswith("format."):
            scoped_values["format"] = owner.removeprefix("format.")
        return {
            "capability_owner": owner,
            "scope": {
                "worker": [agent_id],
                "audience": [scoped_values["audience"]],
                "report_type": [scoped_values["report_type"]],
                "format": [scoped_values["format"]],
            },
        }
