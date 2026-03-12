from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from execution.stress_live import run_f6_t3_stress_suite


class TestF6T3StressLive(unittest.TestCase):
    def test_suite_passes_with_defaults(self) -> None:
        out = run_f6_t3_stress_suite()
        self.assertTrue(out["overall_pass"], out)
        self.assertEqual(len(out["checks"]), 3)

    def test_vix_spike_fails_if_below_threshold(self) -> None:
        out = run_f6_t3_stress_suite(vix_prev=20.0, vix_now=22.0)
        row = [r for r in out["checks"] if r["scenario"] == "VIX_SPIKE_20PCT"][0]
        self.assertFalse(row["pass"])

    def test_api_disconnect_fails_when_reconnect_never_succeeds(self) -> None:
        out = run_f6_t3_stress_suite(reconnect_attempts=[False, False, False])
        row = [r for r in out["checks"] if r["scenario"] == "API_DISCONNECTION"][0]
        self.assertFalse(row["pass"])

    def test_tool_strict_returns_nonzero_on_failure(self) -> None:
        root = Path(__file__).resolve().parents[1]
        tool = root / "tools" / "f6_t3_stress_live.py"
        proc = subprocess.run(
            [
                sys.executable,
                str(tool),
                "--vix-prev",
                "20",
                "--vix-now",
                "22",
                "--strict",
                "--format",
                "json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 10, proc.stdout + proc.stderr)
        obj = json.loads(proc.stdout)
        self.assertIn("overall_pass", obj)


if __name__ == "__main__":
    unittest.main()
