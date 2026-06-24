from __future__ import annotations

import json
import unittest
from pathlib import Path

from presentation_agent.io import read_json
from presentation_agent.llm.client import LLMClient
from presentation_agent.llm.factory import build_llm_client
from presentation_agent.llm.adapters.mock import synthesize_from_schema
from presentation_agent.llm.schema import extract_json, validate
from presentation_agent.llm.types import LLMRequest, SchemaValidationError

ROOT = Path(__file__).resolve().parents[1]
STORYLINE_SCHEMA = read_json(ROOT / "skills" / "storyline_design" / "schemas" / "storyline.v1.json")


class ExtractJsonTests(unittest.TestCase):
    def test_plain_json(self) -> None:
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})

    def test_fenced_block(self) -> None:
        text = "好的，结果如下：\n```json\n{\"a\": 2}\n```\n完成。"
        self.assertEqual(extract_json(text), {"a": 2})

    def test_balanced_fallback(self) -> None:
        text = 'noise {"a": {"b": 3}} trailing'
        self.assertEqual(extract_json(text), {"a": {"b": 3}})

    def test_no_json_raises(self) -> None:
        with self.assertRaises(ValueError):
            extract_json("没有任何 JSON 这里")


class ValidateTests(unittest.TestCase):
    def test_const_and_enum(self) -> None:
        schema = {"type": "object", "required": ["k"], "properties": {"k": {"const": "x"}}}
        self.assertEqual(validate({"k": "x"}, schema), [])
        self.assertTrue(validate({"k": "y"}, schema))

    def test_missing_required(self) -> None:
        schema = {"type": "object", "required": ["a", "b"], "properties": {}}
        errors = validate({"a": 1}, schema)
        self.assertTrue(any("'b'" in e for e in errors))

    def test_nested_array_items(self) -> None:
        schema = {
            "type": "object",
            "required": ["pages"],
            "properties": {
                "pages": {
                    "type": "array",
                    "items": {"type": "object", "required": ["page_no"], "properties": {"page_no": {"type": "integer"}}},
                }
            },
        }
        self.assertEqual(validate({"pages": [{"page_no": 1}]}, schema), [])
        self.assertTrue(validate({"pages": [{"page_no": "x"}]}, schema))


class SynthesizeTests(unittest.TestCase):
    def test_synthesized_storyline_passes_validation(self) -> None:
        payload = synthesize_from_schema(STORYLINE_SCHEMA)
        self.assertEqual(validate(payload, STORYLINE_SCHEMA), [])
        self.assertEqual(payload["agent_id"], "storyline_design")
        self.assertEqual(payload["schema"], "storyline.v1")
        self.assertIsInstance(payload["pages"], list)


class MockClientTests(unittest.TestCase):
    def test_mock_client_produces_valid_artifact(self) -> None:
        client = build_llm_client(ROOT, purpose="generate", provider_override="mock")
        request = LLMRequest(
            system="你是 storyline 设计专家",
            user="主题：测试",
            purpose="generate",
            schema=STORYLINE_SCHEMA,
            schema_name="storyline.v1",
            agent_id="storyline_design",
        )
        response = client.complete(request)
        self.assertEqual(response.provider, "mock")
        self.assertEqual(validate(response.data, STORYLINE_SCHEMA), [])

    def test_retry_then_fail_on_bad_adapter(self) -> None:
        class BadAdapter:
            kind = "bad"

            def generate(self, request: LLMRequest) -> str:
                return "完全没有 json"

        client = LLMClient(adapter=BadAdapter(), max_retries=1)
        with self.assertRaises(SchemaValidationError):
            client.complete(LLMRequest(system="s", user="u", schema={"type": "object"}))


if __name__ == "__main__":
    unittest.main()
