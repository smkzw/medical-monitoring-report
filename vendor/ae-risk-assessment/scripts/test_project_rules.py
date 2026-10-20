#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused regression tests for the project-rule adapter."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from assess_risk import apply_project_rules, assess_risk


def record(test, result, lo, hi, visit):
    return {
        "center": "中心1",
        "subj": "S01",
        "test": test,
        "result": result,
        "lo": lo,
        "hi": hi,
        "visit": visit,
        "date": "2026-01-01" if visit == "基线" else "2026-01-08",
        "unit": "单位",
        "cs": "异常无临床意义" if visit != "基线" else "正常",
        "desc": "",
        "desc_link": "",
        "note": "",
        "ae_ref": "",
        "mh_ref": "",
    }


class ProjectRuleTests(unittest.TestCase):
    def setUp(self):
        self.rules = {
            "version": "test",
            "non_ctcae_threshold_pct": 30,
            "excluded_tests": ["红细胞计数"],
            "excluded_directional_patterns": ["血红蛋白升高"],
            "bp": {
                "收缩压": {"info_max": 140, "medium_max_pct_change": 50},
                "舒张压": {"info_max": 90, "medium_max_pct_change": 50},
            },
        }
        self.data = {
            "lab_records": [
                record("红细胞计数", 4.5, 4.0, 5.5, "基线"),
                record("红细胞计数", 4.8, 4.0, 5.5, "V2"),
                record("血红蛋白", 120, 110, 150, "基线"),
                record("血红蛋白", 160, 110, 150, "V2"),
                record("非CTCAE指标", 100, 90, 110, "基线"),
                record("非CTCAE指标", 125, 90, 110, "V2"),
                record("非CTCAE指标", 135, 90, 110, "V3"),
                record("收缩压", 100, 90, 110, "基线"),
                record("收缩压", 140, 90, 130, "V2"),
                record("舒张压", 80, 60, 90, "基线"),
                record("舒张压", 120, 60, 90, "V2"),
            ],
            "test_names": ["红细胞计数", "血红蛋白", "非CTCAE指标", "收缩压", "舒张压"],
            "test_sources": {},
            "ae_records": [],
            "mh_records": [],
        }

    def test_excluded_tests_are_removed_before_assessment(self):
        filtered = apply_project_rules(self.data, self.rules)
        self.assertNotIn("红细胞计数", filtered["test_names"])
        self.assertTrue(all(r["test"] != "红细胞计数" for r in filtered["lab_records"]))

    def test_population_scope_uses_confirmed_group_table(self):
        extra = record("非CTCAE指标", 140, 90, 110, "V2")
        extra["subj"] = "S02"
        data = dict(self.data)
        data["lab_records"] = self.data["lab_records"] + [extra]
        rules = dict(self.rules, population_scope="group_table")
        filtered = apply_project_rules(data, rules, {"S01": "试验组"})
        self.assertEqual(filtered["subjects"], ["S01"])

    def test_directional_exclusion_and_non_ctcae_threshold(self):
        filtered = apply_project_rules(self.data, self.rules)
        results = assess_risk(filtered, {}, 20, project_rules=self.rules)
        items = [item for tests in results.values() for rows in tests.values() for item in rows]
        tests = {item["test"] for item in items}
        self.assertNotIn("血红蛋白", tests)
        non_ctcae = [item for item in items if item["test"] == "非CTCAE指标"]
        self.assertEqual(len(non_ctcae), 1)
        self.assertEqual(non_ctcae[0]["baseline_change_threshold_pct"], 30.0)

    def test_indicator_override_creates_prompt_or_caps_high_risk(self):
        filtered = apply_project_rules(self.data, self.rules)
        results = assess_risk(filtered, {}, 20, project_rules=self.rules)
        items = [item for tests in results.values() for rows in tests.values() for item in rows]
        by_test = {item["test"]: item for item in items}
        self.assertEqual(by_test["收缩压"]["risk"], "info")
        self.assertEqual(by_test["舒张压"]["risk"], "medium")
        self.assertEqual(by_test["舒张压"]["original_risk"], "high")


if __name__ == "__main__":
    unittest.main()
