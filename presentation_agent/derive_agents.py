"""Derive per-terminal sub-agent definition files from a single source of truth.

``configs/agents.json`` is the single source of truth for the pipeline. This
module projects each of its stage agents into the three host dialects so the
three-layer architecture (L1 Manager -> L2 worker -> L3 reviewer) is *declared*
identically everywhere, while each host expresses capability bounds in its own
way.

For every stage agent we emit two definitions:

- a **worker** (writable, content producer)
- a **reviewer** (read-only checker; its read-only bound is what gives the
  maker-checker isolation a physical guarantee, not a convention)

Dialect mapping (terminal-agnostic contract -> per-host expression):

============  =================  =====================  =========================
role          WorkBuddy          Claude Code            Codex
============  =================  =====================  =========================
worker        general-purpose    tools: Read,Write,Bash worker (full sandbox)
reviewer      Explore            tools: Read (no write) --sandbox read-only
============  =================  =====================  =========================

Important: this generator only emits **stage-level sub-agents**. It never
touches the hand-written **orchestrator** entries (``report-builder``) that
already live in ``.claude/agents`` / ``.codex/prompts`` — those are the L1
Manager surface and are out of scope here. Generated files carry an
``AUTO-GENERATED`` banner and live under dedicated paths so they can be
regenerated safely.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from presentation_agent.io import read_json

AUTOGEN_BANNER = "AUTO-GENERATED from configs/agents.json — do not edit by hand."

# Terminal-agnostic role -> per-host capability expression.
DIALECT = {
    "workbuddy": {
        "worker": {"subagent_type": "general-purpose", "read_only": False},
        "reviewer": {"subagent_type": "Explore", "read_only": True},
    },
    "claude": {
        # Claude Code agent frontmatter `tools:` is an allow-list.
        "worker": {"tools": "Read, Write, Edit, Bash", "read_only": False},
        "reviewer": {"tools": "Read, Grep, Glob", "read_only": True},
    },
    "codex": {
        # Codex expresses read-only via sandbox mode.
        "worker": {"sandbox": "workspace-write", "read_only": False},
        "reviewer": {"sandbox": "read-only", "read_only": True},
    },
}

# Output roots per host (relative to repo root). Stage sub-agents go under a
# dedicated subdir so they never collide with hand-written orchestrators.
OUTPUT_ROOTS = {
    "workbuddy": Path("agents.workbuddy"),
    "claude": Path(".claude/agents/pipeline"),
    "codex": Path(".codex/agents"),
}


@dataclass
class DerivedFile:
    host: str
    role: str
    agent_id: str
    path: Path
    content: str


def _stage_agents(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the pipeline stage agents (those listed in pipeline.stages).

    The legacy ``task_positioning`` agent is included only if it is an active
    stage; otherwise stages drive the projection so we stay in lockstep with the
    real pipeline.
    """

    active = config.get("pipeline", {}).get("stages", [])
    by_id = {a.get("id"): a for a in config.get("agents", [])}
    return [by_id[s] for s in active if s in by_id]


