from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from presentation_agent.memory_router import MemoryRouter


class WP8MemoryRoutingTests(unittest.TestCase):
    def test_new_worker_ids_receive_feedback(self) -> None:
        cases = {
            "这个 finding 缺少反证，证据强度也写高了": "analysis",
            "故事线塔尖结论不够清晰": "storyline",
            "报告正文的章节缺少来源标注": "report",
            "DOCX 版式和视觉层级需要调整": "format",
        }
        with tempfile.TemporaryDirectory() as temp:
            router = MemoryRouter(Path(temp))
            for text, expected in cases.items():
                with self.subTest(expected=expected):
                    route = router.route(text=text, current_agent_id=expected)
                    self.assertEqual(route.target_agent_id, expected)
                    expected_owner = (
                        "format.document"
                        if expected == "format"
                        else f"core.{expected}"
                    )
                    self.assertEqual(route.capability_owner, expected_owner)
                    self.assertEqual(route.scope["worker"], [expected])


if __name__ == "__main__":
    unittest.main()
