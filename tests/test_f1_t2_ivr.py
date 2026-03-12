from __future__ import annotations

import csv
import tempfile
from pathlib import Path
import unittest

from scripts.ivr import load_iv_history_csv, compute_iv_rank_from_history, iv_rank
from tools.f1_t2_compute_ivr import main as cli_main


class TestF1T2IVRank(unittest.TestCase):
    def test_iv_rank_bounds(self) -> None:
        history = load_iv_history_csv(Path("samples/iv_history_sample_252d.csv"))
        v = compute_iv_rank_from_history(history, "SPY", lookback=252)
        self.assertIsNotNone(v)
        assert v is not None
        self.assertGreaterEqual(v, 0.0)
        self.assertLessEqual(v, 100.0)

    def test_against_offline_ground_truth(self) -> None:
        history = load_iv_history_csv(Path("samples/iv_history_sample_252d.csv"))
        with Path("samples/orats_ivrank_ground_truth_offline.csv").open("r", newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                t = row["ticker"]
                gt = float(row["iv_rank_orats"])
                calc = compute_iv_rank_from_history(history, t, lookback=252)
                self.assertIsNotNone(calc)
                assert calc is not None
                self.assertLess(abs(calc - gt), 5.0, f"{t} calc={calc} gt={gt}")

    def test_constant_iv_edge_case(self) -> None:
        self.assertEqual(iv_rank([0.25] * 252), 50.0)

    def test_missing_ticker_graceful(self) -> None:
        history = load_iv_history_csv(Path("samples/iv_history_sample_252d.csv"))
        self.assertIsNone(compute_iv_rank_from_history(history, "NEW_TICKER", lookback=252))

    def test_cli_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td) / "reports"
            rc = cli_main(["--outdir", str(outdir), "--format", "both"])
            self.assertEqual(rc, 0)
            self.assertTrue((outdir / "f1_t2_ivr.json").exists())
            self.assertTrue((outdir / "f1_t2_ivr.md").exists())


if __name__ == "__main__":
    unittest.main()
