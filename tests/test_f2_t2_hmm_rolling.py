import os
import unittest

from scripts.hmm_regime import load_hmm_csv, fit_hmm_rolling
from tools import f2_t2_fit_hmm_rolling as t2


class TestF2T2HMMRolling(unittest.TestCase):
    def test_f2_t2_hmm_pass_criteria_offline(self):
        csv_path = os.path.join("samples", "hmm_features_synth_340d.csv")
        rows = load_hmm_csv(csv_path)

        hmm = fit_hmm_rolling(rows, window=252, max_iter=10, tol=5e-2, max_points=60)
        self.assertTrue(hmm["transition_ok"] if "transition_ok" in hmm else True)

        # Transition matrix rows sum to 1
        for s in hmm["transition_row_sums"]:
            self.assertAlmostEqual(float(s), 1.0, places=6)

        # Coherent with VIX: state means strictly ordered (scaled)
        vix_means = hmm.get("last_vix_means_scaled")
        self.assertIsNotNone(vix_means)
        self.assertEqual(len(vix_means), 3)
        ordered = sorted(vix_means)
        self.assertLess(ordered[0], ordered[1])
        self.assertLess(ordered[1], ordered[2])

        # Convergence: at least some rolling fits converge before max_iter
        conv = [r.get("converged") for r in hmm["rows"]]
        self.assertGreaterEqual(sum(1 for c in conv if c), 10)

        # Early-warning lead vs baseline classifier: >=2/3 families have 1-2d lead
        xgb = t2._xgb_baseline(rows, window=252)
        lead = t2._lead_time_eval(rows, hmm["rows"], xgb["by_date"])
        self.assertTrue(lead["pass"], msg=str(lead))
        self.assertGreaterEqual(lead["ok_leads"], 2)


if __name__ == "__main__":
    unittest.main()
