import tempfile
import unittest
from pathlib import Path

from scripts import market_data_ingest


class TestF1T1MarketIngestion(unittest.TestCase):
    def test_ingest_spy_sample_csv_and_validate(self) -> None:
        csv_path = Path("samples/spy_daily_sample_2020_2022.csv")
        self.assertTrue(csv_path.exists(), f"missing sample CSV: {csv_path}")

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "quantoptionai.duckdb"
            report = market_data_ingest.ingest_csv_to_duckdb(csv_path=csv_path, duckdb_path=db_path, symbol="SPY", source="unit_test")

            self.assertEqual(report.get("ingested_rows"), report.get("rows"))
            self.assertGreater(int(report.get("rows") or 0), 100)

            nulls = report.get("null_counts") or {}
            self.assertTrue(all(int(v or 0) == 0 for v in nulls.values()), f"null_counts not zero: {nulls}")

            gaps = report.get("gap_check") or {}
            self.assertEqual(int(gaps.get("missing") or 0), 0, f"missing dates: {gaps.get('missing_dates')}")

            split = report.get("split_check") or {}
            self.assertTrue(bool(split.get("ok")), f"split_check failed: {split}")


if __name__ == "__main__":
    unittest.main()
