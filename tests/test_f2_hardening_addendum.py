import unittest

from strategy.hardening_regime import correlation_breakdown_flag, hmm_event_oos_qualification, leakage_guard_ok


class TestF2HardeningAddendum(unittest.TestCase):
    def test_leakage_guard_pass_and_fail(self):
        self.assertTrue(leakage_guard_ok(feature_ts=[1, 2, 3], label_ts=[4, 5], train_end_ts=3))
        self.assertFalse(leakage_guard_ok(feature_ts=[1, 4], label_ts=[5], train_end_ts=3))
        self.assertFalse(leakage_guard_ok(feature_ts=[1, 2], label_ts=[3], train_end_ts=3))

    def test_hmm_event_oos_qualification(self):
        events = [
            {"family": "vix", "hmm_lead_days": 2, "xgb_lead_days": 1, "hmm_false_positive": 0, "xgb_false_positive": 0},
            {"family": "correlation", "hmm_lead_days": 1, "xgb_lead_days": 0, "hmm_false_positive": 0, "xgb_false_positive": 1},
            {"family": "credit", "hmm_lead_days": 0, "xgb_lead_days": 1, "hmm_false_positive": 0, "xgb_false_positive": 0},
        ]
        out = hmm_event_oos_qualification(events)
        self.assertTrue(out["qualified"])
        self.assertEqual(out["families_pass"], 2)

    def test_correlation_breakdown_flag(self):
        self.assertTrue(correlation_breakdown_flag(corr_zscore=-2.1))
        self.assertFalse(correlation_breakdown_flag(corr_zscore=-1.2))


if __name__ == "__main__":
    unittest.main()
