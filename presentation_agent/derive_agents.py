"""Derive per-terminal sub-agent definition files from a single source of truth.

``configs/agents.json`` is the single source of truth for the pipeline. This
module projects each Worker into the three host dialects. Quality checks happen
inside the Worker context plus deterministic runtime validation; no separate
process Reviewer agent is derived.

Dialect mapping (terminal-agnostic contract -> per-host expression):

============  =================  =====================  =========================
role          WorkBuddy          Claude Code            Codex
============  =================  =====================  =========================
worker        general-purpose    tools: Read,Write,Bash worker (full sandbox)
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
    },
    "claude": {
        # Claude Code agent frontmatter `tools:` is an allow-list.
        "worker": {"tools": "Read, Write, Edit, Bash", "read_only": False},
    },
    "codex": {
        # Codex expresses read-only via sandbox mode.
        "worker": {"sandbox": "workspace-write", "read_only": False},
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
    """Return the canonical workers from the active contract profile.

    Internal Evidence and post-document extensions are not stage-level
    sub-agents and therefore are not derived here.
    """

    profile_id = str(config.get("active_contract_profile") or "v0_3")
    profile = config.get("contract_profiles", {}).get(profile_id, {})
    active = profile.get("canonical_stages", [])
    by_id = {a.get("id"): a for a in profile.get("workers", [])}
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


def _body(agent: dict[str, Any]) -> str:
    name = agent.get("name", agent["id"])
    skill = agent.get("skill", agent["id"])
    out_schema = agent.get("output_schema", "")
    intro = (
        f"你是被派生的、拥有独立上下文的 **Worker sub-agent**，"
        f"扮演汇报流水线中「{name}」环节。你没有主对话历史——"
        f"全部任务输入都在 harness 交给你的指令包与 input 文件里。"
    )
    duty = (
        "读取 harness 准备的指令包（内嵌完整 SKILL.md 角色/核心准则/工作流/输出契约）"
        "与 input.json，在同一上下文中完成产出、自检和小修正，"
        f"写回指定 handoff 文件。output contract: `{out_schema}`。"
    )
    return (
        f"<!-- {AUTOGEN_BANNER} -->\n\n"
        f"{intro}\n\n"
        f"## 职责\n\n{duty}\n\n"
        f"## skill 包\n\n`skills/{skill}`\n\n"
        f"## 不变量\n\n"
        f"- 派生深度 = 1：你不得再下派任何子 agent。\n"
        f"- 写作用域限本 task_dir；只写指定的 handoff 输出文件。\n"
    )


def _render_claude(agent: dict[str, Any]) -> str:
    cap = DIALECT["claude"]["worker"]
    name = agent["id"]
    desc = (
        f"[{AUTOGEN_BANNER}] 汇报流水线「{agent.get('name', agent['id'])}」"
        "环节的内容生产 Worker。"
    )
    fm = _yaml_frontmatter(
        {"name": name, "description": desc, "tools": cap["tools"]}
    )
    return f"{fm}\n\n{_body(agent)}"


def _render_codex(agent: dict[str, Any]) -> str:
    cap = DIALECT["codex"]["worker"]
    name = agent["id"]
    fm = _yaml_frontmatter(
        {
            "name": name,
            "sandbox": cap["sandbox"],
            "read_only": "true" if cap["read_only"] else "false",
        }
    )
    return f"{fm}\n\n{_body(agent)}"


def _render_workbuddy(agent: dict[str, Any]) -> str:
    cap = DIALECT["workbuddy"]["worker"]
    spec = {
        "_generated": AUTOGEN_BANNER,
        "id": agent["id"],
        "host": "workbuddy",
        "role": "worker",
        "agent_id": agent["id"],
        "name": agent.get("name", agent["id"]),
        "subagent_type": cap["subagent_type"],
        "read_only": cap["read_only"],
        "skill_package": f"skills/{agent.get('skill', agent['id'])}",
        "output_schema": agent.get("output_schema", ""),
        "invariants": {"max_depth": 1, "write_scope": "task_dir"},
    }
    return json.dumps(spec, ensure_ascii=False, indent=2)


RENDERERS = {
    "claude": (_render_claude, ".md"),
    "codex": (_render_codex, ".md"),
    "workbuddy": (_render_workbuddy, ".json"),
}


def derive_all(root: Path) -> list[DerivedFile]:
    """Project every stage Worker for all three hosts.

    Returns the list of derived files (not yet written). Pure function: callers
    decide whether to write.
    """

    config = read_json(root / "configs" / "agents.json", default={})
    agents = _stage_agents(config)
    derived: list[DerivedFile] = []
    for host, (render, ext) in RENDERERS.items():
        out_root = OUTPUT_ROOTS[host]
        for agent in agents:
            filename = f"{agent['id']}{ext}"
            derived.append(
                DerivedFile(
                    host=host,
                    role="worker",
                    agent_id=agent["id"],
                    path=out_root / filename,
                    content=render(agent),
                )
            )
    return derived


def write_derived(root: Path, derived: list[DerivedFile]) -> list[Path]:
    """Replace generated host files with the active profile projection.

    Only files carrying the auto-generated banner are eligible for deletion;
    hand-written orchestrators and unrelated host files are preserved.
    """

    written: list[Path] = []
    desired = {item.path for item in derived}
    for relative_root in OUTPUT_ROOTS.values():
        output_root = root / relative_root
        if not output_root.exists():
            continue
        for target in output_root.iterdir():
            if not target.is_file():
                continue
            relative = target.relative_to(root)
            if relative in desired:
                continue
            try:
                text = target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if AUTOGEN_BANNER in text:
                target.unlink()

    for item in derived:
        target = root / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8")
        written.append(target)
    return written
