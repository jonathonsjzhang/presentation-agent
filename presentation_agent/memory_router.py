from __future__ import annotations

from dataclasses import dataclass
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_agent_id": self.target_agent_id,
            "dimension": self.dimension,
            "reason": self.reason,
            "confidence": self.confidence,
        }


class MemoryRouter:
    """Route human feedback to manager or the relevant specialist agent."""

    ROUTES: list[tuple[str, str, tuple[str, ...], str]] = [
        ("manager", "调度", ("流程", "调度", "阶段", "顺序", "先给", "摘要", "确认", "返工", "回到上游", "以后都", "每次都"), "流程或人审偏好反馈"),
        ("argument_synthesis", "结论", ("论点", "结论", "action", "行动", "证据强度", "判断", "假设", "塔尖"), "核心论点或证据反馈"),
        ("storyline_design", "结构", ("标题", "leadline", "故事线", "storyline", "结构", "一页一问", "so what", "主线"), "故事线或标题反馈"),
        ("page_filling", "页内叙事", ("页面", "单页", "图表", "信息密度", "来源标注", "口径", "dummy", "chart"), "单页内容或图表反馈"),
        ("format", "可读性", ("版式", "格式", "PPT", "html", "docx", "视觉", "可读性", "排版", "模板"), "载体格式或可读性反馈"),
        ("qa_preparation", "风险", ("追问", "Q&A", "QA", "风险", "回答", "质疑", "挑战问题"), "Q&A 或风险反馈"),
        ("speaker_script", "表达", ("逐字稿", "话术", "演讲", "节奏", "口播", "讲稿", "表达"), "讲稿或表达反馈"),
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
    ) -> MemoryRoute:
        normalized = text.lower()
        best: Optional[MemoryRoute] = None
        for agent_id, dimension, keywords, reason in self.ROUTES:
            hits = sum(1 for keyword in keywords if keyword.lower() in normalized or keyword in text)
            if not hits:
                continue
            confidence = min(0.95, 0.55 + hits * 0.15)
            candidate = MemoryRoute(
                target_agent_id=agent_id,
                dimension=explicit_dimension or dimension,
                reason=reason,
                confidence=confidence,
            )
            if best is None or candidate.confidence > best.confidence:
                best = candidate
        if best:
            return best
        return MemoryRoute(
            target_agent_id=current_agent_id or "manager",
            dimension=explicit_dimension or "反馈",
            reason="未命中特定路由规则，回落到当前阶段或 manager",
            confidence=0.35,
        )

    def route_from_run_state(
        self,
        *,
        text: str,
        run_state_path: Optional[Path],
        explicit_dimension: Optional[str] = None,
    ) -> MemoryRoute:
        current_agent_id = None
        if run_state_path and run_state_path.exists():
            state = read_json(run_state_path, default={})
            current_agent_id = state.get("agent_id")
        return self.route(
            text=text,
            current_agent_id=current_agent_id,
            explicit_dimension=explicit_dimension,
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
        parsed = MemoryStore(self.root, route.target_agent_id, data_root=self.data_root).record_text_feedback(
            text=text,
            trigger_scene=trigger_scene,
            source=source,
            dimension=route.dimension,
            scope=scope,
        )
        LearningEventStore(self.root, data_root=self.data_root).append(
            event_type="memory_route",
            agent_id=route.target_agent_id,
            source="memory_router",
            payload={
                "route": route.to_dict(),
                "log_id": parsed["log_id"],
                "run_state_path": str(run_state_path) if run_state_path else "",
            },
        )
        return {
            "route": route.to_dict(),
            "parsed": parsed,
        }
