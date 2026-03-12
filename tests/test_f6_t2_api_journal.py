import unittest
from datetime import date, timedelta
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from api.opz_api import app
except Exception:
    TestClient = None
    app = None

from execution.paper_metrics import record_equity_snapshot
from execution.storage import init_execution_schema


@unittest.skipIf(TestClient is None or app is None, "fastapi not installed in this environment")
class TestF6T2ApiJournal(unittest.TestCase):
    def setUp(self):
        for d in ("db", "logs", "data", "reports"):
            Path(d).mkdir(parents=True, exist_ok=True)

        for dbp in (Path("db/execution.duckdb"),):
            if dbp.exists():
                dbp.unlink(missing_ok=True)
        init_execution_schema()
        self.client = TestClient(app)

    def _seed_equity(self, as_of: date) -> None:
        start = as_of - timedelta(days=59)
        eq = 10000.0
        for i in range(60):
            d = start + timedelta(days=i)
            record_equity_snapshot(profile="paper", asof_date=d, equity=eq, note="api-test")
            eq *= 1.001

    def test_trade_endpoint_persists_f6_t2_fields_and_summary_gate(self):
        as_of = date(2026, 3, 5)
        self._seed_equity(as_of)

        payload = {
            "profile": "paper",
            "symbol": "IWM",
            "strategy": "BULL_PUT",
            "entry_ts_utc": "2026-03-05T15:30:00Z",
            "exit_ts_utc": "2026-03-05T17:30:00Z",
            "strikes": [185.0, 180.0],
            "regime_at_entry": "NORMAL",
            "score_at_entry": 0.72,
            "kelly_fraction": 0.18,
            "exit_reason": "TIME",
            "pnl": 50.0,
            "pnl_pct": 0.005,
            "slippage_ticks": 1.0,
            "violations": 0,
            "note": "journal-complete",
        }
        r = self.client.post("/opz/paper/trade", json=payload)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get("ok"))

        la = self.client.get("/opz/last_actions?limit=1")
        self.assertEqual(la.status_code, 200, la.text)
        trades = la.json().get("paper_trades", [])
        self.assertEqual(len(trades), 1)
        t0 = trades[0]
        self.assertEqual(t0.get("regime_at_entry"), "NORMAL")
        self.assertEqual(t0.get("exit_reason"), "TIME")
        self.assertAlmostEqual(float(t0.get("kelly_fraction")), 0.18)

        s = self.client.get("/opz/paper/summary?profile=paper&window_days=60&asof_date=2026-03-05")
        self.assertEqual(s.status_code, 200, s.text)
        gates = s.json().get("gates", {})
        self.assertIn("f6_t2_journal_complete", gates)
        self.assertTrue(gates["f6_t2_journal_complete"]["pass"])

    def test_trade_endpoint_rejects_out_of_range_kelly(self):
        payload = {
            "profile": "paper",
            "symbol": "IWM",
            "strategy": "BULL_PUT",
            "pnl": 10.0,
            "kelly_fraction": 1.5,
            "note": "invalid",
        }
        r = self.client.post("/opz/paper/trade", json=payload)
        self.assertEqual(r.status_code, 400)
        self.assertIn("kelly_fraction", r.text)


if __name__ == "__main__":
    unittest.main()


