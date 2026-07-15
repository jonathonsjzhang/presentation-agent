from __future__ import annotations

import json
import subprocess
from typing import Optional

from presentation_agent.llm.types import LLMRequest

_JSON_INSTRUCTION = "\n\n请只输出一个 ```json 代码块，不要任何解释、前言或结语。"


class CLIAdapter:
    """Subprocess model channel: borrow a coding agent's session and quota.

    Spawns a headless coding-agent CLI (e.g. `claude -p` or `codex exec`), feeds
    the composed prompt on stdin, and reads the model's text from stdout. JSON
    extraction + schema validation happen centrally in LLMClient, so this
    adapter only needs to return text.

    Two CLIs differ in how they emit output, controlled by `stdout_format`:
      - "text"  (codex exec): stdout is already the final message; progress is
                 on stderr. Return stdout as-is.
      - "envelope" (claude -p --output-format json): stdout is a JSON envelope
                 whose human text lives in a result field; unwrap it before
                 returning so downstream JSON extraction sees the actual content.

    Both real CLIs require explicit non-interactive flags (skip trust prompts,
    read-only sandbox). Those live in configs/llm.json `args`, not hard-coded
    here, so the command contract stays declarative.
    """

    kind = "cli"

    def __init__(
        self,
        command: str,
        args: Optional[list[str]] = None,
        timeout: int = 180,
        cwd: Optional[str] = None,
        stdout_format: str = "text",
        result_field: str = "result",
    ) -> None:
        self.command = command
        self.args = list(args or [])
        self.timeout = timeout
        self.cwd = cwd
        # how to read stdout: "text" (codex) or "envelope" (claude --output-format json)
        self.stdout_format = stdout_format
        # for envelope mode, which top-level field holds the assistant text
        self.result_field = result_field

    def generate(self, request: LLMRequest) -> str:
        prompt = self._compose_prompt(request)
        try:
            completed = subprocess.run(
                [self.command, *self.args],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.cwd,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"CLI provider command not found: {self.command!r}. "
                "确认本机已安装并可非交互执行该命令（如 claude / codex）。"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"CLI provider timed out after {self.timeout}s") from exc

        if completed.returncode != 0:
            raise RuntimeError(
                f"CLI provider {self.command!r} exited {completed.returncode}: "
                f"{(completed.stderr or '').strip()[:300]}"
            )
        return self._read_stdout(completed.stdout)

    def _read_stdout(self, stdout: str) -> str:
        if self.stdout_format != "envelope":
            return stdout
        # claude -p --output-format json emits a single JSON object whose
        # `result` field carries the assistant's text. If parsing fails, fall
        # back to the raw stdout so LLMClient can still attempt extraction.
        text = (stdout or "").strip()
        try:
            envelope = json.loads(text)
        except json.JSONDecodeError:
            return stdout
        if isinstance(envelope, dict) and self.result_field in envelope:
            value = envelope[self.result_field]
            return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return stdout

    @staticmethod
    def _compose_prompt(request: LLMRequest) -> str:
        suffix = (
            "\n\n请直接输出完整 Markdown 正文，不要 JSON 外壳或代码围栏。"
            if request.metadata.get("response_format") == "markdown"
            else _JSON_INSTRUCTION
        )
        parts = [request.system.strip(), "", request.user.strip(), suffix]
        return "\n".join(parts)
