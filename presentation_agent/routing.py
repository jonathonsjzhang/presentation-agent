from __future__ import annotations

from typing import Any

from presentation_agent.memory_retrieval import RetrievedMemory
from presentation_agent.models import AgentSpec


def build_routing_policy(
    *,
    spec: AgentSpec,
    input_data: dict[str, Any],
    global_state: dict[str, Any],
    retrieved_memory: list[RetrievedMemory],
) -> dict[str, Any]:
    """Convert retrieved memory into lightweight execution knobs.

    Routing is intentionally small: it changes attention, checklist emphasis,
    and review strictness. It does not auto-edit skills or autonomously jump
    stages, which keeps the loop understandable.
    """
    text = " ".join(
        str(v)
        for v in [
            input_data.get("audience"),
            input_data.get("report_type"),
            input_data.get("output_format", input_data.get("material_format")),
            global_state.get("audience_profile"),
            global_state.get("target_action"),
            spec.name,
        ]
        if v not in (None, "", [], {})
    )
    high_stakes = any(keyword in text for keyword in ["董事会", "总办", "战略负责人", "集团", "CEO", "CFO"])
    dimensions = [row.item.dimension for row in retrieved_memory]
    emphasis = list(dict.fromkeys(dimensions[:4]))
    review_strictness = "heightened" if high_stakes or len(retrieved_memory) >= 5 else "standard"

    return {
        "version": "routing_policy.v1",
        "agent_id": spec.id,
        "review_strictness": review_strictness,
        "checklist_focus": emphasis,
        "memory_budget": {
            "max_prompt_items": len(retrieved_memory),
            "principle": "只注入最相关的短经验，避免长 memory 抢占注意力",
        },
        "actions": _actions_for(spec, high_stakes, emphasis),
    }


def _actions_for(spec: AgentSpec, high_stakes: bool, emphasis: list[str]) -> list[str]:
    actions: list[str] = []
    if high_stakes:
        actions.append("面向高层汇报，强化结论先行和决策含义，但不把未成熟判断强行闭环为 action")
    if "Leadline" in emphasis or "Wording" in emphasis:
        actions.append("标题和关键句需优先通过结论化/高层化检查")
    if "证据" in emphasis or "图表" in emphasis:
        actions.append("所有关键判断必须保留证据口径和来源说明")
    if spec.id == "storyline_design":
        actions.append("执行结构化标题连读测试，并检查一页一问一 leadline、points 共同支撑该判断")
    if spec.id == "format":
        actions.append("优先检查可读性、视觉层级和载体适配")
    return actions[:5]
