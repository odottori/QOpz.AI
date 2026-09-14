from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from execution.storage import _connect, init_execution_schema, save_opportunity_scan
from strategy.capital_feasibility import build_capital_feasibility
from strategy.opportunity_scanner import (
    OpportunityCandidate,
    ScanResult,
    _build_candidate,
    _STRATEGY_BULL_PUT,
    compute_chain_analytics,
    ChainFilterResult,
    FilterRejectStats,
    OptionContract,
)


class TestCapitalFeasibilityCore(unittest.TestCase):
    def test_bull_put_metrics_are_computed(self):
        out = build_capital_feasibility(
            strategy="BULL_PUT",
            account_size=10_000.0,
            underlying_price=500.0,
            dte=33,
            strikes=[490.0, 495.0],
            credit_or_debit=3.40,
            max_loss=160.0,
        ).to_dict()
        self.assertEqual(out["collateral_required"], 160.0)
        self.assertAlmostEqual(out["collateral_pct_of_account"], 1.6, places=3)
        self.assertAlmostEqual(out["max_loss_pct_of_account"], 1.6, places=3)
        self.assertGreater(out["post_assignment_concentration_pct"], 400.0)
        self.assertIn("capital_efficiency_score", out)

    def test_wheel_requires_assignment_scale_capital(self):
        out = build_capital_feasibility(
            strategy="WHEEL",
            account_size=10_000.0,
            underlying_price=480.0,
            dte=30,
            strikes=[475.0],
            credit_or_debit=2.50,
            max_loss=47_500.0,
        ).to_dict()
        self.assertEqual(out["collateral_required"], 47_500.0)
        self.assertAlmostEqual(out["post_fill_concentration_pct"], 475.0, places=3)
        self.assertAlmostEqual(out["post_assignment_concentration_pct"], 475.0, places=3)

    def test_build_candidate_emits_capital_feasibility(self):
        contracts = [
            OptionContract(symbol="TEST", expiry="2026-04-17", dte=33, strike=490.0, right="P", bid=3.80, ask=4.00, delta=-0.35, gamma=0.01, theta=-0.02, vega=0.08, iv=0.28, open_interest=800, volume=60, underlying_price=500.0),
            OptionContract(symbol="TEST", expiry="2026-04-17", dte=33, strike=485.0, right="P", bid=0.40, ask=0.60, delta=-0.20, gamma=0.01, theta=-0.01, vega=0.05, iv=0.27, open_interest=600, volume=40, underlying_price=500.0),
            OptionContract(symbol="TEST", expiry="2026-04-17", dte=33, strike=500.0, right="C", bid=3.10, ask=3.30, delta=0.50, gamma=0.02, theta=-0.03, vega=0.09, iv=0.29, open_interest=900, volume=80, underlying_price=500.0),
            OptionContract(symbol="TEST", expiry="2026-04-17", dte=33, strike=500.0, right="P", bid=3.00, ask=3.20, delta=-0.50, gamma=0.02, theta=-0.03, vega=0.09, iv=0.29, open_interest=850, volume=70, underlying_price=500.0),
        ]
        chain = ChainFilterResult(
            symbol="TEST",
            profile="dev",
            data_mode="SYNTHETIC_SURFACE_CALIBRATED",
            fetched_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            expiry="2026-04-17",
            dte=33,
            underlying_price=500.0,
            contracts_raw=len(contracts),
            contracts_kept=contracts,
            reject_stats=FilterRejectStats(total_raw=len(contracts)),
            data_quality="cache",
            source="csv_delayed",
        )
        iv_hist = [round(0.25 + 0.01 * (i % 7 - 3), 6) for i in range(90)]
        analytics = compute_chain_analytics(chain, iv_history=iv_hist)
        c0 = _build_candidate(chain, analytics, _STRATEGY_BULL_PUT, "NORMAL", iv_hist, account_size=10_000.0)
        self.assertIsNotNone(c0)
        cf = c0.capital_feasibility
        self.assertIsInstance(cf, dict)
        self.assertIn("collateral_required", cf)
        self.assertIn("capital_efficiency_score", cf)

    def test_save_opportunity_scan_persists_capital_feasibility_json(self):
        Path("db").mkdir(parents=True, exist_ok=True)
        dbp = Path("db/execution.duckdb")
        if dbp.exists():
            dbp.unlink(missing_ok=True)
        init_execution_schema()

        candidate = OpportunityCandidate(
            symbol="TEST",
            strategy="BULL_PUT",
            score=75.0,
            score_breakdown={"vol_edge": 20, "liquidity": 20, "risk_reward": 20, "regime_align": 15},
            expiry="2026-04-17",
            dte=33,
            strikes=[495.0, 490.0],
            delta=0.30,
            iv=0.28,
            iv_zscore_30=1.2,
            iv_zscore_60=0.9,
            iv_interp="expensive",
            expected_move=0.035,
            signal_vs_em_ratio=None,
            spread_pct=2.5,
            open_interest=500,
            volume=120,
            max_loss=160.0,
            max_loss_pct=1.6,
            breakeven=491.60,
            breakeven_pct=1.68,
            credit_or_debit=3.40,
            sizing_suggested=2.0,
            kelly_fraction=None,
            events_flag=None,
            human_review_required=False,
            stress_base=-96.0,
            stress_shock=-152.0,
            data_quality="cache",
            source="csv_delayed",
            underlying_price=500.0,
            capital_feasibility=build_capital_feasibility(
                strategy="BULL_PUT",
                account_size=10_000.0,
                underlying_price=500.0,
                dte=33,
                strikes=[495.0, 490.0],
                credit_or_debit=3.40,
                max_loss=160.0,
            ).to_dict(),
        )
        result = ScanResult(
            profile="paper",
            regime="NORMAL",
            data_mode="SYNTHETIC_SURFACE_CALIBRATED",
            scan_ts=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            symbols_scanned=1,
            symbols_with_chain=1,
            filtered_count=0,
            cache_used=True,
            cache_age_hours=0.5,
            candidates=[candidate],
            ranking_suspended=False,
            suspension_reason=None,
        )
        save_opportunity_scan(batch_id="batch-capital-001", profile="paper", scan_result=result)

        con = _connect()
        try:
            row = con.execute(
                "SELECT capital_feasibility_json FROM opportunity_candidates WHERE batch_id = ?",
                ["batch-capital-001"],
            ).fetchone()
        finally:
            con.close()
        self.assertIsNotNone(row)
        payload = json.loads(row[0])
        self.assertIn("collateral_required", payload)
        self.assertIn("capital_efficiency_score", payload)


if __name__ == "__main__":
    unittest.main()
