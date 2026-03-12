import unittest

from strategy.sizing_controls import adaptive_fixed_fractional, kelly_allowed


class TestF4AddendumSizingControls(unittest.TestCase):
    def test_adaptive_fixed_fractional_pre_kelly(self):
        self.assertAlmostEqual(adaptive_fixed_fractional(regime="NORMAL", base_fraction=0.01, n_closed_trades=10), 0.01)
        self.assertAlmostEqual(adaptive_fixed_fractional(regime="CAUTION", base_fraction=0.01, n_closed_trades=10), 0.005)
        self.assertAlmostEqual(adaptive_fixed_fractional(regime="SHOCK", base_fraction=0.01, n_closed_trades=10), 0.0)

    def test_adaptive_keeps_base_after_track_record(self):
        self.assertAlmostEqual(adaptive_fixed_fractional(regime="CAUTION", base_fraction=0.01, n_closed_trades=50), 0.01)

    def test_kelly_allowed_gate(self):
        self.assertFalse(kelly_allowed(data_mode="SYNTHETIC_SURFACE_CALIBRATED", n_closed_trades=80))
        self.assertFalse(kelly_allowed(data_mode="VENDOR_REAL_CHAIN", n_closed_trades=20))
        self.assertTrue(kelly_allowed(data_mode="VENDOR_REAL_CHAIN", n_closed_trades=50))


if __name__ == "__main__":
    unittest.main()
