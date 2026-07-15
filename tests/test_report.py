from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from presentation_agent.llm.schema import validate


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v0_3"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ReportCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storyline = read_json(FIXTURES / "storyline.v3.valid.json")
        self.report = read_json(FIXTURES / "report.v1.valid.json")
        self.schema = read_json(ROOT / "skills" / "report" / "schemas" / "report.v1.json")

    def test_report_skill_defines_a_real_markdown_author(self) -> None:
        skill = (ROOT / "skills" / "report" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(
            "基于已批准的 Storyline，把论证骨架编辑成一篇",
            skill,
        )
        self.assertIn("report_markdown", skill)
        self.assertIn("唯一内容真相源", skill)
        self.assertIn("本批访谈材料支持的核心判断是", skill)
        self.assertIn("把审计语言改成读者语言", skill)
        self.assertIn("默认不用“不是……而是……”", skill)
        self.assertIn("做四次删除式编辑", skill)
        self.assertIn("原因分析应把现象和量化拆解作为必要铺垫", skill)
        self.assertIn("`open_issues` 控制措辞和必要说明", skill)
        self.assertIn("Report 只负责写作和编辑，不决定阶段路由", skill)
        self.assertIn("Markdown-first run", skill)
        self.assertIn("Legacy `report.v1` run", skill)
        self.assertIn("runtime 将其保存为 canonical `report.md`", skill)
        self.assertNotIn("正文 block 必须", skill)

    def test_report_skill_blocks_process_draft_language(self) -> None:
        skill = (ROOT / "skills" / "report" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "本节、本文、现有材料、该结果、我们的假设",
            "一句话若只是在解释报告为何这样写",
            "总办若要把该趋势用于资源判断",
            "避免在每节末尾追加研究计划",
            "下一步需要、总办需要",
        ):
            self.assertIn(phrase, skill)

        self.assertNotIn("不是新的分析者", skill)
        self.assertNotIn("返回 Storyline", skill)
        self.assertNotIn("返回 Analysis", skill)
        self.assertNotIn("停止扩写并退回", skill)

    def test_report_skill_defines_safe_editing_boundaries(self) -> None:
        skill = (ROOT / "skills" / "report" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "保持核心判断、发现顺序、证据强度、决策含义和关键边界不变",
            "删除或新增一个结论、改变 bullet 从属关系属于 Storyline 修改",
            "这里的去重对象是完整数据集",
            "不要求关键数字从正文消失",
            "通常一至两句",
            "不做机械词频达标",
            "删掉后是否削弱核心答案、读者理解或任务要求的决策",
        ):
            self.assertIn(phrase, skill)

    def test_report_skill_uses_bullets_as_argument_structure(self) -> None:
        skill = (ROOT / "skills" / "report" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "用 Markdown 结构呈现金字塔关系",
            "bullet-led report",
            "一级 bullet 是正文的默认段落容器",
            "二级 bullet 用于展开支撑一级结论的数据、机制、差异或并列证据",
            "三级 bullet 用于进一步展开案例、用户分群、指标拆解",
            "子结论 → 数据或机制 → 具体案例",
            "bullet 是完整的分析单元",
            "一级 bullet 应能独立传达子结论",
            "整章若连续出现多个无 bullet 的分析段",
            "Format 不得重新决定哪些内容应成为 bullet",
        ):
            self.assertIn(phrase, skill)

    def test_report_skill_explicitly_applies_minto_pyramid_principle(self) -> None:
        skill = (ROOT / "skills" / "report" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "用 Minto 金字塔把 Storyline 写成 bullet 层级",
            "Minto 金字塔原理是战略报告的默认组织纪律",
            "`core_answer` 是全篇塔尖",
            "结论式章节标题是塔尖的第一层分解",
            "一级 bullet 是章节结论的下一层分解",
            "为什么成立、如何发生、由什么证据证明",
            "同组平行 bullet 保持相同抽象层级和同一种逻辑关系",
            "不等于机械 MECE、固定三点或每章相同层数",
            "核心答案 → 章节标题 → 一级子结论 → 支撑证据或机制",
            "从证据向上反读一次",
        ):
            self.assertIn(phrase, skill)

    def test_report_skill_includes_a_bullet_led_markdown_template(self) -> None:
        skill = (ROOT / "skills" / "report" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "### Markdown 输出模板",
            "## Executive Summary",
            "最重要的总判断",
            "直接支撑章节标题的一级子结论",
            "直接支撑上级判断的数据结论或比较判断",
            "直接支撑上级判断的机制判断",
            "进一步支撑该机制的具体案例、用户分群、指标拆解或访谈观察",
            "Source：专家访谈",
            "最终 bullet 数量和层级由 Storyline 的实际论证关系决定",
        ):
            self.assertIn(phrase, skill)

    def test_report_skill_exposes_readable_sources_not_evidence_ids(self) -> None:
        skill = (ROOT / "skills" / "report" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "来源是报告内容的一部分",
            "Source：专家访谈",
            "Source：用户问卷调研（n=1,568）",
            "没有 URL 时直接写来源类型或名称",
            "不得虚构链接",
            "必须在最终载体中被替换",
        ):
            self.assertIn(phrase, skill)

    def test_frozen_report_strictly_validates_as_report_v1(self) -> None:
        self.assertEqual(validate(self.report, self.schema), [])
        self.assertEqual(
            self.schema["required"],
            ["report_markdown", "visual_evidence_placements"],
        )
        self.assertEqual(self.report["agent_id"], "report")
        self.assertEqual(self.report["schema"], "report.v1")
        self.assertEqual(self.report["report_file"], "report.md")
        for legacy in ("executive_summary", "sections", "narrative_blocks", "recommendations"):
            self.assertNotIn(legacy, self.report)

    def test_markdown_is_complete_continuous_and_self_contained(self) -> None:
        markdown = self.report["report_markdown"]
        self.assertTrue(markdown.startswith("# AI 助手用户留存改善机会"))
        for heading in (
            "## Executive Summary",
            "## 一、成果保存与回访共同出现，但因果仍待验证",
            "## 二、可复用成果提供了值得优先验证的回访理由",
            "## 结论与战略含义",
            "## 方法与边界",
        ):
            self.assertIn(heading, markdown)
        self.assertGreater(len(markdown), 1000)
        self.assertNotRegex(markdown, r"(核心论点|本节结论|承接)：")
        self.assertIn("34%", markdown)
        self.assertIn("非随机", markdown)

    def test_markdown_covers_the_approved_storyline_spine(self) -> None:
        markdown = self.report["report_markdown"]
        for section in self.storyline["sections"]:
            self.assertIn(section["heading"], markdown)
        self.assertNotIn("section_manifest", self.schema["properties"])

    def test_markdown_uses_readable_sources_not_internal_ids(self) -> None:
        markdown = self.report["report_markdown"]
        self.assertIn("来源：冻结匿名化行为数据快照", markdown)
        self.assertNotRegex(markdown, r"\b(?:E-Q|E-I|C-|F-)\d")
        self.assertIn("冻结匿名化行为数据快照", markdown)


if __name__ == "__main__":
    unittest.main()
