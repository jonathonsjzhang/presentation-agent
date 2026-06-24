from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from presentation_agent.launch import BriefError, normalize_brief


class NormalizeBriefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_dict_brief_fills_defaults_and_schema(self) -> None:
        out = normalize_brief(
            {"topic": "T", "audience": "A", "decision_goal": "D"}, self.root
        )
        self.assertEqual(out["schema"], "raw_brief.v1")
        self.assertEqual(out["report_type"], "deep_dive")
        self.assertEqual(out["output_format"], "ppt")
        self.assertEqual(out["materials"], [])

    def test_inline_json_string(self) -> None:
        out = normalize_brief(
            '{"topic":"T","audience":"A","decision_goal":"D"}', self.root
        )
        self.assertEqual(out["topic"], "T")

    def test_file_path_string(self) -> None:
        brief_file = self.root / "b.json"
        brief_file.write_text(
            '{"topic":"T","audience":"A","decision_goal":"D"}', encoding="utf-8"
        )
        out = normalize_brief("b.json", self.root)
        self.assertEqual(out["audience"], "A")

    def test_plain_string_materials_normalized(self) -> None:
        out = normalize_brief(
            {
                "topic": "T",
                "audience": "A",
                "decision_goal": "D",
                "materials": ["论点甲", {"claim": "论点乙", "evidence": ["e1"]}],
            },
            self.root,
        )
        self.assertEqual(out["materials"][0], {"claim": "论点甲", "evidence": [], "so_what": ""})
        self.assertEqual(out["materials"][1]["evidence"], ["e1"])

    def test_missing_required_raises(self) -> None:
        with self.assertRaises(BriefError):
            normalize_brief({"topic": "只有主题"}, self.root)

    def test_bad_json_raises(self) -> None:
        with self.assertRaises(BriefError):
            normalize_brief("{not json", self.root)


if __name__ == "__main__":
    unittest.main()
