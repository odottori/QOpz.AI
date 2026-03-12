import unittest

from execution.margin_efficiency import build_margin_efficiency_summary


class TestF1MarginEfficiencyMetric(unittest.TestCase):
    def test_summary_computes_margin_efficiency(self):
        trades = [
            {"margin_used": 1000.0, "pnl": 40.0},
            {"margin_used": 1500.0, "pnl": 30.0},
            {"margin_used": 500.0, "pnl": -10.0},
        ]
        s = build_margin_efficiency_summary(trades=trades, capital=10_000.0)
        self.assertAlmostEqual(s["avg_margin_used"], 1000.0)
        self.assertAlmostEqual(s["avg_margin_used_pct"], 0.10)
        self.assertAlmostEqual(s["total_pnl"], 60.0)
        self.assertAlmostEqual(s["margin_efficiency"], 0.06)


if __name__ == "__main__":
    unittest.main()
