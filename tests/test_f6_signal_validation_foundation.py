import unittest
from datetime import date
from pathlib import Path

from execution.signal_validation import (
    list_signal_observations,
    list_signal_scorecards,
    rebuild_signal_scorecards,
    recompute_forward_outcomes,
)
from execution.storage import _connect, init_execution_schema, save_opportunity_scan
from scripts.market_data_ingest import DailyBar, ensure_market_schema, ingest_daily_bars
from strategy.opportunity_scanner import OpportunityCandidate, ScanResult

try:
    from fastapi.testclient import TestClient
    from api.opz_api import app
except Exception:
    TestClient = None
    app = None


class SignalValidationFoundationMixin:
    def _reset_db(self) -> None:
        for d in ("db", "logs", "data", "reports"):
            Path(d).mkdir(parents=True, exist_ok=True)
        dbp = Path("db/execution.duckdb")
        if dbp.exists():
            dbp.unlink(missing_ok=True)
        init_execution_schema()

    def _seed_scan_and_market(self) -> None:
        candidate = OpportunityCandidate(
            symbol="IWM",
            strategy="BULL_PUT",
            score=82.5,
            score_breakdown={"vol_edge": 80.0, "liquidity": 84.0, "risk_reward": 78.0, "regime_align": 90.0},
            expiry="2026-04-30",
            dte=17,
            strikes=[200.0, 195.0],
            delta=0.29,
            iv=0.24,
            iv_zscore_30=1.2,
            iv_zscore_60=1.0,
            iv_interp="expensive",
            expected_move=0.035,
            signal_vs_em_ratio=1.3,
            spread_pct=4.2,
            open_interest=1200,
            volume=340,
            max_loss=410.0,
            max_loss_pct=4.1,
            breakeven=201.2,
            breakeven_pct=-1.8,
            credit_or_debit=0.9,
            sizing_suggested=1.5,
            kelly_fraction=None,
            events_flag=None,
            human_review_required=False,
            stress_base=-240.0,
            stress_shock=-390.0,
            data_quality="real_time",
            source="ibkr_paper",
            underlying_price=205.0,
        )
        scan = ScanResult(
            profile="paper",
            regime="NORMAL",
            data_mode="VENDOR_REAL_CHAIN",
            scan_ts="2026-04-01T14:30:00Z",
            symbols_scanned=1,
            symbols_with_chain=1,
            filtered_count=0,
            cache_used=False,
            cache_age_hours=None,
            candidates=[candidate],
            ranking_suspended=False,
            suspension_reason=None,
            events_source="ibkr_live",
        )
        save_opportunity_scan(batch_id="batch-signal-001", profile="paper", scan_result=scan)
        con = _connect()
        try:
            ensure_market_schema(con)
            ingest_daily_bars(
                con,
                symbol="IWM",
                bars=[
                    DailyBar(dt=date(2026, 4, 2), open=205.0, high=206.0, low=204.5, close=206.0, adj_close=206.0, volume=100000),
                    DailyBar(dt=date(2026, 4, 6), open=206.0, high=210.0, low=205.5, close=209.0, adj_close=209.0, volume=120000),
                    DailyBar(dt=date(2026, 4, 21), open=209.0, high=214.0, low=208.0, close=212.0, adj_close=212.0, volume=130000),
                ],
                source="unit_test",
            )
        finally:
            con.close()


class TestSignalValidationFoundationStorage(unittest.TestCase, SignalValidationFoundationMixin):
    def setUp(self) -> None:
        self._reset_db()

    def test_scan_persists_signal_observation_and_forward_outcomes(self) -> None:
        self._seed_scan_and_market()
        observations = list_signal_observations(profile="paper", limit=10, include_outcomes=False)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["signal_direction"], "bullish")

        report = recompute_forward_outcomes(profile="paper", asof_date="2026-04-21", horizons=[1, 5, 20])
        self.assertEqual(report["computed"], 3)

        observations = list_signal_observations(profile="paper", limit=10, include_outcomes=True)
        outcomes = observations[0]["forward_outcomes"]
        self.assertEqual([o["horizon_days"] for o in outcomes], [1, 5, 20])
        self.assertAlmostEqual(outcomes[0]["spot_return_pct"], round((206.0 - 205.0) / 205.0 * 100.0, 4))
        self.assertTrue(outcomes[0]["success"])

    def test_scorecard_rollup_is_created(self) -> None:
        self._seed_scan_and_market()
        recompute_forward_outcomes(profile="paper", asof_date="2026-04-21", horizons=[5])
        score_report = rebuild_signal_scorecards(profile="paper", asof_date="2026-04-21", window_days=30, horizons=[5])
        self.assertGreaterEqual(score_report["scorecards_created"], 2)
        rows = list_signal_scorecards(profile="paper", asof_date="2026-04-21", window_days=30, horizon_days=5, limit=10)
        overall = [r for r in rows if r["strategy"] is None][0]
        self.assertEqual(overall["observations_count"], 1)
        self.assertEqual(overall["outcomes_ready_count"], 1)
        self.assertEqual(overall["hit_rate_pct"], 100.0)


@unittest.skipIf(TestClient is None or app is None, "fastapi not installed in this environment")
class TestSignalValidationFoundationApi(unittest.TestCase, SignalValidationFoundationMixin):
    def setUp(self) -> None:
        self._reset_db()
        self._seed_scan_and_market()
        recompute_forward_outcomes(profile="paper", asof_date="2026-04-21", horizons=[1, 5])
        rebuild_signal_scorecards(profile="paper", asof_date="2026-04-21", window_days=30, horizons=[1, 5])
        self.client = TestClient(app)

    def test_signal_observations_endpoint_returns_nested_outcomes(self) -> None:
        r = self.client.get("/opz/signals/observations", params={"profile": "paper", "limit": 5})
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()
        self.assertTrue(out["ok"])
        self.assertEqual(out["count"], 1)
        self.assertEqual(len(out["observations"][0]["forward_outcomes"]), 2)

    def test_signal_scorecards_endpoint_returns_rollups(self) -> None:
        r = self.client.get("/opz/signals/scorecards", params={"profile": "paper", "asof_date": "2026-04-21", "window_days": 30, "horizon_days": 5})
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()
        self.assertTrue(out["ok"])
        self.assertGreaterEqual(out["count"], 2)
        overall = [row for row in out["scorecards"] if row["strategy"] is None][0]
        self.assertEqual(overall["hit_rate_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
