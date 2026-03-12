import unittest
from pathlib import Path

from scripts.options_chain_quality import load_chain_csv, run_quality_checks, write_report


class TestF1T3OptionsChainQuality(unittest.TestCase):
    def test_quality_checks_exclusions_and_parity(self):
        csv_path = Path("samples/options_chain_sample_5d_100strikes.csv")
        quotes = load_chain_csv(csv_path)
        # 5 days * 100 strikes * 2 rights
        self.assertEqual(len(quotes), 1000)

        report = run_quality_checks(quotes, days=5, strikes_per_day=100, seed=42, parity_threshold=0.50)
        self.assertEqual(report["rows_sampled"], 1000)

        excl = report["excluded_by_reason"]
        self.assertEqual(excl.get("bid_gt_ask"), 1)
        self.assertEqual(excl.get("delta_put_out_of_range"), 1)
        self.assertEqual(excl.get("iv_out_of_range"), 1)

        parity = report["parity"]
        self.assertGreaterEqual(parity["alerts_count"], 1)
        strikes = {a["strike"] for a in parity["alerts"]}
        self.assertIn(350.0, strikes)

        outdir = Path("reports_test")
        js, md = write_report(report, outdir=outdir)
        self.assertTrue(js.exists())
        self.assertTrue(md.exists())
        # cleanup
        js.unlink(missing_ok=True)
        md.unlink(missing_ok=True)
        try:
            outdir.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    unittest.main()
