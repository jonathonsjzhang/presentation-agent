from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from presentation_agent.llm.adapters.cli import CLIAdapter
from presentation_agent.llm.client import LLMClient
from presentation_agent.llm.types import LLMRequest

ROOT = Path(__file__).resolve().parents[1]


def _fake_cli(body: str) -> tuple[str, list[str], object]:
    """Write a tiny Python program acting as a 'CLI' and return how to invoke it.

    Returns (command, args, tmpdir_handle). Keep the handle alive for the test
    so the file is not deleted before the subprocess runs.
    """
    tmp = tempfile.TemporaryDirectory()
    script = Path(tmp.name) / "fake_cli.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return sys.executable, [str(script)], tmp


class CLIEnvelopeUnwrapTests(unittest.TestCase):
    """Validate stdout handling without any real CLI, by driving a tiny Python
    program as the 'CLI'. Hermetic and fast."""

    def test_text_mode_returns_stdout_verbatim(self) -> None:
        cmd, args, tmp = _fake_cli(
            """
            import sys, json
            sys.stdin.read()
            print(json.dumps({"a": 1}))
            """
        )
        with tmp:
            adapter = CLIAdapter(command=cmd, args=args, stdout_format="text")
            out = adapter.generate(LLMRequest(system="s", user="u"))
        self.assertIn('"a": 1', out)

    def test_envelope_mode_unwraps_result_field(self) -> None:
        cmd, args, tmp = _fake_cli(
            """
            import sys, json
            sys.stdin.read()
            inner = json.dumps({"b": 2})
            print(json.dumps({"result": inner, "session_id": "x"}))
            """
        )
        with tmp:
            adapter = CLIAdapter(command=cmd, args=args, stdout_format="envelope", result_field="result")
            out = adapter.generate(LLMRequest(system="s", user="u"))
        self.assertIn('"b": 2', out)

    def test_client_validates_cli_output_against_schema(self) -> None:
        cmd, args, tmp = _fake_cli(
            """
            import sys, json
            sys.stdin.read()
            print("```json")
            print(json.dumps({"k": "v"}))
            print("```")
            """
        )
        with tmp:
            adapter = CLIAdapter(command=cmd, args=args, stdout_format="text")
            client = LLMClient(adapter=adapter, max_retries=1)
            schema = {"type": "object", "required": ["k"], "properties": {"k": {"type": "string"}}}
            resp = client.complete(LLMRequest(system="s", user="u", schema=schema))
        self.assertEqual(resp.data, {"k": "v"})
        self.assertEqual(resp.provider, "cli")

    def test_nonzero_exit_raises(self) -> None:
        cmd, args, tmp = _fake_cli("import sys; sys.exit(3)")
        with tmp:
            adapter = CLIAdapter(command=cmd, args=args)
            with self.assertRaises(RuntimeError):
                adapter.generate(LLMRequest(system="s", user="u"))

    def test_missing_command_raises_clear_error(self) -> None:
        adapter = CLIAdapter(command="definitely-not-a-real-cli-xyz", args=[])
        with self.assertRaises(RuntimeError) as ctx:
            adapter.generate(LLMRequest(system="s", user="u"))
        self.assertIn("not found", str(ctx.exception))


class RealCLIIntegrationTests(unittest.TestCase):
    """Opt-in integration: only runs if a real CLI is installed. Skips cleanly
    otherwise so CI never depends on claude/codex being present."""

    def test_claude_cli_round_trip_if_installed(self) -> None:
        if os.environ.get("RUN_REAL_CLI_TESTS") != "1":
            self.skipTest("set RUN_REAL_CLI_TESTS=1 to enable real CLI integration tests")
        if shutil.which("claude") is None:
            self.skipTest("claude CLI not installed")
        from presentation_agent.llm.factory import build_llm_client

        client = build_llm_client(ROOT, purpose="generate", provider_override="cli")
        schema = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}
        resp = client.complete(
            LLMRequest(system="You output JSON.", user='Return {"ok": true}', schema=schema)
        )
        self.assertTrue(resp.data.get("ok"))

    def test_codex_cli_round_trip_if_installed(self) -> None:
        if os.environ.get("RUN_REAL_CLI_TESTS") != "1":
            self.skipTest("set RUN_REAL_CLI_TESTS=1 to enable real CLI integration tests")
        if shutil.which("codex") is None:
            self.skipTest("codex CLI not installed")
        from presentation_agent.llm.factory import build_llm_client

        client = build_llm_client(ROOT, purpose="generate", provider_override="codex")
        schema = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}
        resp = client.complete(
            LLMRequest(system="You output JSON.", user='Return {"ok": true}', schema=schema)
        )
        self.assertTrue(resp.data.get("ok"))


if __name__ == "__main__":
    unittest.main()
