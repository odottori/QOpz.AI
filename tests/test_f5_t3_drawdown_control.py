import json
import shutil
import unittest
from pathlib import Path

from execution.drawdown_control import evaluate_drawdown_policy
from tools import f5_t3_drawdown_control as tool


class TestF5T3DrawdownControl(unittest.TestCase):
    def setUp(self):
        Path("reports").mkdir(parents=True, exist_ok=True)

    def test_policy_escalates_alert_stop_kill(self):
        state = evaluate_drawdown_policy(equity_series=[10000, 9000, 8500, 8000])
        self.assertEqual([e.level for e in state.events], ["ALERT", "STOP", "KILL"])
        self.assertAlmostEqual(state.sizing_scalar, 0.0)
        self.assertFalse(state.allow_new_positions)
        self.assertTrue(state.hedge_on)
        self.assertTrue(state.kill_switch)

    def test_policy_is_escalation_only(self):
        state = evaluate_drawdown_policy(equity_series=[10000, 9000, 10000, 9500])
        self.assertEqual([e.level for e in state.events], ["ALERT"])
        self.assertAlmostEqual(state.sizing_scalar, 0.5)
        self.assertTrue(state.allow_new_positions)
        self.assertFalse(state.hedge_on)
        self.assertFalse(state.kill_switch)

    def test_empty_series_defaults(self):
        state = evaluate_drawdown_policy(equity_series=[])
        self.assertAlmostEqual(state.max_drawdown, 0.0)
        self.assertAlmostEqual(state.sizing_scalar, 1.0)
        self.assertTrue(state.allow_new_positions)
        self.assertFalse(state.hedge_on)
        self.assertFalse(state.kill_switch)
        self.assertEqual(state.events, [])

    def test_tool_writes_reports_and_passes(self):
        outdir = Path("reports") / "f5_t3_test_out"
        if outdir.exists():
            shutil.rmtree(outdir, ignore_errors=True)
        outdir.mkdir(parents=True, exist_ok=True)

        rc = tool.main(
            [
                "--equity-series",
                "10000,9000,8500,8000",
                "--outdir",
                str(outdir),
            ]
        )
        self.assertEqual(rc, 0)
        self.assertTrue((outdir / "f5_t3_drawdown_control.json").exists())
        self.assertTrue((outdir / "f5_t3_drawdown_control.md").exists())

        payload = json.loads((outdir / "f5_t3_drawdown_control.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["result"]["missing_levels"], [])
        self.assertEqual(payload["result"]["seen_levels"], ["ALERT", "STOP", "KILL"])

    def test_tool_fails_if_required_level_missing(self):
        outdir = Path("reports") / "f5_t3_test_out_fail"
        if outdir.exists():
            shutil.rmtree(outdir, ignore_errors=True)
        outdir.mkdir(parents=True, exist_ok=True)

        rc = tool.main(
            [
                "--equity-series",
                "10000,9500,9300",
                "--outdir",
                str(outdir),
            ]
        )
        self.assertEqual(rc, 10)


if __name__ == "__main__":
    unittest.main()
