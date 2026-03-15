"""
tests/test_roc12_spread_dte_filter.py — ROC12

Verifica il filtro spread_cost_per_dte in apply_hard_filters():
  - property spread_cost_per_dte su OptionContract
  - contratti con spread alto a basso DTE vengono rigettati
  - stesso spread a DTE alto viene accettato
  - statistiche spread_cost_dte contabilizzate correttamente
  - coesistenza con filtro spread_pct assoluto
  - FilterParams.max_spread_cost_per_dte configurabile
  - DTE = 0 → spread_cost_per_dte = 9999 (edge case)
"""
from __future__ import annotations

import math
import unittest
from dataclasses import replace

from strategy.opportunity_scanner import (
    DEFAULT_MAX_SPREAD_COST_PER_DTE,
    DEFAULT_MAX_SPREAD_PCT,
    FilterParams,
    FilterRejectStats,
    OptionContract,
    apply_hard_filters,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _contract(
    dte: int = 30,
    bid: float = 1.00,
    ask: float = 1.20,    # spread = 0.20, mid = 1.10 → spread_pct ≈ 18%... no
    strike: float = 490.0,
    right: str = "P",
    delta: float = -0.30,
    iv: float = 0.28,
    oi: int = 600,
    volume: int = 50,
    underlying: float = 500.0,
) -> OptionContract:
    return OptionContract(
        symbol="SPY", expiry="2026-04-17", dte=dte,
        strike=strike, right=right,
        bid=bid, ask=ask,
        delta=delta, gamma=0.01, theta=-0.05, vega=0.20,
        iv=iv, open_interest=oi, volume=volume,
        underlying_price=underlying,
    )


def _permissive_params(**overrides) -> FilterParams:
    """Params con soglie molto larghe salvo quelle in test."""
    base = dict(
        min_dte=14, max_dte=60,
        min_oi=10, min_volume=1,
        max_spread_pct=DEFAULT_MAX_SPREAD_PCT,
        max_spread_cost_per_dte=DEFAULT_MAX_SPREAD_COST_PER_DTE,
        delta_min=0.05, delta_max=0.70,
    )
    base.update(overrides)
    return FilterParams(**base)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Property spread_cost_per_dte
# ─────────────────────────────────────────────────────────────────────────────

class TestSpreadCostPerDteProperty(unittest.TestCase):

    def test_basic_value(self):
        # bid=1.00, ask=1.20 → mid=1.10, spread=0.20, spread_pct=18.18%
        # spread_cost_per_dte = 18.18 / 30 = 0.606
        c = _contract(bid=1.00, ask=1.20, dte=30)
        self.assertAlmostEqual(c.spread_cost_per_dte, c.spread_pct / 30, places=3)

    def test_lower_dte_higher_cost(self):
        """Stesso spread → DTE minore = cost_per_dte maggiore."""
        c_short = _contract(bid=2.00, ask=2.20, dte=15)
        c_long = _contract(bid=2.00, ask=2.20, dte=45)
        self.assertGreater(c_short.spread_cost_per_dte, c_long.spread_cost_per_dte)

    def test_dte_zero_returns_sentinel(self):
        c = _contract(dte=0)
        self.assertEqual(c.spread_cost_per_dte, 9999.0)

    def test_zero_mid_returns_sentinel(self):
        c = _contract(bid=0.0, ask=0.0, dte=30)
        self.assertEqual(c.spread_cost_per_dte, 9999.0)

    def test_tight_spread_low_cost(self):
        # bid=2.00, ask=2.04 → spread_pct ≈ 2% → cost/dte a 30 = 0.067
        c = _contract(bid=2.00, ask=2.04, dte=30)
        self.assertLess(c.spread_cost_per_dte, 0.10)

    def test_value_formula(self):
        c = _contract(bid=1.50, ask=1.80, dte=20)
        expected = c.spread_pct / 20
        self.assertAlmostEqual(c.spread_cost_per_dte, expected, places=3)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Il filtro rejetta correttamente
# ─────────────────────────────────────────────────────────────────────────────

class TestSpreadDteFilterRejects(unittest.TestCase):

    def _filtered(self, c: OptionContract, max_cost: float = DEFAULT_MAX_SPREAD_COST_PER_DTE):
        params = _permissive_params(max_spread_cost_per_dte=max_cost)
        kept, stats = apply_hard_filters([c], params)
        return kept, stats

    def test_high_spread_low_dte_rejected(self):
        """8% spread a 14 DTE: cost_per_dte ≈ 0.57 > 0.50 → rigettato."""
        # bid=1.0, ask=1.16 → spread=0.16, mid=1.08, spread_pct≈14.8%... uso valori esatti
        # Voglio spread_pct = 8% → bid=1.96, ask=2.04 (mid=2.00, spread=0.08)
        c = _contract(bid=1.96, ask=2.04, dte=14)
        # spread_pct = (0.08/2.00)*100 = 4% → cost = 4/14 = 0.286 < 0.50 → passa
        # Uso spread più alto: bid=1.80, ask=2.20 → mid=2.00, spread=0.40, pct=20% > 10% → bloccato da spread_pct
        # Uso spread = 7%: bid=1.86, ask=1.99 → mid=1.925, spread=0.13, pct=6.75%, cost=6.75/14=0.48 < 0.50
        # Uso 8%: bid=1.84, ask=1.99 → mid=1.915, spread=0.15, pct=7.8%, cost=7.8/14=0.56 → rigettato
        c2 = _contract(bid=1.84, ask=1.99, dte=14)
        kept, stats = self._filtered(c2)
        self.assertEqual(len(kept), 0)
        self.assertGreater(stats.spread_cost_dte, 0)

    def test_same_spread_high_dte_accepted(self):
        """Stesso spread ma 45 DTE: cost basso → accettato."""
        c = _contract(bid=1.84, ask=1.99, dte=45)
        # cost = 7.8/45 = 0.17 < 0.50 → accettato
        kept, stats = self._filtered(c)
        self.assertEqual(len(kept), 1)
        self.assertEqual(stats.spread_cost_dte, 0)

    def test_tight_spread_any_dte_accepted(self):
        """Spread stretto (2%) anche a 14 DTE: cost=2/14=0.14 → accettato."""
        c = _contract(bid=1.98, ask=2.02, dte=14)
        kept, stats = self._filtered(c)
        self.assertEqual(len(kept), 1)
        self.assertEqual(stats.spread_cost_dte, 0)

    def test_stat_counter_increments_once_per_rejection(self):
        c1 = _contract(bid=1.84, ask=1.99, dte=14)
        c2 = _contract(bid=1.84, ask=1.99, dte=14)
        params = _permissive_params(max_spread_cost_per_dte=0.50)
        _, stats = apply_hard_filters([c1, c2], params)
        self.assertEqual(stats.spread_cost_dte, 2)

    def test_threshold_configurable(self):
        """Con soglia 0.10 (molto severa) anche 45 DTE a spread 7% viene rigettato."""
        c = _contract(bid=1.84, ask=1.99, dte=45)  # cost ≈ 0.17
        kept, _ = self._filtered(c, max_cost=0.10)
        self.assertEqual(len(kept), 0)

    def test_threshold_0_rejects_all_nonzero(self):
        """Soglia 0 → qualsiasi spread > 0 viene rigettato."""
        c = _contract(bid=1.98, ask=2.02, dte=45)
        kept, stats = self._filtered(c, max_cost=0.0)
        self.assertEqual(len(kept), 0)
        self.assertGreater(stats.spread_cost_dte, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Coesistenza con filtro spread_pct assoluto
# ─────────────────────────────────────────────────────────────────────────────

class TestCoexistenceWithAbsoluteFilter(unittest.TestCase):

    def test_absolute_hits_before_dte_adjusted(self):
        """spread_pct > max_spread_pct → bloccato da filtro assoluto (spread_pct counter)."""
        # spread_pct = 15% a 45 DTE: cost=0.33 < 0.50 ma pct=15% > 10% → bloccato da assoluto
        c = _contract(bid=1.70, ask=2.00, dte=45)  # mid=1.85, spread=0.30, pct≈16.2%
        params = _permissive_params(max_spread_pct=10.0, max_spread_cost_per_dte=0.50)
        _, stats = apply_hard_filters([c], params)
        self.assertGreater(stats.spread_pct, 0)
        self.assertEqual(stats.spread_cost_dte, 0)  # non raggiunto

    def test_both_filters_independent(self):
        """Contratto che passa absolute ma fallisce DTE-adjusted."""
        # spread_pct = 7% a 13 DTE: cost=7/13=0.54 > 0.50 → DTE filter
        c = _contract(bid=1.86, ask=2.00, dte=14)
        # mid=1.93, spread=0.14, pct=7.25% < 10% → passa assoluto; cost=7.25/14=0.52 > 0.50 → fallisce DTE
        params = _permissive_params(max_spread_pct=10.0, max_spread_cost_per_dte=0.50)
        kept, stats = apply_hard_filters([c], params)
        self.assertEqual(len(kept), 0)
        self.assertEqual(stats.spread_pct, 0)
        self.assertGreater(stats.spread_cost_dte, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. FilterRejectStats.total_rejected include spread_cost_dte
# ─────────────────────────────────────────────────────────────────────────────

class TestFilterRejectStatsTotal(unittest.TestCase):

    def test_total_rejected_includes_spread_cost_dte(self):
        stats = FilterRejectStats(total_raw=5, spread_pct=1, spread_cost_dte=2, oi_low=1)
        self.assertEqual(stats.total_rejected, 4)

    def test_total_rejected_zero_when_all_pass(self):
        stats = FilterRejectStats(total_raw=3)
        self.assertEqual(stats.total_rejected, 0)

    def test_default_spread_cost_dte_is_zero(self):
        stats = FilterRejectStats()
        self.assertEqual(stats.spread_cost_dte, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Costante di default
# ─────────────────────────────────────────────────────────────────────────────

class TestDefaultConstant(unittest.TestCase):

    def test_default_value_is_reasonable(self):
        """0.50 pennette spread 7.5% a 15 DTE (cost=0.50) — soglia al limite."""
        self.assertAlmostEqual(DEFAULT_MAX_SPREAD_COST_PER_DTE, 0.50)

    def test_default_in_filter_params(self):
        p = FilterParams()
        self.assertEqual(p.max_spread_cost_per_dte, DEFAULT_MAX_SPREAD_COST_PER_DTE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
