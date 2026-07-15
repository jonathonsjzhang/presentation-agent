from __future__ import annotations

import unittest
from pathlib import Path

from presentation_agent.capabilities.models import CapabilityError
from presentation_agent.capabilities.profile import normalize_report_profile
from presentation_agent.launch import BriefError, launch_report, normalize_brief


ROOT = Path(__file__).resolve().parents[1]


class ReportProfileTests(unittest.TestCase):
    def test_host_launch_requires_worker_spawn_adapter(self) -> None:
        with self.assertRaisesRegex(BriefError, "显式选择 spawn_adapter"):
            launch_report({"topic": "AI 产品"}, root=ROOT)

    def test_canonical_profile(self) -> None:
        profile = normalize_report_profile(
            {
                "audience": "board",
                "report_type": "business_progress",
                "output_format": "document",
            },
            root=ROOT,
        )
        self.assertEqual(profile.audience, "board")
        self.assertEqual(profile.report_type, "business_progress")
        self.assertEqual(profile.output_format, "document")

    def test_chinese_aliases(self) -> None:
        profile = normalize_report_profile(
            {
                "audience": "董事会",
                "report_type": "业务进展汇报",
                "output_format": "文档",
            },
            root=ROOT,
        )
        self.assertEqual(
            profile.to_dict(),
            {
                "audience": "board",
                "report_type": "business_progress",
                "output_format": "document",
                "version": "v1",
            },
        )

    def test_unknown_value_fails_in_strict_mode(self) -> None:
        with self.assertRaises(CapabilityError):
            normalize_report_profile(
                {
                    "audience": "mystery",
                    "report_type": "deep_dive",
                    "output_format": "ppt",
                },
                root=ROOT,
            )

    def test_raw_brief_rejects_unknown_report_type(self) -> None:
        with self.assertRaises(CapabilityError):
            normalize_brief(
                {
                    "topic": "AI 产品",
                    "audience": "CEO 和 COO",
                    "decision_goal": "确定投入优先级",
                    "report_type": "weekly_magic",
                },
                ROOT,
            )

    def test_raw_brief_uses_new_confirmation_defaults(self) -> None:
        brief = normalize_brief(
            {
                "user_intent": "分析 AI 广告产品机会",
            },
            ROOT,
        )
        self.assertEqual(brief["audience"], "exec_office")
        self.assertEqual(brief["project_type"], "分析类")
        self.assertEqual(brief["delivery_format"], "文档")
        self.assertEqual(brief["report_length"], "3页")
        self.assertEqual(brief["output_format"], "document")
        self.assertEqual(brief["delivery_targets"], ["document"])
        self.assertEqual(brief["research_purpose"], "")
        self.assertEqual(brief["research_direction"], "")

    def test_raw_brief_does_not_prefill_research_fields_from_decision_fields(self) -> None:
        brief = normalize_brief(
            {
                "topic": "AI 产品",
                "decision_goal": "确定投入优先级",
                "expected_action": "形成资源配置结论",
            },
            ROOT,
        )
        self.assertEqual(brief["research_purpose"], "")
        self.assertEqual(brief["research_direction"], "")
        self.assertEqual(brief["decision_goal"], "确定投入优先级")
        self.assertEqual(brief["expected_action"], "形成资源配置结论")

    def test_raw_brief_presets_ppt_length_and_defers_delivery(self) -> None:
        brief = normalize_brief(
            {
                "topic": "AI 产品",
                "output_format": "PPT",
            },
            ROOT,
        )
        self.assertEqual(brief["requested_delivery_targets"], ["ppt"])
        self.assertEqual(brief["requested_followup_targets"], ["ppt"])
        self.assertEqual(brief["delivery_format"], "PPT")
        self.assertEqual(brief["report_length"], "10页PPT")
        self.assertEqual(brief["delivery_targets"], ["document"])
        self.assertEqual(brief["output_format"], "document")

    def test_raw_brief_requires_at_least_one_starting_signal(self) -> None:
        with self.assertRaises(BriefError):
            normalize_brief({}, ROOT)

    def test_free_form_audience_survives_raw_brief_normalization(self) -> None:
        brief = normalize_brief(
            {
                "topic": "AI 产品",
                "audience": "CEO 和 COO",
                "decision_goal": "确定投入优先级",
            },
            ROOT,
        )
        self.assertEqual(brief["audience"], "CEO 和 COO")
        self.assertEqual(brief["report_type"], "deep_dive")
        self.assertEqual(brief["output_format"], "document")
        self.assertEqual(brief["delivery_targets"], ["document"])
        self.assertEqual(brief["report_profile_version"], "v0_4")


if __name__ == "__main__":
    unittest.main()
