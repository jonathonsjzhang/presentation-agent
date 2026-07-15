from __future__ import annotations

from pathlib import Path
from typing import Optional

from presentation_agent.llm.schema import extract_json
from presentation_agent.llm.types import LLMRequest


class InlineAdapter:
    """In-session model channel (prompt-as-skill).

    When the harness is launched *inside* a host agent (WorkBuddy skill or a
    Claude Code subagent), the model that should produce the artifact is the
    host's own main model — the one already running this conversation. There is
    no API to "call back into" it; instead the host model executes the
    generation step itself and hands the JSON back to Python for validation.

    This adapter therefore does NOT spawn a model. It works as a relay:
      - `compose_instruction(request)` renders the instruction block that the
        SKILL.md wrapper embeds for the host model to execute.
      - the host model writes its JSON to an agreed handoff file.
      - `generate(request)` reads that handoff file back as raw text.

    The handoff path is provided per-run by the wrapper (stage A4). When no
    handoff is configured, generate() raises a clear error rather than guessing.
    """

    kind = "inline"

    def __init__(self, handoff_path: Optional[Path] = None) -> None:
        self.handoff_path = Path(handoff_path) if handoff_path else None

    def compose_instruction(self, request: LLMRequest) -> str:
        markdown = request.metadata.get("response_format") == "markdown"
        lines = [
            "## 由宿主模型执行的生成步骤",
            "",
            "请扮演以下角色并按 schema 产出结果：",
            "",
            "### 角色与 SOP",
            request.system.strip(),
            "",
            "### 任务输入",
            request.user.strip(),
            "",
            "### 输出要求",
            (
                "- 直接产出完整 Markdown 正文，写入约定的 .md 交接文件。"
                if markdown
                else f"- 严格符合 schema: {request.schema_name or '(见下)'}"
            ),
        ]
        if not markdown:
            lines.append("- 只产出一个 JSON 对象，写入约定的交接文件后由程序读取校验。")
        return "\n".join(lines)

    def generate(self, request: LLMRequest) -> str:
        if not self.handoff_path:
            raise RuntimeError(
                "InlineAdapter 需要 handoff_path：被宿主拉起时，由封装层（A4 阶段的 "
                "SKILL.md / subagent）把宿主模型产出的 JSON 写入该文件，再由程序读取校验。"
            )
        if not self.handoff_path.exists():
            raise RuntimeError(
                f"inline handoff 文件不存在：{self.handoff_path}。"
                "应由宿主模型先按 compose_instruction 的指令产出 JSON 写入此路径。"
            )
        text = self.handoff_path.read_text(encoding="utf-8")
        if request.metadata.get("response_format") != "markdown":
            extract_json(text)
        return text
