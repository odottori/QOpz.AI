import unittest

from strategy.scoring import Regime, compute_trade_score, kelly_fractional


class TestF4_ScoringAndKelly(unittest.TestCase):
    # F4-T1 — Score composito 4 pilastri
    def test_score_composite_typical(self):
        r = compute_trade_score(
            ivr=50,
            bid_ask_spread_pct=3.0,
            open_interest=500,
            rr=2.0,
            regime=Regime.NORMAL,
        )
        self.assertTrue(r.accepted)
        self.assertGreaterEqual(r.score, 60.0)
        self.assertLessEqual(r.score, 80.0)

    def test_reject_hard_low_ivr(self):
        r = compute_trade_score(
            ivr=15,
            bid_ask_spread_pct=3.0,
            open_interest=500,
            rr=2.0,
            regime=Regime.NORMAL,
        )
        self.assertFalse(r.accepted)
        self.assertEqual(r.score, 0.0)

    def test_reject_hard_wide_spread(self):
        r = compute_trade_score(
            ivr=50,
            bid_ask_spread_pct=12.0,
            open_interest=500,
            rr=2.0,
            regime=Regime.NORMAL,
        )
        self.assertFalse(r.accepted)
        self.assertEqual(r.score, 0.0)

    # F4-T2 — Kelly fractional [v11.1]
    # Tests pass _data_mode="VENDOR_REAL_CHAIN" to satisfy the DATA_MODE gate
    # (production code reads OPZ_DATA_MODE env var — tests bypass env dependency explicitly)
    _KDM = "VENDOR_REAL_CHAIN"

    def test_kelly_base(self):
        f = kelly_fractional(p=0.65, b=1.5, skewness=0.0, _data_mode=self._KDM)
        self.assertAlmostEqual(f, 0.2083333, places=4)

    def test_kelly_skew_adjustment(self):
        f = kelly_fractional(p=0.65, b=1.5, skewness=-1.5, _data_mode=self._KDM)
        self.assertAlmostEqual(f, 0.1666666, places=4)

    def test_kelly_lower_bound_no_trade(self):
        # choose params that produce ~0.3% (<0.5%) after half-kelly
        f = kelly_fractional(p=0.51, b=1.05, skewness=0.0, min_trade_pct=0.5, _data_mode=self._KDM)
        self.assertEqual(f, 0.0)

    def test_kelly_upper_bound_cap(self):
        f = kelly_fractional(p=0.9, b=4.0, skewness=0.0, f_max=0.25, _data_mode=self._KDM)
        self.assertEqual(f, 0.25)

    def test_kelly_invalid_params(self):
        self.assertEqual(kelly_fractional(p=1.0, b=1.0, _data_mode=self._KDM), 0.0)
        self.assertEqual(kelly_fractional(p=0.0, b=1.0, _data_mode=self._KDM), 0.0)
        self.assertEqual(kelly_fractional(p=0.6, b=0.0, _data_mode=self._KDM), 0.0)
        self.assertEqual(kelly_fractional(p=0.6, b=-1.0, _data_mode=self._KDM), 0.0)

    def test_kelly_blocked_in_synthetic_mode(self):
        """Kelly must raise RuntimeError when DATA_MODE != VENDOR_REAL_CHAIN."""
        with self.assertRaises(RuntimeError):
            kelly_fractional(p=0.65, b=1.5, _data_mode="SYNTHETIC_SURFACE_CALIBRATED")


if __name__ == "__main__":
    unittest.main()
