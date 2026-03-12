import json
import shutil
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from execution.paper_metrics import compute_paper_summary, record_equity_snapshot, record_trade
from execution.storage import init_execution_schema
from tools import f6_t2_go_nogo_pack as tool


class TestF6T2GoNoGoPack(unittest.TestCase):
    def setUp(self):
        for d in ("db", "logs", "data", "reports"):
            Path(d).mkdir(parents=True, exist_ok=True)

        for dbp in (Path("db/execution.duckdb"),):
            if dbp.exists():
                dbp.unlink(missing_ok=True)
        init_execution_schema()

    def _seed_equity(self, as_of: date) -> None:
        start = as_of - timedelta(days=59)
        eq = 10000.0
        for i in range(60):
            d = start + timedelta(days=i)
            record_equity_snapshot(profile="paper", asof_date=d, equity=eq, note="f6_t2")
            eq *= 1.001

    def test_journal_gate_fails_when_required_fields_missing(self):
        as_of = date(2026, 3, 5)
        self._seed_equity(as_of)

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
                note="",  # missing operational note
            )

        s = compute_paper_summary(profile="paper", window_days=60, as_of_date=as_of)
        self.assertFalse(s.gates["f6_t2_journal_complete"]["pass"])
        self.assertGreater(s.gates["f6_t2_journal_complete"]["required_missing"]["entry_ts_utc"], 0)

    def test_tool_strict_passes_on_complete_journal(self):
        as_of = date(2026, 3, 5)
        self._seed_equity(as_of)

        for i in range(20):
            t0 = datetime(2026, 3, 1, 15, 30, tzinfo=timezone.utc) + timedelta(days=i)
            t1 = t0 + timedelta(hours=2)
            record_trade(
                profile="paper",
                symbol="IWM",
                strategy="BULL_PUT",
                entry_ts_utc=t0,
                exit_ts_utc=t1,
                strikes=[185.0, 180.0],
                regime_at_entry="NORMAL",
                score_at_entry=0.72,
                kelly_fraction=0.18,
                exit_reason="TIME",
                pnl=50.0,
                pnl_pct=0.005,
                slippage_ticks=1.0,
                violations=0,
                note="journal complete",
            )

        outdir = Path("reports") / "f6_t2_test_out"
        if outdir.exists():
            shutil.rmtree(outdir, ignore_errors=True)
        outdir.mkdir(parents=True, exist_ok=True)

        rc = tool.main(["--profile", "paper", "--window-days", "60", "--asof-date", "2026-03-05", "--strict", "--outdir", str(outdir)])
        self.assertEqual(rc, 0)

        jf = outdir / "f6_t2_go_nogo_pack.json"
        mf = outdir / "f6_t2_go_nogo_pack.md"
        self.assertTrue(jf.exists())
        self.assertTrue(mf.exists())

        payload = json.loads(jf.read_text(encoding="utf-8"))
        self.assertTrue(payload["gates"]["go_nogo"]["pass"])
        self.assertTrue(payload["gates"]["f6_t2_journal_complete"]["pass"])


if __name__ == "__main__":
    unittest.main()

