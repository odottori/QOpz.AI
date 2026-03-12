import json
import tempfile
import unittest
from pathlib import Path

from scripts.wfa_bull_put import load_returns_csv, run_wfa_bull_put


class TestF2T4WfaBullPut(unittest.TestCase):
    def test_thresholds_and_outputs(self) -> None:
        rows = load_returns_csv(Path("samples/iwm_bull_put_synth_2010_2024.csv"))
        summary, oos_points = run_wfa_bull_put(rows, n_folds=10, is_years=3)

        self.assertEqual(summary.n_folds, 10)
        self.assertGreaterEqual(summary.median_sharpe_oos, 0.60)
        self.assertLessEqual(summary.max_dd_oos, 0.15)
        self.assertGreaterEqual(summary.median_win_rate_oos, 0.55)
        self.assertGreaterEqual(summary.deflation, 0.60)
        self.assertTrue(all(m.maxdd_oos <= 0.20 for m in summary.folds))
        self.assertGreater(len(oos_points), 100)

        # Exercise tool outputs
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td)
            import tools.f2_t4_wfa_bull_put as tool

            rc = tool.main(["--outdir", str(outdir), "--no-plots"])
            self.assertEqual(rc, 0)
            self.assertTrue((outdir / "f2_t4_wfa_summary.json").exists())
            self.assertTrue((outdir / "f2_t4_wfa_summary.md").exists())
            self.assertTrue((outdir / "f2_t4_equity_oos.csv").exists())
            self.assertTrue((outdir / "f2_t4_sharpe_by_fold.csv").exists())
            self.assertTrue((outdir / "f2_t4_drawdown_oos.csv").exists())

            js = json.loads((outdir / "f2_t4_wfa_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(js["n_folds"], 10)
            self.assertGreaterEqual(js["median_sharpe_oos"], 0.60)


if __name__ == "__main__":
    unittest.main()
