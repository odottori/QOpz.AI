import unittest

from execution.execution_plan import select_execution_plan


class TestD26ExecutionPlan(unittest.TestCase):
    def test_reject_spread_pct(self):
        plan = select_execution_plan(bid=1.0, ask=1.3, spread_reject_pct=0.10)
        self.assertEqual(plan.kind, "REJECT")
        self.assertEqual(plan.reason, "SPREAD_TOO_WIDE")

    def test_ladder_default(self):
        plan = select_execution_plan(bid=100.0, ask=100.10, spread_reject_pct=0.10)
        self.assertEqual(plan.kind, "LADDER")
        self.assertEqual(plan.reason, "SMART_LADDER")

    def test_twap_optional(self):
        plan = select_execution_plan(bid=10.0, ask=10.70, enable_twap=True, twap_trigger_abs=0.50)
        self.assertEqual(plan.kind, "TWAP")
