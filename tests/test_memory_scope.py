from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from presentation_agent.io import read_json, write_json
from presentation_agent.memory import MemoryItem, MemoryStore
from presentation_agent.memory_router import MemoryRouter


class MemoryScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data_root = self.root / "data"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_memory_receives_core_owner_and_wildcard_scope(self) -> None:
        path = self.data_root / "agents" / "storyline" / "memory.json"
        write_json(path, {
            "items": [{
                "id": "M-001",
                "dimension": "结构",
                "trigger": "标题",
                "trigger_type": "keyword",
                "suggestion": "标题先给结论",
            }]
        })
        item = MemoryStore(
            self.root, "storyline", data_root=self.data_root
        ).load_items()[0]

        self.assertEqual(item.owner, "core.storyline")
        self.assertEqual(item.applies_to["audience"], ["*"])

    def test_profile_scoped_memory_does_not_cross_audience_or_format(self) -> None:
        board = MemoryItem(
            id="M-001",
            dimension="受众",
            trigger="风险",
            trigger_type="keyword",
            suggestion="董事会先讲 downside",
            owner="audience.board",
            applies_to={
                "worker": ["storyline"],
                "audience": ["board"],
                "report_type": ["*"],
                "format": ["ppt"],
            },
        )
        store = MemoryStore(
            self.root, "storyline", data_root=self.data_root
        )
        store.save_items([board])

        self.assertEqual(
            len(store.scan(
                "风险",
                active_capabilities=[
                    "core.storyline",
                    "audience.board",
                    "report.deep_dive",
                    "format.ppt",
                ],
            )),
            1,
        )
        self.assertEqual(
            store.scan(
                "风险",
                active_capabilities=[
                    "core.storyline",
                    "audience.external",
                    "report.deep_dive",
                    "format.document",
                ],
            ),
            [],
        )

    def test_repeated_memory_remains_scoped_hot_memory(self) -> None:
        store = MemoryStore(self.root, "format", data_root=self.data_root)
        store.save_items([
            MemoryItem(
                id="M-001",
                dimension="版式",
                trigger="来源太小",
                trigger_type="keyword",
                suggestion="来源脚注至少可读",
                hit_count=3,
                owner="format.ppt",
                applies_to={
                    "worker": ["format"],
                    "audience": ["*"],
                    "report_type": ["*"],
                    "format": ["ppt"],
                },
            )
        ])

        items = store.load_items()
        self.assertEqual(items[0].hit_count, 3)
        self.assertEqual(items[0].owner, "format.ppt")
        self.assertFalse((self.root / "skills").exists())

    def test_feedback_route_emits_capability_owner_and_narrow_scope(self) -> None:
        route = MemoryRouter(self.root, data_root=self.data_root).route(
            text="董事会 PPT 的来源脚注太小，下次需要放大",
            current_agent_id="format",
            active_capabilities=[
                "core.format",
                "audience.board",
                "report.deep_dive",
                "format.ppt",
            ],
        )

        self.assertEqual(route.target_agent_id, "format")
        self.assertEqual(route.capability_owner, "format.ppt")
        self.assertEqual(route.scope["audience"], ["board"])
        self.assertEqual(route.scope["format"], ["ppt"])

    def test_professional_feedback_stays_core_despite_active_profile(self) -> None:
        route = MemoryRouter(self.root, data_root=self.data_root).route(
            text="标题还是主题词，下次改成完整判断句",
            current_agent_id="storyline",
            active_capabilities=[
                "core.storyline",
                "audience.board",
                "report.deep_dive",
                "format.ppt",
            ],
        )

        self.assertEqual(route.capability_owner, "core.storyline")
        self.assertEqual(route.scope["audience"], ["*"])
        self.assertEqual(route.scope["format"], ["*"])


if __name__ == "__main__":
    unittest.main()
