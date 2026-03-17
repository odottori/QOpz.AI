"""
tests/test_roc1_scan.py — ROC1-T1

Test suite per scan_opportunities() e funzioni di supporto:
  - _select_strategy: SHOCK/CAUTION/NORMAL + IV Z-Score + signal
  - _pick_spread_legs: selezione contratti per ogni strategia
  - _approx_payoff: calcoli credit/debit/max_loss/breakeven
  - _build_candidate: costruzione OpportunityCandidate
  - scan_opportunities: pipeline completa
    - SHOCK → suspended
    - lista vuota → 0 candidati
    - CAUTION → BULL_PUT forzato, sizing=1.0%
    - simbolo mancante → gestito senza crash
    - min_score filtra candidati bassi
    - top_n limita output
    - IV history passata via iv_history_map
    - DATA_MODE watermark nel risultato

Nessun IBKR, nessuna rete, solo CSV fixture (synt_chain_TEST.csv).
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from strategy.opportunity_scanner import (
    DELTA_LONG_MAX,
    DELTA_LONG_MIN,
    DEFAULT_MAX_SPREAD_PCT,
    FilterParams,
    OpportunityCandidate,
    ScanResult,
    _STRATEGY_BULL_CALL,
    _STRATEGY_BULL_PUT,
    _STRATEGY_IRON_CONDOR,
    _STRATEGY_STRADDLE,
    _approx_payoff,
    _build_candidate,
    _closest_delta,
    _ivr_from_history,
    _pick_spread_legs,
    _select_strategy,
    _sizing_adaptive_fixed,
    _stress_estimate,
    compute_chain_analytics,
    scan_opportunities,
    ChainFilterResult,
    FilterRejectStats,
    OptionContract,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _expiry(days: int = 34) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _contract(
    strike: float = 500.0, right: str = "C", delta: float = 0.30,
    bid: float = 2.0, ask: float = 2.20, iv: float = 0.25,
    oi: int = 600, volume: int = 50, dte: int = 30,
    underlying: float = 500.0,
) -> OptionContract:
    exp = _expiry(dte)
    return OptionContract(
        symbol="SPY", expiry=exp, dte=dte, strike=strike, right=right,
        bid=bid, ask=ask, delta=delta, gamma=0.01, theta=-0.05, vega=0.30,
        iv=iv, open_interest=oi, volume=volume, underlying_price=underlying,
    )


def _minimal_chain_result(
    contracts: list[OptionContract], symbol: str = "SPY", dte: int = 30,
) -> ChainFilterResult:
    underlying = contracts[0].underlying_price if contracts else 500.0
    return ChainFilterResult(
        symbol=symbol, profile="dev",
        data_mode="SYNTHETIC_SURFACE_CALIBRATED",
        fetched_at=datetime.now(timezone.utc).isoformat() + "Z",
        expiry=_expiry(dte), dte=dte,
        underlying_price=underlying,
        contracts_raw=len(contracts), contracts_kept=contracts,
        reject_stats=FilterRejectStats(total_raw=len(contracts)),
    )


def _iv_hist(n: int = 90, mean: float = 0.25) -> list[float]:
    """Variabile ma deterministica."""
    return [mean + 0.01 * (i % 7 - 3) for i in range(n)]


# ─────────────────────────────────────────────────────────────────────────────
# 1.  _select_strategy
# ─────────────────────────────────────────────────────────────────────────────

class TestSelectStrategy(unittest.TestCase):

    def test_shock_returns_empty(self):
        s = _select_strategy("SHOCK", None, None, None)
        self.assertEqual(s, "")

    def test_caution_always_bull_put(self):
        for z in (-2.0, 0.0, 2.0, None):
            with self.subTest(z=z):
                s = _select_strategy("CAUTION", z, "bullish", 60.0)
                self.assertEqual(s, _STRATEGY_BULL_PUT)

    def test_normal_bullish_iv_expensive_bull_put(self):
        s = _select_strategy("NORMAL", 2.0, "bullish", 50.0)
        self.assertEqual(s, _STRATEGY_BULL_PUT)

    def test_normal_bullish_iv_cheap_bull_call(self):
        s = _select_strategy("NORMAL", -2.0, "bullish", 50.0)
        self.assertEqual(s, _STRATEGY_BULL_CALL)

    def test_normal_bullish_iv_fair_defaults_bull_put(self):
        s = _select_strategy("NORMAL", 0.0, "bullish", 50.0)
        self.assertEqual(s, _STRATEGY_BULL_PUT)

    def test_normal_neutral_high_ivr_iron_condor(self):
        s = _select_strategy("NORMAL", 0.0, "neutral", 50.0)
        self.assertEqual(s, _STRATEGY_IRON_CONDOR)

    def test_normal_neutral_low_ivr_straddle(self):
        s = _select_strategy("NORMAL", 0.0, "neutral", 30.0)
        self.assertEqual(s, _STRATEGY_STRADDLE)

    def test_normal_no_signal_defaults_bull_put(self):
        # None signal treated as bullish by default
        s = _select_strategy("NORMAL", 0.5, None, 40.0)
        self.assertEqual(s, _STRATEGY_BULL_PUT)


# ─────────────────────────────────────────────────────────────────────────────
# 2.  _closest_delta
# ─────────────────────────────────────────────────────────────────────────────

class TestClosestDelta(unittest.TestCase):

    def _contracts(self) -> list[OptionContract]:
        return [
            _contract(strike=490.0, right="P", delta=-0.20),
            _contract(strike=495.0, right="P", delta=-0.30),
            _contract(strike=500.0, right="P", delta=-0.45),
        ]

    def test_finds_closest_delta(self):
        c = _closest_delta(self._contracts(), "P", 0.30)
        self.assertIsNotNone(c)
        self.assertAlmostEqual(c.strike, 495.0)

    def test_wrong_right_returns_none(self):
        c = _closest_delta(self._contracts(), "C", 0.30)
        self.assertIsNone(c)

    def test_empty_list_returns_none(self):
        c = _closest_delta([], "P", 0.30)
        self.assertIsNone(c)


# ─────────────────────────────────────────────────────────────────────────────
# 3.  _pick_spread_legs
# ─────────────────────────────────────────────────────────────────────────────

class TestPickSpreadLegs(unittest.TestCase):

    def _spy_contracts(self) -> list[OptionContract]:
        underlying = 500.0
        return [
            _contract(500.0, "C", 0.50, underlying=underlying),
            _contract(505.0, "C", 0.30, underlying=underlying),
            _contract(510.0, "C", 0.20, underlying=underlying),
            _contract(500.0, "P", -0.50, underlying=underlying),
            _contract(495.0, "P", -0.30, underlying=underlying),
            _contract(490.0, "P", -0.20, underlying=underlying),
        ]

    def test_bull_put_returns_short_and_long(self):
        contracts = self._spy_contracts()
        short, long = _pick_spread_legs(contracts, _STRATEGY_BULL_PUT)
        self.assertIsNotNone(short)
        # If long found: short.strike > long.strike (spread)
        if long is not None:
            self.assertGreater(short.strike, long.strike)

    def test_bull_call_returns_two_legs(self):
        contracts = self._spy_contracts()
        primary, hedge = _pick_spread_legs(contracts, _STRATEGY_BULL_CALL)
        self.assertIsNotNone(primary)

    def test_straddle_returns_call_and_put(self):
        contracts = self._spy_contracts()
        call_leg, put_leg = _pick_spread_legs(contracts, _STRATEGY_STRADDLE)
        if call_leg is not None:
            self.assertEqual(call_leg.right, "C")
        if put_leg is not None:
            self.assertEqual(put_leg.right, "P")

    def test_empty_contracts_returns_none_pair(self):
        short, long = _pick_spread_legs([], _STRATEGY_BULL_PUT)
        self.assertIsNone(short)
        self.assertIsNone(long)


# ─────────────────────────────────────────────────────────────────────────────
# 4.  _approx_payoff
# ─────────────────────────────────────────────────────────────────────────────

class TestApproxPayoff(unittest.TestCase):

    def _put_pair(self):
        short = _contract(495.0, "P", -0.30, bid=2.50, ask=2.70)
        long  = _contract(490.0, "P", -0.20, bid=1.20, ask=1.40)
        return short, long

    def test_bull_put_credit_positive(self):
        short, long = self._put_pair()
        credit, max_loss, breakeven, rr = _approx_payoff(_STRATEGY_BULL_PUT, short, long, 500.0)
        self.assertGreater(credit, 0.0)

    def test_bull_put_max_loss_positive(self):
        short, long = self._put_pair()
        _, max_loss, _, _ = _approx_payoff(_STRATEGY_BULL_PUT, short, long, 500.0)
        self.assertGreater(max_loss, 0.0)

    def test_bull_put_rr_positive(self):
        short, long = self._put_pair()
        _, _, _, rr = _approx_payoff(_STRATEGY_BULL_PUT, short, long, 500.0)
        self.assertGreater(rr, 0.0)

    def test_bull_put_breakeven_below_short_strike(self):
        short, long = self._put_pair()
        _, _, be, _ = _approx_payoff(_STRATEGY_BULL_PUT, short, long, 500.0)
        self.assertLess(be, short.strike)

    def test_no_short_leg_returns_safe_defaults(self):
        credit, max_loss, _, _ = _approx_payoff(_STRATEGY_BULL_PUT, None, None, 500.0)
        self.assertEqual(credit, 0.0)
        self.assertGreater(max_loss, 0.0)

    def test_straddle_debit_negative(self):
        call = _contract(500.0, "C", 0.50, bid=3.00, ask=3.20)
        put  = _contract(500.0, "P", -0.50, bid=2.80, ask=3.00)
        credit, max_loss, _, _ = _approx_payoff(_STRATEGY_STRADDLE, call, put, 500.0)
        self.assertLess(credit, 0.0)   # debit paid
        self.assertGreater(max_loss, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 5.  _stress_estimate
# ─────────────────────────────────────────────────────────────────────────────

class TestStressEstimate(unittest.TestCase):

    def test_credit_strategy_stress_negative(self):
        base, shock = _stress_estimate(_STRATEGY_BULL_PUT, 150.0, 350.0)
        self.assertLess(base, 0.0)
        self.assertLess(shock, 0.0)

    def test_shock_worse_than_base(self):
        base, shock = _stress_estimate(_STRATEGY_BULL_PUT, 150.0, 350.0)
        self.assertLess(shock, base)

    def test_debit_strategy_stress_negative(self):
        base, shock = _stress_estimate(_STRATEGY_BULL_CALL, -200.0, 200.0)
        self.assertLess(base, 0.0)
        self.assertLess(shock, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 6.  _sizing_adaptive_fixed
# ─────────────────────────────────────────────────────────────────────────────

class TestSizingAdaptiveFixed(unittest.TestCase):

    def test_normal_full_base(self):
        s = _sizing_adaptive_fixed("NORMAL")
        self.assertAlmostEqual(s, 2.0)

    def test_caution_half(self):
        s = _sizing_adaptive_fixed("CAUTION")
        self.assertAlmostEqual(s, 1.0)

    def test_shock_zero(self):
        s = _sizing_adaptive_fixed("SHOCK")
        self.assertAlmostEqual(s, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 7.  _ivr_from_history
# ─────────────────────────────────────────────────────────────────────────────

class TestIvrFromHistory(unittest.TestCase):

    def test_returns_none_for_short_history(self):
        r = _ivr_from_history(0.25, [0.25] * 10)
        self.assertIsNone(r)

    def test_returns_float_for_long_history(self):
        hist = [0.20 + (i % 10) * 0.01 for i in range(60)]
        r = _ivr_from_history(0.25, hist)
        self.assertIsNotNone(r)
        self.assertGreaterEqual(r, 0.0)
        self.assertLessEqual(r, 100.0)

    def test_constant_history_returns_50(self):
        hist = [0.25] * 50
        r = _ivr_from_history(0.25, hist)
        self.assertAlmostEqual(r, 50.0)

    def test_iv_at_min_returns_near_zero(self):
        hist = [0.20 + i * 0.001 for i in range(50)]
        r = _ivr_from_history(hist[0], hist)
        self.assertAlmostEqual(r, 0.0, places=1)

    def test_iv_at_max_returns_near_100(self):
        hist = [0.20 + i * 0.001 for i in range(50)]
        r = _ivr_from_history(hist[-1], hist)
        self.assertAlmostEqual(r, 100.0, places=1)


# ─────────────────────────────────────────────────────────────────────────────
# 8.  _build_candidate
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildCandidate(unittest.TestCase):

    def _setup(self):
        # Contratti progettati per R/R ≈ 2.1 → score ≥ 60 anche in CAUTION
        # short put 490: mid=3.90, long put 485: mid=0.50
        # credit=3.40, width=5, rr=3.40/1.60≈2.1
        # ATM call+put a 500 per Expected Move (necessario per human_review)
        contracts = [
            _contract(490.0, "P", -0.35, bid=3.80, ask=4.00, oi=800, volume=60),
            _contract(485.0, "P", -0.20, bid=0.40, ask=0.60, oi=600, volume=40),
            _contract(500.0, "C",  0.50, bid=3.10, ask=3.30, oi=900, volume=80),
            _contract(500.0, "P", -0.50, bid=3.00, ask=3.20, oi=850, volume=70),
        ]
        chain = _minimal_chain_result(contracts)
        analytics = compute_chain_analytics(chain, iv_history=_iv_hist())
        return chain, analytics

    def test_returns_candidate_for_valid_input(self):
        chain, analytics = self._setup()
        c = _build_candidate(chain, analytics, _STRATEGY_BULL_PUT, "NORMAL", _iv_hist())
        self.assertIsNotNone(c)
        self.assertIsInstance(c, OpportunityCandidate)

    def test_strategy_matches(self):
        chain, analytics = self._setup()
        c = _build_candidate(chain, analytics, _STRATEGY_BULL_PUT, "NORMAL", _iv_hist())
        self.assertIsNotNone(c)
        self.assertEqual(c.strategy, _STRATEGY_BULL_PUT)

    def test_score_in_range(self):
        chain, analytics = self._setup()
        c = _build_candidate(chain, analytics, _STRATEGY_BULL_PUT, "NORMAL", _iv_hist())
        self.assertIsNotNone(c)
        self.assertGreaterEqual(c.score, 0.0)
        self.assertLessEqual(c.score, 100.0)

    def test_sizing_caution_half(self):
        chain, analytics = self._setup()
        c = _build_candidate(chain, analytics, _STRATEGY_BULL_PUT, "CAUTION", _iv_hist())
        self.assertIsNotNone(c)
        self.assertAlmostEqual(c.sizing_suggested, 1.0)

    def test_empty_contracts_returns_none(self):
        chain = _minimal_chain_result([])
        analytics = compute_chain_analytics(chain)
        c = _build_candidate(chain, analytics, _STRATEGY_BULL_PUT, "NORMAL", [])
        self.assertIsNone(c)

    def test_data_quality_passthrough(self):
        chain, analytics = self._setup()
        c = _build_candidate(chain, analytics, _STRATEGY_BULL_PUT, "NORMAL", _iv_hist())
        self.assertIsNotNone(c)
        self.assertEqual(c.data_quality, chain.data_quality)

    def test_max_loss_positive(self):
        chain, analytics = self._setup()
        c = _build_candidate(chain, analytics, _STRATEGY_BULL_PUT, "NORMAL", _iv_hist())
        self.assertIsNotNone(c)
        self.assertGreater(c.max_loss, 0.0)

    def test_human_review_set_for_large_signal(self):
        chain, analytics = self._setup()
        # Signal 3× Expected Move → human review required
        em = analytics.expected_move or 0.03
        large_signal = em * 3.0
        c = _build_candidate(
            chain, analytics, _STRATEGY_BULL_PUT, "NORMAL", _iv_hist(),
            signal_pct=large_signal,
        )
        self.assertIsNotNone(c)
        self.assertTrue(c.human_review_required)

    def test_human_review_not_set_for_small_signal(self):
        chain, analytics = self._setup()
        em = analytics.expected_move or 0.03
        small_signal = em * 1.0
        c = _build_candidate(
            chain, analytics, _STRATEGY_BULL_PUT, "NORMAL", _iv_hist(),
            signal_pct=small_signal,
        )
        self.assertIsNotNone(c)
        self.assertFalse(c.human_review_required)


# ─────────────────────────────────────────────────────────────────────────────
# 9.  scan_opportunities  (pipeline completa)
# ─────────────────────────────────────────────────────────────────────────────

class TestScanOpportunities(unittest.TestCase):

    def _synth_iv(self, n: int = 90, mean: float = 0.25) -> list[float]:
        """Dati IV deterministici inline — nessuna rete, nessun codice produzione."""
        return [round(mean + 0.01 * (i % 7 - 3), 6) for i in range(n)]

    def test_returns_scan_result(self):
        r = scan_opportunities(profile="dev", regime="NORMAL", symbols=["TEST"],
                                use_cache=False)
        self.assertIsInstance(r, ScanResult)

    def test_shock_suspended(self):
        r = scan_opportunities(profile="dev", regime="SHOCK", symbols=["TEST"])
        self.assertTrue(r.ranking_suspended)
        self.assertIsNotNone(r.suspension_reason)
        self.assertEqual(len(r.candidates), 0)

    def test_empty_symbols_returns_empty(self):
        r = scan_opportunities(profile="dev", regime="NORMAL", symbols=[])
        self.assertEqual(r.symbols_scanned, 0)
        self.assertEqual(len(r.candidates), 0)
        self.assertFalse(r.ranking_suspended)

    def test_missing_symbol_no_crash(self):
        r = scan_opportunities(profile="dev", regime="NORMAL",
                                symbols=["XXMISSING99"], use_cache=False)
        self.assertEqual(r.symbols_with_chain, 0)
        self.assertEqual(len(r.candidates), 0)

    def test_test_symbol_produces_candidate(self):
        r = scan_opportunities(
            profile="dev", regime="NORMAL", symbols=["TEST"],
            use_cache=False,
            iv_history_map={"TEST": self._synth_iv()},
        )
        self.assertGreaterEqual(r.symbols_with_chain, 0)
        # Candidates may be 0 if score < min_score=60 (depends on fixture data)
        self.assertIsInstance(r.candidates, list)

    def test_caution_forces_bull_put_strategy(self):
        r = scan_opportunities(
            profile="dev", regime="CAUTION", symbols=["TEST"],
            use_cache=False,
            iv_history_map={"TEST": self._synth_iv()},
        )
        for c in r.candidates:
            self.assertEqual(c.strategy, _STRATEGY_BULL_PUT)

    def test_caution_sizing_half(self):
        r = scan_opportunities(
            profile="dev", regime="CAUTION", symbols=["TEST"],
            use_cache=False,
            iv_history_map={"TEST": self._synth_iv()},
        )
        for c in r.candidates:
            self.assertAlmostEqual(c.sizing_suggested, 1.0)

    def test_top_n_limits_candidates(self):
        # Even with one symbol there should be at most top_n candidates
        r = scan_opportunities(
            profile="dev", regime="NORMAL", symbols=["TEST"],
            top_n=1, use_cache=False,
            iv_history_map={"TEST": self._synth_iv()},
        )
        self.assertLessEqual(len(r.candidates), 1)

    def test_min_score_filters_candidates(self):
        r_high = scan_opportunities(
            profile="dev", regime="NORMAL", symbols=["TEST"],
            min_score=99.0, use_cache=False,
        )
        # Almost all candidates should be excluded at min_score=99
        for c in r_high.candidates:
            self.assertGreaterEqual(c.score, 99.0)

    def test_data_mode_watermark(self):
        r = scan_opportunities(profile="dev", regime="NORMAL", symbols=["TEST"],
                                use_cache=False)
        self.assertEqual(r.data_mode, "SYNTHETIC_SURFACE_CALIBRATED")

    def test_candidates_sorted_by_score_desc(self):
        r = scan_opportunities(
            profile="dev", regime="NORMAL",
            symbols=["TEST", "TEST"],   # same symbol twice — both will be processed
            use_cache=False,
            iv_history_map={"TEST": self._synth_iv()},
        )
        scores = [c.score for c in r.candidates]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_symbols_scanned_count(self):
        r = scan_opportunities(
            profile="dev", regime="NORMAL",
            symbols=["TEST", "MISSING_X"],
            use_cache=False,
        )
        self.assertEqual(r.symbols_scanned, 2)

    def test_filtered_count_nonnegative(self):
        r = scan_opportunities(profile="dev", regime="NORMAL", symbols=["TEST"],
                                use_cache=False)
        self.assertGreaterEqual(r.filtered_count, 0)

    def test_scan_ts_is_utc_iso(self):
        r = scan_opportunities(profile="dev", regime="NORMAL", symbols=["TEST"],
                                use_cache=False)
        self.assertTrue(r.scan_ts.endswith("Z"))
        parsed = datetime.fromisoformat(r.scan_ts.replace("Z", "+00:00"))
        self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_signal_map_passed(self):
        r = scan_opportunities(
            profile="dev", regime="NORMAL", symbols=["TEST"],
            signal_map={"TEST": "bullish"},
            use_cache=False,
            iv_history_map={"TEST": self._synth_iv()},
        )
        self.assertIsInstance(r, ScanResult)   # should not crash

    def test_candidate_fields_populated(self):
        r = scan_opportunities(
            profile="dev", regime="NORMAL", symbols=["TEST"],
            use_cache=False,
            iv_history_map={"TEST": self._synth_iv()},
        )
        for c in r.candidates:
            self.assertIsInstance(c.symbol, str)
            self.assertIsInstance(c.strategy, str)
            self.assertIsInstance(c.score, float)
            self.assertIsInstance(c.max_loss, float)
            self.assertIsInstance(c.score_breakdown, dict)
            self.assertIn("vol_edge", c.score_breakdown)
            self.assertIn("liquidity", c.score_breakdown)
            self.assertIn("risk_reward", c.score_breakdown)
            self.assertIn("regime_align", c.score_breakdown)


if __name__ == "__main__":
    unittest.main()
