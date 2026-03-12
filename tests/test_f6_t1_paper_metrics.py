import unittest
from datetime import date, timedelta
from pathlib import Path

from execution.paper_metrics import (
    compute_paper_summary,
    record_equity_snapshot,
    record_trade,
)
from execution.storage import init_execution_schema


class TestF6T1PaperMetrics(unittest.TestCase):
    def setUp(self):
        for d in ("db", "logs", "data", "reports"):
            Path(d).mkdir(parents=True, exist_ok=True)

        # Reset execution DB between tests (runtime-only, gitignored)
        for dbp in (Path("db/execution.duckdb"),):
            if dbp.exists():
                dbp.unlink(missing_ok=True)
        init_execution_schema()

    def test_go_nogo_and_f6_acceptance_pass_on_synthetic_data(self):
        as_of = date(2026, 3, 5)
        start = as_of - timedelta(days=59)

        # Constant-positive equity curve => MaxDD ~ 0 and Sharpe high.
        eq = 10000.0
        for i in range(60):
            d = start + timedelta(days=i)
            record_equity_snapshot(profile="paper", asof_date=d, equity=eq, note="test")
            eq *= 1.001  # +0.1% daily

        # Trade journal: 20 wins, slippage within target, no violations.
        for _ in range(20):
            record_trade(
                profile="paper",
                symbol="IWM",
                strategy="BULL_PUT",
                entry_ts_utc=None,
                exit_ts_utc=None,
                pnl=50.0,
                pnl_pct=0.005,
                slippage_ticks=1.0,
                violations=0,
                note="test",
            )

        s = compute_paper_summary(profile="paper", window_days=60, as_of_date=as_of)
        self.assertTrue(s.gates["go_nogo"]["pass"], s.gates["go_nogo"])
        self.assertTrue(s.gates["f6_t1_acceptance"]["pass"], s.gates["f6_t1_acceptance"])

    def test_missing_data_fails_gates_with_reasons(self):
        as_of = date(2026, 3, 5)
        s = compute_paper_summary(profile="paper", window_days=60, as_of_date=as_of)
        self.assertFalse(s.gates["go_nogo"]["pass"])
        self.assertTrue(any("missing equity snapshots" in r for r in s.gates["go_nogo"]["reasons"]))


if __name__ == "__main__":
    unittest.main()

