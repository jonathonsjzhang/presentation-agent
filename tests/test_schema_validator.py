from __future__ import annotations

import json
import unittest
from pathlib import Path

from presentation_agent.llm.schema import validate


ROOT = Path(__file__).resolve().parents[1]


class SchemaValidatorTests(unittest.TestCase):
    def test_additional_properties_false_rejects_legacy_fields(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"schema": {"const": "current.v1"}},
        }
        self.assertEqual(
            validate(
                {"schema": "current.v1", "legacy_pages": []},
                schema,
            ),
            ["$: unexpected field 'legacy_pages'"],
        )

    def test_additional_properties_schema_validates_dynamic_keys(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["status"],
            },
        }
        self.assertTrue(validate({"SU-01": {}}, schema))
        self.assertEqual(
            validate({"SU-01": {"status": "captured"}}, schema),
            [],
        )

    def test_qa_schema_validates_augmented_report_shape(self) -> None:
        schema = json.loads(
            (
                ROOT / "skills/qa_preparation/schemas/report.v1.json"
            ).read_text(encoding="utf-8")
        )
        errors = validate({"schema": "report.v1", "qa_question_list": ["为什么？"]}, schema)
        self.assertTrue(
            any(
                "$" in error
                and "missing required field 'report_markdown'" in error
                for error in errors
            ),
            errors,
        )

    def test_minimum_is_enforced(self) -> None:
        self.assertEqual(
            validate(-1, {"type": "integer", "minimum": 0}),
            ["$: must be at least 0, got -1"],
        )


if __name__ == "__main__":
    unittest.main()
