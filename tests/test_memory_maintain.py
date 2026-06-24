from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from presentation_agent.memory import MemoryItem, MemoryStore

ROOT = Path(__file__).resolve().parents[1]


class MemoryMaintainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        shutil.copytree(ROOT / "configs", self.root / "configs")
        shutil.copytree(ROOT / "skills", self.root / "skills")
        (self.root / "data" / "agents" / "storyline_design").mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _store(self) -> MemoryStore:
        return MemoryStore(self.root, "storyline_design")

    def _seed(self, items: list[MemoryItem]) -> None:
        self._store().save_items(items)

    def test_thresholds_come_from_config(self) -> None:
        store = self._store()
        self.assertEqual(store.promotion_threshold(), 3)
        self.assertEqual(store.soft_limit(), 30)

    def test_promotion_candidates_by_hit_count(self) -> None:
        self._seed(
            [
                MemoryItem("M-001", "Wording", "唯一", "keyword", "改成有分寸", hit_count=3),
                MemoryItem("M-002", "结构", "现象：", "keyword", "写成判断句", hit_count=1),
            ]
        )
        candidates = self._store().promotion_candidates()
        self.assertEqual([c.id for c in candidates], ["M-001"])

    def test_apply_promotion_writes_rubric_and_removes_memory(self) -> None:
        self._seed(
            [MemoryItem("M-001", "Wording", "唯一", "keyword", "标题避免绝对化措辞", hit_count=3)]
        )
        store = self._store()
        result = store.apply_promotion(["M-001"])
        self.assertEqual(result["promoted"], ["M-001"])

        # rubric appended
        rubrics_path = self.root / "skills" / "storyline_design" / "rubrics.json"
        rubrics = json.loads(rubrics_path.read_text(encoding="utf-8"))["rubrics"]
        promoted = [r for r in rubrics if r.get("source", {}).get("promoted_from_memory") == "M-001"]
        self.assertEqual(len(promoted), 1)
        self.assertEqual(promoted[0]["severity"], "P1")

        # memory removed
        self.assertEqual(store.load_items(), [])

    def test_lint_flags_over_limit_orphan_and_duplicates(self) -> None:
        items = [MemoryItem(f"M-{i:03d}", "结构", f"trigger{i}", "keyword", f"建议{i}", hit_count=1) for i in range(1, 33)]
        # orphan link on the first item
        items[0].links = ["M-999"]
        # a duplicate of item 2 (same dimension+suggestion)
        items.append(MemoryItem("M-100", "结构", "dupe", "keyword", "建议2", hit_count=1))
        self._seed(items)

        report = self._store().lint()
        self.assertGreater(len(report["over_limit"]), 0)
        self.assertIn("M-001", report["orphan_links"])
        self.assertTrue(any(d["duplicate"] == "M-100" for d in report["duplicates"]))

    def test_apply_lint_evicts_and_clears_orphans(self) -> None:
        items = [MemoryItem(f"M-{i:03d}", "结构", f"t{i}", "keyword", f"s{i}", hit_count=0) for i in range(1, 35)]
        items[5].links = ["M-404"]
        self._seed(items)

        store = self._store()
        result = store.apply_lint()
        self.assertLessEqual(result["remaining"], store.soft_limit())
        for item in store.load_items():
            for link in item.links:
                self.assertTrue(any(o.id == link for o in store.load_items()))

    def test_record_text_feedback_infers_dimension_and_change(self) -> None:
        result = self._store().record_text_feedback(
            text="标题还是主题词，应该改成完整判断句并带出 so what",
            trigger_scene="human_review_chat",
        )

        self.assertEqual(result["log_id"], "L-001")
        self.assertEqual(result["dimension"], "Leadline")
        self.assertIn("标题还是主题词", result["problem"])
        self.assertIn("应该改成完整判断句", result["change"])
        items = self._store().load_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].dimension, "Leadline")

    def test_next_memory_id_uses_max_existing_sequence(self) -> None:
        self._seed(
            [
                MemoryItem("M-001", "结构", "a", "keyword", "A"),
                MemoryItem("M-004", "结构", "b", "keyword", "B"),
            ]
        )

        self._store().record_feedback(
            scope="agent",
            dimension="结构",
            trigger_scene="unit_test",
            problem="c",
            reason="",
            change="C",
        )

        self.assertEqual([item.id for item in self._store().load_items()], ["M-001", "M-004", "M-005"])

    def test_dream_writes_summary_and_applies_cleanup(self) -> None:
        self._seed(
            [
                MemoryItem("M-001", "结构", "标题主题词", "keyword", "标题写成判断句", hit_count=1),
                MemoryItem("M-002", "结构", "标题主题词", "keyword", "标题写成判断句", hit_count=2),
                MemoryItem("M-003", "证据", "口径", "keyword", "补充数据来源", hit_count=1, links=["M-404"]),
            ]
        )

        result = self._store().dream(apply=True, reason="unit_test")

        self.assertTrue(result["applied"])
        self.assertTrue((self.root / "data" / "agents" / "storyline_design" / "memory_summary.json").exists())
        self.assertTrue(result["report_path"].endswith(".json"))
        items = self._store().load_items()
        self.assertEqual(len([item for item in items if item.suggestion == "标题写成判断句"]), 1)
        for item in items:
            self.assertNotIn("M-404", item.links)


if __name__ == "__main__":
    unittest.main()
