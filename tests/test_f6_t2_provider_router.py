import unittest
from pathlib import Path

from execution.market_provider_contract import UniverseSnapshotRequest
from execution.providers.external_delayed_provider import ExternalDelayedCsvProvider
from execution.providers.ibkr_provider import IbkrProvider
from execution.providers.router import ProviderRouter


class TestF6T2ProviderRouter(unittest.TestCase):
    def setUp(self):
        self.providers_dir = Path("data/providers")
        self.providers_dir.mkdir(parents=True, exist_ok=True)
        self.external_csv = self.providers_dir / "external_delayed_quotes.csv"
        self.external_csv.write_text(
            "symbol,asset_type,last,bid,ask,iv,open_interest,volume,delta,observed_at_utc\n"
            "SPY,etf,601.0,600.8,601.2,0.24,11000000,9000000,0.30,2026-03-05T10:00:00Z\n"
            "QQQ,etf,521.0,520.9,521.1,0.29,10000000,7000000,0.25,2026-03-05T10:00:00Z\n",
            encoding="utf-8",
        )

    def test_router_returns_field_sources_and_conflicts(self):
        router = ProviderRouter(ibkr=IbkrProvider(), external=ExternalDelayedCsvProvider(csv_path=self.external_csv))
        out = router.get_universe_snapshot(UniverseSnapshotRequest(symbols=["SPY", "QQQ"], regime="NORMAL"))

        self.assertEqual(out.get("source"), "provider_router")
        self.assertIn("policy_version", out)
        self.assertIsInstance(out.get("rows"), list)

        if out.get("rows"):
            row = out["rows"][0]
            self.assertIn("field_sources", row)
            self.assertIn("source", row)
            self.assertIn("freshness_s", row)
            self.assertIn("conflict_flags", row)


if __name__ == "__main__":
    unittest.main()
