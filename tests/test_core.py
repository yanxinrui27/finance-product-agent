import copy
import json
from pathlib import Path
import tempfile
import unittest

from finance_agent.core import Conflict, Store, assess, evaluate, impact, validate

ROOT = Path(__file__).resolve().parents[1]
(ROOT / "data").mkdir(exist_ok=True)


def demo():
    return json.loads((ROOT / "examples/demo.json").read_text(encoding="utf-8"))


def passed(data):
    for case in data["uats"]:
        case.update(status="passed", actual=case["expected"], executor="测试人", evidence="合成测试记录：已核对路由")
    return data


class DomainTests(unittest.TestCase):
    def test_money_boundary_rounding_and_currency(self):
        rule = demo()["rules"][0]
        for amount, expected in [("9999.99", "普通财务复核"), ("10000", "普通财务复核"), ("10000.005", "财务主管复核")]:
            self.assertEqual(evaluate(rule, amount, "CNY", "2026-10-21"), expected)
        for amount in ["NaN", "Infinity", "-1", "1e999999", True, 10000.01]:
            with self.assertRaises(ValueError):
                evaluate(rule, amount, "CNY", "2026-10-21")
        with self.assertRaises(ValueError):
            evaluate(rule, "1", "USD", "2026-10-21")
        with self.assertRaises(ValueError):
            evaluate(rule, "1", "CNY", "2027-01-01")

    def test_invalid_references_duplicates_and_coverage(self):
        data = demo()
        validate(data)
        data["prd"][0]["rule_ids"] = ["MISSING"]
        with self.assertRaises(ValueError):
            validate(data)
        data = demo()
        data["screens"][0]["id"] = "REQ-1"
        with self.assertRaises(ValueError):
            validate(data)
        data = demo()
        data["uats"] = []
        self.assertTrue(any("UAT" in x for x in assess(data)))

    def test_clarification_and_evidence_gate(self):
        self.assertTrue(assess(demo()))
        self.assertEqual(assess(passed(demo())), [])
        data = passed(demo())
        data["questions"][0]["answer"] = "  "
        self.assertTrue(any("澄清" in x for x in assess(data)))
        data = passed(demo())
        data["uats"][0]["evidence"] = ""
        self.assertTrue(any("证据" in x for x in assess(data)))

    def test_transitive_impact(self):
        data = demo()
        impacted = impact(data, ["RULE-1"])
        self.assertTrue({"RULE-1", "FLOW-1", "PRD-1", "UI-1", "UAT-1"} <= set(impacted))

    def test_cross_requirement_false_trace_is_rejected(self):
        data = demo()
        second = copy.deepcopy(data["requirements"][0])
        second["id"] = "REQ-2"
        data["requirements"].append(second)
        data["uats"][0]["requirement_ids"] = ["REQ-2"]
        with self.assertRaises(ValueError):
            validate(data)

    def test_approval_conflict_history_and_invalidation(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "data") as folder:
            store = Store(Path(folder) / "test.sqlite")
            first = store.save(demo(), 0, "产品经理", "合成初稿")
            with self.assertRaises(ValueError):
                store.approve(first["version"], "财务负责人")
            second = store.save(passed(demo()), 1, "测试人", "录入合成验收记录")
            store.approve(second["version"], "财务负责人")
            self.assertTrue(store.current()["signed"])
            with self.assertRaises(Conflict):
                store.save(demo(), 1, "另一编辑人", "过时版本")
            revised = copy.deepcopy(second["data"])
            revised["rules"][0]["threshold"] = "9000.00"
            third = store.save(revised, 2, "产品经理", "调整合成阈值")
            self.assertFalse(third["signed"])
            self.assertTrue(all(c["status"] == "pending" for c in third["data"]["uats"]))
            self.assertIn("UI-2", store.history()[0]["impact"])
            self.assertEqual(len(store.history()), 3)
            self.assertEqual(Store(Path(folder) / "test.sqlite").current()["version"], 3)


if __name__ == "__main__":
    unittest.main()