def _yaml_frontmatter(fields: dict[str, str]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        # description may be multi-line; fold it for readability.
        if "\n" in value:
            lines.append(f"{key}: >-")
            for chunk in value.split("\n"):
                lines.append(f"  {chunk.strip()}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def _body(agent: dict[str, Any], role: str) -> str:
    name = agent.get("name", agent["id"])
    skill = agent.get("skill", agent["id"])
    out_schema = agent.get("output_schema", "")
    rubrics = agent.get("rubrics", [])
    if role == "worker":
        intro = (
            f"你是被派生的、拥有独立上下文的 **Worker sub-agent**，"
            f"扮演汇报流水线中「{name}」环节。你没有主对话历史——"
            f"全部任务输入都在 harness 交给你的指令包与 input 文件里。"
        )
        duty = (
            "读取 harness 准备的指令包(内嵌完整 SKILL.md 角色/工作流/输出契约)"
            "与 input.json，严格按 Output Contract 产出一个合法 JSON 对象，"
            f"写回 handoff 的 output 文件。output schema: `{out_schema}`。"
        )
    else:
        intro = (
            f"你是被派生的、拥有独立干净上下文的 **只读 Reviewer sub-agent**"
            f"(maker-checker 中的 checker)，审查「{name}」环节的产物。"
            f"你与产出该产物的 worker 完全隔离，**只读不改产物**。"
        )
        duty = (
            "读取 review 指令包(内嵌 rubrics 与被审产物)，逐条对照 P0/P1，"
            '按精确格式写回 `{"objections":[{rubric_id,severity,dimension,'
            'message,evidence,suggestion}]}`(无命中则空数组)到 review 输出文件。'
        )
    rubric_lines = "\n".join(f"- {r}" for r in rubrics) or "- (见指令包内 rubrics)"
    return (
        f"<!-- {AUTOGEN_BANNER} -->\n\n"
        f"{intro}\n\n"
        f"## 职责\n\n{duty}\n\n"
        f"## skill 包\n\n`skills/{skill}`\n\n"
        f"## 环节红线(rubrics)\n\n{rubric_lines}\n\n"
        f"## 不变量\n\n"
        f"- 派生深度 = 1：你不得再下派任何子 agent。\n"
        f"- 写作用域限本 task_dir；只写指定的 handoff 输出文件。\n"
    )


def _render_claude(agent: dict[str, Any], role: str) -> str:
    cap = DIALECT["claude"][role]
    suffix = "" if role == "worker" else "-reviewer"
    name = f"{agent['id']}{suffix}"
    desc = (
        f"[{AUTOGEN_BANNER}] 汇报流水线「{agent.get('name', agent['id'])}」"
        f"环节的{'内容生产 worker' if role == 'worker' else '只读审查 reviewer'}。"
    )
    fm = _yaml_frontmatter(
        {"name": name, "description": desc, "tools": cap["tools"]}
    )
    return f"{fm}\n\n{_body(agent, role)}"


def _render_codex(agent: dict[str, Any], role: str) -> str:
    cap = DIALECT["codex"][role]
    suffix = "" if role == "worker" else "-reviewer"
    name = f"{agent['id']}{suffix}"
    fm = _yaml_frontmatter(
        {
            "name": name,
            "sandbox": cap["sandbox"],
            "read_only": "true" if cap["read_only"] else "false",
        }
    )
    return f"{fm}\n\n{_body(agent, role)}"


def _render_workbuddy(agent: dict[str, Any], role: str) -> str:
    cap = DIALECT["workbuddy"][role]
    suffix = "" if role == "worker" else "_reviewer"
    spec = {
        "_generated": AUTOGEN_BANNER,
        "id": f"{agent['id']}{suffix}",
        "host": "workbuddy",
        "role": role,
        "agent_id": agent["id"],
        "name": agent.get("name", agent["id"]),
        "subagent_type": cap["subagent_type"],
        "read_only": cap["read_only"],
        "skill_package": f"skills/{agent.get('skill', agent['id'])}",
        "output_schema": agent.get("output_schema", ""),
        "rubrics": agent.get("rubrics", []),
        "invariants": {"max_depth": 1, "write_scope": "task_dir"},
    }
    return json.dumps(spec, ensure_ascii=False, indent=2)


RENDERERS = {
    "claude": (_render_claude, ".md"),
    "codex": (_render_codex, ".md"),
    "workbuddy": (_render_workbuddy, ".json"),
}


def derive_all(root: Path) -> list[DerivedFile]:
    """Project every stage agent into worker+reviewer files for all three hosts.

    Returns the list of derived files (not yet written). Pure function: callers
    decide whether to write.
    """

    config = read_json(root / "configs" / "agents.json", default={})
    agents = _stage_agents(config)
    derived: list[DerivedFile] = []
    for host, (render, ext) in RENDERERS.items():
        out_root = OUTPUT_ROOTS[host]
        for agent in agents:
            for role in ("worker", "reviewer"):
                suffix = "" if role == "worker" else (
                    "-reviewer" if host != "workbuddy" else "_reviewer"
                )
                filename = f"{agent['id']}{suffix}{ext}"
                derived.append(
                    DerivedFile(
                        host=host,
                        role=role,
                        agent_id=agent["id"],
                        path=out_root / filename,
                        content=render(agent, role),
                    )
                )
    return derived


def write_derived(root: Path, derived: list[DerivedFile]) -> list[Path]:
    """Write derived files to disk, creating parent dirs. Returns written paths."""

    written: list[Path] = []
    for item in derived:
        target = root / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8")
        written.append(target)
    return written
