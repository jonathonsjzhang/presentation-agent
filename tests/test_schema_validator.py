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

    def test_local_ref_validates_qa_question_shape(self) -> None:
        schema = json.loads(
            (
                ROOT / "skills/qa_preparation/schemas/qa_pack.v1.json"
            ).read_text(encoding="utf-8")
        )
        question_schema = {
            "schema": "qa_pack.v1",
            "topic": "测试",
            "audience": "strategy_lead",
            "format": "document",
            "question_source_coverage": {},
            "top_questions": [{}],
            "page_level_questions": [],
            "risk_register": [],
            "data_gaps_to_close": [],
            "pre_meeting_followups": [],
            "backup_appendix_requests": [],
            "defensive_notes": [],
            "meeting_handling_plan": {},
            "speaker_script_handoff": {},
            "answer_tone_guidance": "直接",
        }
        errors = validate(question_schema, schema)
        self.assertTrue(
            any(
                "$.top_questions[0]" in error
                and "missing required field 'question_id'" in error
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
