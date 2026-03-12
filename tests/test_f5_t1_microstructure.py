import json
import shutil
import unittest
from pathlib import Path

from scripts.microstructure_features import (
    compute_iv_curvature_accel,
    compute_microstructure_features,
    compute_oi_change_velocity,
    compute_volume_profile_delta,
    detect_velocity_spike,
)
from tools import f5_t1_microstructure as tool


class TestF5T1Microstructure(unittest.TestCase):
    def setUp(self):
        Path("reports").mkdir(parents=True, exist_ok=True)

    def test_volume_profile_delta_is_bounded(self):
        self.assertAlmostEqual(compute_volume_profile_delta(bid_volume=50, ask_volume=150), 0.5)
        self.assertAlmostEqual(compute_volume_profile_delta(bid_volume=200, ask_volume=0), -1.0)
        self.assertAlmostEqual(compute_volume_profile_delta(bid_volume=0, ask_volume=200), 1.0)
        self.assertAlmostEqual(compute_volume_profile_delta(bid_volume=0, ask_volume=0), 0.0)

    def test_oi_change_velocity_annualized(self):
        vel = compute_oi_change_velocity(oi_t=1100, oi_t_minus_n=1000, periods=3, annualization_factor=252)
        self.assertAlmostEqual(vel, 8.4)

    def test_detect_velocity_spike_with_zscore(self):
        series = [0.02, 0.03, 0.01, 0.40]
        self.assertTrue(detect_velocity_spike(velocity_history=series, z_threshold=2.0))

    def test_iv_curvature_accel_second_difference(self):
        accel = compute_iv_curvature_accel(skew_5d_series=[0.10, 0.12, 0.17])
        self.assertAlmostEqual(accel, 0.03)

    def test_composite_features(self):
        out = compute_microstructure_features(
            bid_volume=100,
            ask_volume=160,
            oi_t=1200,
            oi_t_minus_n=1000,
            oi_velocity_history=[0.01, 0.02, 0.03, 0.2],
            skew_5d_series=[0.10, 0.12, 0.16],
        )
        self.assertGreaterEqual(out.volume_profile_delta, -1.0)
        self.assertLessEqual(out.volume_profile_delta, 1.0)
        self.assertGreater(out.oi_change_velocity, 0.0)
        self.assertTrue(out.oi_velocity_spike)

    def test_tool_writes_reports(self):
        outdir = Path("reports") / "f5_t1_test_out"
        if outdir.exists():
            shutil.rmtree(outdir, ignore_errors=True)
        outdir.mkdir(parents=True, exist_ok=True)

        rc = tool.main(
            [
                "--bid-volume",
                "100",
                "--ask-volume",
                "150",
                "--oi-t",
                "1200",
                "--oi-t-3",
                "1000",
                "--oi-velocity-history",
                "0.01,0.02,0.03,0.25",
                "--skew-5d",
                "0.10,0.12,0.16",
                "--outdir",
                str(outdir),
            ]
        )
        self.assertEqual(rc, 0)

        j = outdir / "f5_t1_microstructure.json"
        m = outdir / "f5_t1_microstructure.md"
        self.assertTrue(j.exists())
        self.assertTrue(m.exists())

        payload = json.loads(j.read_text(encoding="utf-8"))
        self.assertIn("features", payload)
        self.assertIn("volume_profile_delta", payload["features"])


if __name__ == "__main__":
    unittest.main()
