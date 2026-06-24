from __future__ import annotations

import unittest

from presentation_agent.machine_check import run_machine_checks


class MachineCheckTests(unittest.TestCase):
    def test_enum_pass_and_fail(self) -> None:
        rubric = {
            "id": "R-ENUM",
            "severity": "P0",
            "dimension": "layout",
            "machine_check": {
                "each": "units",
                "rules": [
                    {"kind": "enum", "path": "layout", "values": ["a", "b"]}
                ],
            },
        }
        ok = {"units": [{"layout": "a"}, {"layout": "b"}]}
        self.assertEqual(run_machine_checks(ok, [rubric]), [])

        bad = {"units": [{"layout": "a"}, {"layout": "zzz"}]}
        objs = run_machine_checks(bad, [rubric])
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].severity, "P0")
        self.assertEqual(objs[0].id, "P0-R-ENUM")
        self.assertIn("units[1]", objs[0].evidence)

    def test_str_len_bounds(self) -> None:
        rubric = {
            "id": "R-LEN",
            "severity": "P0",
            "machine_check": {
                "each": "units",
                "rules": [{"kind": "str_len", "path": "headline", "min": 10, "max": 45}],
            },
        }
        bad = {"units": [{"headline": "短"}, {"headline": "这是一个足够长的合规标题包含动词与判断"}]}
        objs = run_machine_checks(bad, [rubric])
        self.assertEqual(len(objs), 1)
        self.assertIn("小于下限", objs[0].message)

    def test_exempt_when_skips_node(self) -> None:
        rubric = {
            "id": "R-TITLE",
            "severity": "P0",
            "machine_check": {
                "each": "units",
                "exempt_when": {"path": "layout", "values": ["cover", "closing"]},
                "rules": [{"kind": "str_len", "path": "headline", "min": 10}],
            },
        }
        data = {
            "units": [
                {"layout": "cover", "headline": "封面"},      # exempt -> ok
                {"layout": "key_takeaway", "headline": "短"},  # not exempt -> fail
            ]
        }
        objs = run_machine_checks(data, [rubric])
        self.assertEqual(len(objs), 1)
        self.assertIn("units[1]", objs[0].evidence)

    def test_array_count_max(self) -> None:
        rubric = {
            "id": "R-CNT",
            "severity": "P0",
            "machine_check": {
                "each": "charts",
                "rules": [{"kind": "count_max", "path": "segments", "value": 6}],
            },
        }
        bad = {"charts": [{"segments": list(range(9))}]}
        objs = run_machine_checks(bad, [rubric])
        self.assertEqual(len(objs), 1)
        self.assertIn("超过上限", objs[0].message)

    def test_optional_container_missing_is_silent(self) -> None:
        rubric = {
            "id": "R-OPT",
            "severity": "P1",
            "machine_check": {
                "each": "draft.units",
                "optional_container": True,
                "rules": [{"kind": "enum", "path": "layout", "values": ["a"]}],
            },
        }
        # container absent -> no objection
        self.assertEqual(run_machine_checks({}, [rubric]), [])

    def test_missing_required_container_fails(self) -> None:
        rubric = {
            "id": "R-REQ",
            "severity": "P0",
            "machine_check": {
                "each": "units",
                "rules": [{"kind": "enum", "path": "layout", "values": ["a"]}],
            },
        }
        objs = run_machine_checks({}, [rubric])
        self.assertEqual(len(objs), 1)
        self.assertIn("不存在或类型错误", objs[0].message)

    def test_rubric_without_machine_check_is_skipped(self) -> None:
        rubric = {"id": "R-NONE", "severity": "P0", "criterion": "subjective only"}
        self.assertEqual(run_machine_checks({"x": 1}, [rubric]), [])

    def test_root_scope_no_each(self) -> None:
        rubric = {
            "id": "R-ROOT",
            "severity": "P0",
            "machine_check": {
                "rules": [{"kind": "field_present", "path": "artifact_manifest"}],
            },
        }
        self.assertEqual(run_machine_checks({"artifact_manifest": {"x": 1}}, [rubric]), [])
        objs = run_machine_checks({}, [rubric])
        self.assertEqual(len(objs), 1)


if __name__ == "__main__":
    unittest.main()
