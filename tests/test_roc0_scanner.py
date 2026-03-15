"""
tests/test_roc0_scanner.py — ROC0-T4

Unit tests for strategy/opportunity_scanner.py:
  - apply_hard_filters
  - compute_iv_zscore
  - compute_expected_move
  - compute_chain_analytics  (end-to-end)
  - _save_cache / _load_cache  (roundtrip)
  - fetch_and_filter_chain    (CSV-based, no IBKR, profile=dev)

All tests run without IBKR, network, or external services.
DATA_MODE is forced to SYNTHETIC_SURFACE_CALIBRATED via env var.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

# Force dev data mode for the entire module
os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from strategy.opportunity_scanner import (
    CACHE_TTL_HOURS,
    DELTA_LONG_MAX,
    DELTA_LONG_MIN,
    DEFAULT_MAX_SPREAD_PCT,
    DEFAULT_MIN_OI,
    DEFAULT_MIN_VOLUME,
    HARD_MAX_DTE,
    HARD_MIN_DTE,
    PAPER_LIVE_MIN_OI,
    Z_CHEAP_THRESHOLD,
    Z_EXPENSIVE_THRESHOLD,
    ChainAnalytics,
    ChainFilterResult,
    FilterParams,
    FilterRejectStats,
    OptionContract,
    _load_cache,
    _save_cache,
    apply_hard_filters,
    compute_chain_analytics,
    compute_expected_move,
    compute_iv_zscore,
    fetch_and_filter_chain,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _future_expiry(days: int = 34) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _make_contract(
    *,
    symbol: str = "SPY",
    expiry: str | None = None,
    dte: int = 30,
    strike: float = 500.0,
    right: str = "C",
    bid: float = 2.0,
    ask: float = 2.20,
    delta: float = 0.30,
    gamma: float = 0.01,
    theta: float = -0.05,
    vega: float = 0.30,
    iv: float = 0.25,
    open_interest: int = 600,
    volume: int = 50,
    underlying_price: float = 500.0,
) -> OptionContract:
    if expiry is None:
        expiry = _future_expiry(dte)
    return OptionContract(
        symbol=symbol,
        expiry=expiry,
        dte=dte,
        strike=strike,
        right=right,
        bid=bid,
        ask=ask,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        iv=iv,
        open_interest=open_interest,
        volume=volume,
        underlying_price=underlying_price,
    )


def _atm_pair(
    underlying: float = 500.0,
    call_bid: float = 3.10,
    call_ask: float = 3.30,
    put_bid: float = 3.00,
    put_ask: float = 3.20,
    dte: int = 34,
) -> list[OptionContract]:
    exp = _future_expiry(dte)
    call = _make_contract(
        strike=underlying, right="C", bid=call_bid, ask=call_ask,
        delta=0.50, dte=dte, expiry=exp, underlying_price=underlying,
    )
    put = _make_contract(
        strike=underlying, right="P", bid=put_bid, ask=put_ask,
        delta=-0.50, dte=dte, expiry=exp, underlying_price=underlying,
    )
    return [call, put]


# ─────────────────────────────────────────────────────────────────────────────
# 1.  OptionContract properties
# ─────────────────────────────────────────────────────────────────────────────

class TestOptionContractProperties(unittest.TestCase):

    def test_mid(self):
        c = _make_contract(bid=2.0, ask=2.40)
        self.assertAlmostEqual(c.mid, 2.20, places=4)

    def test_spread_pct(self):
        c = _make_contract(bid=2.0, ask=2.40)
        # spread = 0.40, mid = 2.20 → 0.40/2.20*100 ≈ 18.18%
        self.assertAlmostEqual(c.spread_pct, 18.182, places=2)

    def test_spread_pct_zero_mid(self):
        c = _make_contract(bid=0.0, ask=0.0)
        self.assertEqual(c.spread_pct, 9999.0)

    def test_delta_abs(self):
        put = _make_contract(delta=-0.35)
        self.assertAlmostEqual(put.delta_abs, 0.35, places=4)


# ─────────────────────────────────────────────────────────────────────────────
# 2.  apply_hard_filters
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyHardFilters(unittest.TestCase):

    def _default_params(self):
        return FilterParams()

    def test_good_contract_passes(self):
        contracts = [_make_contract()]
        kept, stats = apply_hard_filters(contracts)
        self.assertEqual(len(kept), 1)
        self.assertEqual(stats.total_rejected, 0)

    def test_iv_zero_rejected(self):
        contracts = [_make_contract(iv=0.0)]
        kept, stats = apply_hard_filters(contracts)
        self.assertEqual(len(kept), 0)
        self.assertEqual(stats.iv_missing, 1)

    def test_iv_negative_rejected(self):
        contracts = [_make_contract(iv=-0.01)]
        kept, stats = apply_hard_filters(contracts)
        self.assertEqual(len(kept), 0)
        self.assertEqual(stats.iv_missing, 1)

    def test_dte_below_hard_min_rejected(self):
        contracts = [_make_contract(dte=HARD_MIN_DTE - 1)]
        kept, stats = apply_hard_filters(contracts)
        self.assertEqual(len(kept), 0)
        self.assertEqual(stats.dte_out, 1)

    def test_dte_above_hard_max_rejected(self):
        contracts = [_make_contract(dte=HARD_MAX_DTE + 1)]
        kept, stats = apply_hard_filters(contracts)
        self.assertEqual(len(kept), 0)
        self.assertEqual(stats.dte_out, 1)

    def test_dte_at_hard_boundaries_accepted(self):
        # FilterParams deve usare i limiti hard come min/max per testare i boundary
        # max_spread_cost_per_dte=999 → test isolato su DTE, non su spread
        params = FilterParams(min_dte=HARD_MIN_DTE, max_dte=HARD_MAX_DTE, max_spread_cost_per_dte=999.0)
        lo = _make_contract(dte=HARD_MIN_DTE)
        hi = _make_contract(dte=HARD_MAX_DTE)
        kept, stats = apply_hard_filters([lo, hi], params)
        self.assertEqual(len(kept), 2)
        self.assertEqual(stats.dte_out, 0)

    def test_spread_too_wide_rejected(self):
        # spread_pct > 10%: bid=1.0, ask=1.30 → spread=0.30, mid=1.15 → 26%
        contracts = [_make_contract(bid=1.0, ask=1.30)]
        kept, stats = apply_hard_filters(contracts)
        self.assertEqual(len(kept), 0)
        self.assertEqual(stats.spread_pct, 1)

    def test_spread_exactly_at_max_accepted(self):
        # target exactly 10%: mid=2.0, spread=0.20 → bid=1.90, ask=2.10
        contracts = [_make_contract(bid=1.90, ask=2.10)]
        kept, stats = apply_hard_filters(contracts)
        self.assertEqual(len(kept), 1)

    def test_oi_too_low_rejected(self):
        contracts = [_make_contract(open_interest=DEFAULT_MIN_OI - 1)]
        kept, stats = apply_hard_filters(contracts)
        self.assertEqual(len(kept), 0)
        self.assertEqual(stats.oi_low, 1)

    def test_volume_too_low_rejected(self):
        contracts = [_make_contract(volume=DEFAULT_MIN_VOLUME - 1)]
        kept, stats = apply_hard_filters(contracts)
        self.assertEqual(len(kept), 0)
        self.assertEqual(stats.volume_low, 1)

    def test_delta_below_min_rejected(self):
        contracts = [_make_contract(delta=DELTA_LONG_MIN - 0.01)]
        kept, stats = apply_hard_filters(contracts)
        self.assertEqual(len(kept), 0)
        self.assertEqual(stats.delta_out, 1)

    def test_delta_above_max_rejected(self):
        contracts = [_make_contract(delta=DELTA_LONG_MAX + 0.01)]
        kept, stats = apply_hard_filters(contracts)
        self.assertEqual(len(kept), 0)
        self.assertEqual(stats.delta_out, 1)

    def test_put_negative_delta_uses_abs(self):
        # delta=-0.30 → abs=0.30 → within [0.15, 0.50]
        contracts = [_make_contract(delta=-0.30)]
        kept, stats = apply_hard_filters(contracts)
        self.assertEqual(len(kept), 1)
        self.assertEqual(stats.delta_out, 0)

    def test_filter_order_iv_before_dte(self):
        # Contract that fails both IV and DTE — should be counted in iv_missing
        c = _make_contract(iv=0.0, dte=5)
        _, stats = apply_hard_filters([c])
        self.assertEqual(stats.iv_missing, 1)
        self.assertEqual(stats.dte_out, 0)

    def test_total_raw_matches_input(self):
        contracts = [_make_contract() for _ in range(5)]
        _, stats = apply_hard_filters(contracts)
        self.assertEqual(stats.total_raw, 5)

    def test_reject_stats_total_rejected(self):
        bad_iv = _make_contract(iv=0.0)
        bad_dte = _make_contract(dte=5)
        good = _make_contract()
        _, stats = apply_hard_filters([bad_iv, bad_dte, good])
        self.assertEqual(stats.total_rejected, 2)
        self.assertEqual(stats.total_raw, 3)

    def test_custom_params_stricter_oi(self):
        params = FilterParams(min_oi=PAPER_LIVE_MIN_OI)
        contracts = [_make_contract(open_interest=200)]
        kept, stats = apply_hard_filters(contracts, params)
        self.assertEqual(len(kept), 0)
        self.assertEqual(stats.oi_low, 1)

    def test_empty_input(self):
        kept, stats = apply_hard_filters([])
        self.assertEqual(kept, [])
        self.assertEqual(stats.total_raw, 0)
        self.assertEqual(stats.total_rejected, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 3.  compute_iv_zscore
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeIvZscore(unittest.TestCase):

    def _history(self, n: int, mean: float = 0.25, std: float = 0.05) -> list[float]:
        """Generate deterministic history of length n around mean±std."""
        import random
        rng = random.Random(42)
        return [mean + rng.gauss(0, std) for _ in range(n)]

    def test_returns_float_with_sufficient_history(self):
        history = self._history(35)
        z = compute_iv_zscore(0.30, history, 30)
        self.assertIsNotNone(z)
        self.assertIsInstance(z, float)

    def test_returns_none_if_history_too_short(self):
        z = compute_iv_zscore(0.30, [0.25, 0.26, 0.24], 30)
        self.assertIsNone(z)

    def test_returns_none_for_empty_history(self):
        z = compute_iv_zscore(0.30, [], 30)
        self.assertIsNone(z)

    def test_returns_none_if_std_zero(self):
        # All same values → std = 0
        z = compute_iv_zscore(0.25, [0.25] * 35, 30)
        self.assertIsNone(z)

    def test_positive_z_when_iv_above_mean(self):
        history = [0.25] * 29 + [0.26]  # mean ≈ 0.25, std very small
        # Use manual history with known variance
        history = [0.20] * 15 + [0.30] * 15  # mean=0.25, std>0
        z = compute_iv_zscore(0.40, history, 30)
        self.assertIsNotNone(z)
        self.assertGreater(z, 0)

    def test_negative_z_when_iv_below_mean(self):
        history = [0.20] * 15 + [0.30] * 15
        z = compute_iv_zscore(0.10, history, 30)
        self.assertIsNotNone(z)
        self.assertLess(z, 0)

    def test_cheap_zone_below_threshold(self):
        # IV way below history → very negative z
        history = [0.30] * 35
        # Use variance: manually pick min std: mix values
        history = [0.25 + (i % 5) * 0.02 for i in range(35)]
        z = compute_iv_zscore(0.01, history, 30)
        self.assertIsNotNone(z)
        self.assertLess(z, Z_CHEAP_THRESHOLD)

    def test_expensive_zone_above_threshold(self):
        history = [0.25 + (i % 5) * 0.02 for i in range(35)]
        z = compute_iv_zscore(0.80, history, 30)
        self.assertIsNotNone(z)
        self.assertGreater(z, Z_EXPENSIVE_THRESHOLD)

    def test_uses_only_last_n_values(self):
        # Build history where last 30 values have mean=0.30, earlier have mean=0.10
        old = [0.10] * 10
        recent = [0.30] * 30
        history = old + recent
        z = compute_iv_zscore(0.30, history, 30)
        # Mean of last 30 ≈ 0.30 → z should be near 0 if recent is homogeneous
        # But all same → std=0 → None; add tiny variance
        recent_var = [0.28 + (i % 5) * 0.01 for i in range(30)]
        history2 = old + recent_var
        z2 = compute_iv_zscore(0.30, history2, 30)
        # z2 should be close to 0 (iv ≈ mean of last 30)
        self.assertIsNotNone(z2)
        self.assertLess(abs(z2), 2.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4.  compute_expected_move
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeExpectedMove(unittest.TestCase):

    def test_basic_expected_move(self):
        contracts = _atm_pair(underlying=500.0, call_bid=3.10, call_ask=3.30,
                               put_bid=3.00, put_ask=3.20)
        em_dec, em_abs, atm_strike, c_mid, p_mid = compute_expected_move(contracts, 500.0)
        # call_mid = 3.20, put_mid = 3.10 → em_abs = 6.30, em_dec = 6.30/500 = 0.0126
        self.assertIsNotNone(em_dec)
        self.assertAlmostEqual(c_mid, 3.20, places=4)
        self.assertAlmostEqual(p_mid, 3.10, places=4)
        self.assertAlmostEqual(em_abs, 6.30, places=4)
        self.assertAlmostEqual(em_dec, 0.0126, places=4)
        self.assertAlmostEqual(atm_strike, 500.0, places=4)

    def test_atm_strike_selection(self):
        # Underlying = 498.0 → closest strike is 500.0
        c1 = _make_contract(strike=490.0, right="C")
        c2 = _make_contract(strike=500.0, right="C")
        c3 = _make_contract(strike=500.0, right="P", delta=-0.50)
        c4 = _make_contract(strike=510.0, right="P", delta=-0.40)
        _, _, atm_strike, _, _ = compute_expected_move([c1, c2, c3, c4], 498.0)
        self.assertAlmostEqual(atm_strike, 500.0, places=1)

    def test_empty_contracts_returns_none(self):
        result = compute_expected_move([], 500.0)
        self.assertEqual(result, (None, None, None, None, None))

    def test_zero_underlying_returns_none(self):
        contracts = _atm_pair()
        result = compute_expected_move(contracts, 0.0)
        self.assertEqual(result, (None, None, None, None, None))

    def test_missing_put_returns_none_em(self):
        call = _make_contract(strike=500.0, right="C", bid=3.10, ask=3.30)
        em_dec, em_abs, atm_strike, c_mid, p_mid = compute_expected_move([call], 500.0)
        self.assertIsNone(em_dec)
        self.assertIsNone(em_abs)

    def test_zero_bid_ask_returns_none_em(self):
        call = _make_contract(strike=500.0, right="C", bid=0.0, ask=0.0)
        put = _make_contract(strike=500.0, right="P", bid=0.0, ask=0.0, delta=-0.50)
        em_dec, em_abs, _, _, _ = compute_expected_move([call, put], 500.0)
        self.assertIsNone(em_dec)


# ─────────────────────────────────────────────────────────────────────────────
# 5.  compute_chain_analytics  (end-to-end)
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeChainAnalytics(unittest.TestCase):

    def _make_result(self, contracts: list[OptionContract]) -> ChainFilterResult:
        underlying = contracts[0].underlying_price if contracts else 500.0
        return ChainFilterResult(
            symbol="SPY",
            profile="dev",
            data_mode="SYNTHETIC_SURFACE_CALIBRATED",
            fetched_at=datetime.now(timezone.utc).isoformat(),
            expiry=contracts[0].expiry if contracts else "",
            dte=contracts[0].dte if contracts else 0,
            underlying_price=underlying,
            contracts_raw=len(contracts),
            contracts_kept=contracts,
        )

    def test_empty_result_returns_empty_analytics(self):
        result = self._make_result([])
        analytics = compute_chain_analytics(result)
        self.assertIsInstance(analytics, ChainAnalytics)
        self.assertIsNone(analytics.expected_move)
        self.assertIsNone(analytics.iv_zscore_30)
        self.assertIsNone(analytics.iv_zscore_60)

    def test_expected_move_computed(self):
        contracts = _atm_pair(underlying=500.0)
        result = self._make_result(contracts)
        analytics = compute_chain_analytics(result)
        self.assertIsNotNone(analytics.expected_move)
        self.assertGreater(analytics.expected_move, 0.0)
        self.assertIsNotNone(analytics.atm_strike)

    def test_zscore_none_without_history(self):
        contracts = _atm_pair()
        result = self._make_result(contracts)
        analytics = compute_chain_analytics(result, iv_history=None)
        self.assertIsNone(analytics.iv_zscore_30)
        self.assertIsNone(analytics.iv_zscore_60)
        self.assertEqual(analytics.iv_interp_30, "unknown")

    def test_zscore_computed_with_history(self):
        contracts = _atm_pair()
        result = self._make_result(contracts)
        # Give 65 values to satisfy both 30d and 60d windows
        iv_history = [0.25 + (i % 7) * 0.01 for i in range(65)]
        analytics = compute_chain_analytics(result, iv_history=iv_history)
        self.assertIsNotNone(analytics.iv_zscore_30)
        self.assertIsNotNone(analytics.iv_zscore_60)
        self.assertIn(analytics.iv_interp_30, ("cheap", "fair", "expensive"))
        self.assertIn(analytics.iv_interp_60, ("cheap", "fair", "expensive"))

    def test_history_too_short_for_60d_window(self):
        contracts = _atm_pair()
        result = self._make_result(contracts)
        iv_history = [0.25 + (i % 5) * 0.01 for i in range(35)]  # enough for 30 only
        analytics = compute_chain_analytics(result, iv_history=iv_history)
        self.assertIsNotNone(analytics.iv_zscore_30)
        self.assertIsNone(analytics.iv_zscore_60)

    def test_iv_current_set_from_atm_contracts(self):
        contracts = _atm_pair(underlying=500.0)
        result = self._make_result(contracts)
        analytics = compute_chain_analytics(result)
        self.assertIsNotNone(analytics.iv_current)
        self.assertGreater(analytics.iv_current, 0.0)

    def test_history_len_reflects_window(self):
        contracts = _atm_pair()
        result = self._make_result(contracts)
        iv_history = [0.25 + (i % 7) * 0.01 for i in range(65)]
        analytics = compute_chain_analytics(result, iv_history=iv_history)
        self.assertEqual(analytics.history_len_30, 30)
        self.assertEqual(analytics.history_len_60, 60)


# ─────────────────────────────────────────────────────────────────────────────
# 6.  Cache roundtrip
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheRoundtrip(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_cache_dir = None

    def tearDown(self):
        self._tmpdir.cleanup()

    def _patch_cache_dir(self):
        """Return a context manager patching CACHE_DIR to a temp directory."""
        import strategy.opportunity_scanner as mod
        return patch.object(mod, "CACHE_DIR", Path(self._tmpdir.name))

    def test_save_and_load_roundtrip(self):
        contracts = [_make_contract()]
        with self._patch_cache_dir():
            _save_cache("ROUNDTRIP", contracts)
            loaded, age = _load_cache("ROUNDTRIP")
        self.assertIsNotNone(loaded)
        self.assertIsNotNone(age)
        self.assertEqual(len(loaded), 1)
        self.assertAlmostEqual(age, 0.0, places=1)

    def test_loaded_contract_fields_match(self):
        c = _make_contract(symbol="SPY", strike=450.0, right="P", iv=0.32, dte=28)
        with self._patch_cache_dir():
            _save_cache("FIELDS", [c])
            loaded, _ = _load_cache("FIELDS")
        self.assertIsNotNone(loaded)
        lc = loaded[0]
        self.assertEqual(lc.symbol, "SPY")
        self.assertAlmostEqual(lc.strike, 450.0)
        self.assertEqual(lc.right, "P")
        self.assertAlmostEqual(lc.iv, 0.32)

    def test_load_returns_none_for_missing_file(self):
        with self._patch_cache_dir():
            loaded, age = _load_cache("NONEXISTENT")
        self.assertIsNone(loaded)
        self.assertIsNone(age)

    def test_stale_cache_returns_none(self):
        contracts = [_make_contract()]
        import strategy.opportunity_scanner as mod
        with self._patch_cache_dir():
            _save_cache("STALE", contracts)
            # Backdating captured_at by > TTL
            path = mod._cache_path("STALE")
            data = json.loads(path.read_text())
            stale_ts = (
                datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS + 1)
            ).isoformat().replace("+00:00", "Z")
            data["captured_at"] = stale_ts
            path.write_text(json.dumps(data))
            loaded, age = _load_cache("STALE")
        self.assertIsNone(loaded)
        self.assertIsNone(age)

    def test_cache_file_contains_captured_at(self):
        contracts = [_make_contract()]
        import strategy.opportunity_scanner as mod
        with self._patch_cache_dir():
            _save_cache("TSCHECK", contracts)
            path = mod._cache_path("TSCHECK")
            data = json.loads(path.read_text())
        self.assertIn("captured_at", data)
        self.assertIn("expires_at", data)
        self.assertIn("contracts", data)


# ─────────────────────────────────────────────────────────────────────────────
# 7.  fetch_and_filter_chain — CSV path (dev, no IBKR)
# ─────────────────────────────────────────────────────────────────────────────

class TestFetchAndFilterChainDev(unittest.TestCase):
    """
    Tests that use the real chain_TEST.csv fixture at data/providers/chain_TEST.csv.
    Profile=dev → CSV path always, no IBKR, no cache write.
    """

    def test_returns_chain_filter_result(self):
        result = fetch_and_filter_chain("TEST", profile="dev", use_cache=False)
        self.assertIsInstance(result, ChainFilterResult)

    def test_symbol_uppercase(self):
        result = fetch_and_filter_chain("test", profile="dev", use_cache=False)
        self.assertEqual(result.symbol, "TEST")

    def test_data_mode_watermark_in_result(self):
        result = fetch_and_filter_chain("TEST", profile="dev", use_cache=False)
        self.assertEqual(result.data_mode, "SYNTHETIC_SURFACE_CALIBRATED")

    def test_source_is_csv_for_dev(self):
        result = fetch_and_filter_chain("TEST", profile="dev", use_cache=False)
        self.assertEqual(result.source, "csv_delayed")

    def test_data_quality_synthetic_for_dev(self):
        result = fetch_and_filter_chain("TEST", profile="dev", use_cache=False)
        self.assertEqual(result.data_quality, "synthetic")

    def test_contracts_raw_nonzero_for_known_csv(self):
        result = fetch_and_filter_chain("TEST", profile="dev", use_cache=False)
        self.assertGreater(result.contracts_raw, 0)

    def test_underlying_price_set(self):
        result = fetch_and_filter_chain("TEST", profile="dev", use_cache=False)
        self.assertGreater(result.underlying_price, 0.0)

    def test_kept_contracts_all_pass_filters(self):
        result = fetch_and_filter_chain("TEST", profile="dev", use_cache=False)
        params = FilterParams()
        for c in result.contracts_kept:
            self.assertGreater(c.iv, 0.0)
            self.assertGreaterEqual(c.dte, max(params.min_dte, HARD_MIN_DTE))
            self.assertLessEqual(c.dte, min(params.max_dte, HARD_MAX_DTE))
            self.assertLessEqual(c.spread_pct, params.max_spread_pct)
            self.assertGreaterEqual(c.open_interest, params.min_oi)
            self.assertGreaterEqual(c.volume, params.min_volume)
            self.assertGreaterEqual(c.delta_abs, params.delta_min)
            self.assertLessEqual(c.delta_abs, params.delta_max)

    def test_unknown_symbol_returns_empty_chain(self):
        result = fetch_and_filter_chain("XXXX_MISSING", profile="dev", use_cache=False)
        self.assertEqual(result.contracts_raw, 0)
        self.assertEqual(result.contracts_kept, [])

    def test_paper_profile_upgrades_min_oi(self):
        """
        Paper profile auto-upgrades min_oi to 500.
        With our TEST CSV (OI 280–2500), most should still pass.
        """
        result = fetch_and_filter_chain("TEST", profile="paper", use_cache=False)
        for c in result.contracts_kept:
            self.assertGreaterEqual(c.open_interest, PAPER_LIVE_MIN_OI)

    def test_custom_params_accepted(self):
        params = FilterParams(delta_min=0.40, delta_max=0.60)
        result = fetch_and_filter_chain(
            "TEST", profile="dev", params=params, use_cache=False
        )
        for c in result.contracts_kept:
            self.assertGreaterEqual(c.delta_abs, 0.40)

    def test_dte_range_respected(self):
        result = fetch_and_filter_chain(
            "TEST", profile="dev", use_cache=False, min_dte=20, max_dte=45
        )
        for c in result.contracts_kept:
            self.assertGreaterEqual(c.dte, 20)
            self.assertLessEqual(c.dte, 45)

    def test_fetched_at_is_utc_iso(self):
        result = fetch_and_filter_chain("TEST", profile="dev", use_cache=False)
        # Should parse as ISO and end with 'Z'
        self.assertTrue(result.fetched_at.endswith("Z"))
        # Verify it parses
        parsed = datetime.fromisoformat(result.fetched_at.replace("Z", "+00:00"))
        self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_reject_stats_total_raw_consistent(self):
        result = fetch_and_filter_chain("TEST", profile="dev", use_cache=False)
        self.assertEqual(
            result.contracts_raw,
            result.reject_stats.total_raw,
        )
        self.assertEqual(
            result.contracts_raw,
            len(result.contracts_kept) + result.reject_stats.total_rejected,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 8.  Integration: fetch → analytics pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestFetchThenAnalytics(unittest.TestCase):

    def test_pipeline_produces_expected_move(self):
        result = fetch_and_filter_chain("TEST", profile="dev", use_cache=False)
        if not result.contracts_kept:
            self.skipTest("No contracts passed filters — check chain_TEST.csv fixture")
        analytics = compute_chain_analytics(result)
        # Expected move should be set if ATM pair exists in filtered contracts
        # (may be None if both ATM call and put don't survive filters)
        self.assertIsInstance(analytics, ChainAnalytics)
        self.assertEqual(analytics.symbol, "TEST")

    def test_pipeline_zscore_with_history(self):
        result = fetch_and_filter_chain("TEST", profile="dev", use_cache=False)
        if not result.contracts_kept:
            self.skipTest("No contracts passed filters")
        iv_history = [0.26 + (i % 8) * 0.005 for i in range(65)]
        analytics = compute_chain_analytics(result, iv_history=iv_history)
        # With 65 values both windows should compute (if iv_current is set)
        if analytics.iv_current is not None:
            self.assertIsNotNone(analytics.iv_zscore_30)
            self.assertIsNotNone(analytics.iv_zscore_60)


if __name__ == "__main__":
    unittest.main()
