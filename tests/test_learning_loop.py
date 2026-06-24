from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from presentation_agent.io import read_json
from presentation_agent.learning import compare_material_versions
from presentation_agent.memory import MemoryItem, MemoryStore
from presentation_agent.memory_retrieval import MemoryRetriever
from presentation_agent.models import AgentSpec
from presentation_agent.routing import build_routing_policy

ROOT = Path(__file__).resolve().parents[1]


class LearningLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        shutil.copytree(ROOT / "configs", self.root / "configs")
        shutil.copytree(ROOT / "skills", self.root / "skills")
        (self.root / "data" / "agents" / "storyline_design").mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _spec(self) -> AgentSpec:
        cfg = read_json(self.root / "configs" / "agents.json")
        data = next(item for item in cfg["agents"] if item["id"] == "storyline_design")
        return AgentSpec.from_dict(data)

    def test_success_memory_records_project_event_and_hot_memory(self) -> None:
        store = MemoryStore(self.root, "storyline_design")
        log_id = store.record_success(
            dimension="Leadline",
            trigger_scene="unit_success",
            pattern="战略负责人材料标题写成业务判断 + so what",
            why_it_worked="更容易被标题连读测试捕捉",
        )

        self.assertEqual(log_id, "L-001")
        items = store.load_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].dimension, "Leadline")
        self.assertIn("优先复用", items[0].suggestion)

        events = (self.root / "data" / "learning" / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn('"event_type": "feedback"', events)
        self.assertIn('"source": "success"', events)

    def test_compare_material_versions_and_record_comparison(self) -> None:
        before = self.root / "docs" / "v1.md"
        after = self.root / "docs" / "v2.md"
        before.parent.mkdir(parents=True)
        before.write_text("私域流量分析\nQ3 DAU +12%\n", encoding="utf-8")
        after.write_text("某产品高时长来自任务型使用迁移，因此应优先争夺高频工作流\n行动：投入内容生态资源\n", encoding="utf-8")

        comparison = compare_material_versions(before, after)
        self.assertIn("action_closure", comparison["change_tags"])

        log_id = MemoryStore(self.root, "storyline_design").record_comparison(
            dimension="Leadline",
            trigger_scene="unit_compare",
            before_ref=str(before),
            after_ref=str(after),
            change_summary=", ".join(comparison["change_tags"]),
            lesson="后续标题从主题词升级为战略判断，并在结尾闭环 action",
        )
        self.assertEqual(log_id, "L-001")
        self.assertIn("战略判断", MemoryStore(self.root, "storyline_design").load_items()[0].suggestion)

    def test_retrieval_and_routing_are_attention_limited(self) -> None:
        store = MemoryStore(self.root, "storyline_design")
        store.save_items(
            [
                MemoryItem("M-001", "Leadline", "标题,战略", "keyword", "标题必须写成战略判断", hit_count=4),
                MemoryItem("M-002", "图表", "柱状图", "keyword", "避免无意义装饰图", hit_count=1),
                MemoryItem("M-003", "结构", "action", "keyword", "结尾必须回到 action", hit_count=2),
            ]
        )

        spec = self._spec()
        input_data = {"audience": "集团战略负责人", "topic": "某产品用户时长较高", "objective": "推动资源投入"}
        global_state = {"target_action": "申请内容生态资源"}
        retrieved = MemoryRetriever(store).retrieve(
            spec=spec,
            input_data=input_data,
            global_state=global_state,
            dimensions=["Leadline", "结构"],
            limit=2,
        )
        self.assertEqual([row.item.id for row in retrieved], ["M-001", "M-003"])

        policy = build_routing_policy(
            spec=spec,
            input_data=input_data,
            global_state=global_state,
            retrieved_memory=retrieved,
        )
        self.assertEqual(policy["review_strictness"], "heightened")
        self.assertIn("Leadline", policy["checklist_focus"])
        self.assertLessEqual(policy["memory_budget"]["max_prompt_items"], 2)


if __name__ == "__main__":
    unittest.main()
