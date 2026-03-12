import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from api.opz_api import app
except Exception:
    TestClient = None
    app = None

from execution.storage import init_execution_schema
from execution.universe import PIPELINE_DATASET_DIR, init_universe_schema


@unittest.skipIf(TestClient is None or app is None, "fastapi not installed in this environment")
class TestF6T2UniverseApi(unittest.TestCase):
    def setUp(self):
        for d in ("db", "logs", "data", "reports"):
            Path(d).mkdir(parents=True, exist_ok=True)

        for dbp in (Path("db/execution.duckdb"),):
            if dbp.exists():
                dbp.unlink(missing_ok=True)

        pipeline_root = PIPELINE_DATASET_DIR.parent
        if pipeline_root.exists():
            for p in sorted(pipeline_root.rglob("*"), reverse=True):
                if p.is_file():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    try:
                        p.rmdir()
                    except OSError:
                        pass
        PIPELINE_DATASET_DIR.mkdir(parents=True, exist_ok=True)

        self._seed_dataset(PIPELINE_DATASET_DIR / "demo_dataset.csv")

        init_execution_schema()
        init_universe_schema()
        self.client = TestClient(app)

    def _seed_dataset(self, path: Path) -> None:
        rows = [
            (1, "SPY", 599.7, 600.3, 600.0, 0.22, 8_500_000, 12_000_000, "Financial"),
            (2, "QQQ", 519.8, 520.2, 520.0, 0.28, 6_800_000, 10_100_000, "Technology"),
            (3, "IWM", 209.6, 210.4, 210.0, 0.31, 4_900_000, 6_200_000, "Industrial"),
            (4, "AAPL", 188.9, 189.1, 189.0, 0.35, 12_000_000, 18_000_000, "Technology"),
            (5, "MSFT", 427.9, 428.1, 428.0, 0.26, 5_300_000, 11_000_000, "Technology"),
            (6, "NVDA", 868.5, 871.5, 870.0, 0.48, 14_500_000, 25_000_000, "Technology"),
        ]

        header = (
            "capture_id,captured_ts_utc,source,symbol,page_type,observed_ts_utc,bid,ask,last,iv,delta,"
            "underlying_price,fingerprint_sha256,model,prompt_version,backend,raw_path,output_path,"
            "volume,open_interest,industry,market_cap_mln,has_options\n"
        )

        lines = [header]
        for capture_id, symbol, bid, ask, last, iv, vol, oi, industry in rows:
            line = (
                f"{capture_id},2026-03-05T10:00:00Z,ibkr_demo,{symbol},quote,2026-03-05T10:00:00Z,"
                f"{bid},{ask},{last},{iv},0.20,{last},fp{capture_id},qwen2.5,v1,json-pass,raw{capture_id},out{capture_id},"
                f"{vol},{oi},{industry},50000,true\n"
            )
            lines.append(line)

        path.write_text("".join(lines), encoding="utf-8")

    def test_latest_empty_before_first_scan(self):
        r = self.client.get("/opz/universe/latest")
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        self.assertFalse(j.get("has_data"))
        self.assertEqual(j.get("items"), [])

    def test_scan_persists_and_latest_returns_sorted_shortlist(self):
        payload = {
            "profile": "paper",
            "symbols": ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA"],
            "regime": "NORMAL",
            "top_n": 4,
            "source": "manual",
        }
        s = self.client.post("/opz/universe/scan", json=payload)
        self.assertEqual(s.status_code, 200, s.text)
        scan = s.json()

        self.assertTrue(scan.get("batch_id"))
        items = scan.get("items", [])
        self.assertEqual(len(items), 4)
        self.assertGreaterEqual(scan.get("market_rows_available", 0), 6)

        prev = 10.0
        for idx, item in enumerate(items, start=1):
            self.assertEqual(item.get("rank"), idx)
            self.assertLessEqual(float(item.get("score")), prev + 1e-12)
            prev = float(item.get("score"))

        l = self.client.get("/opz/universe/latest")
        self.assertEqual(l.status_code, 200, l.text)
        latest = l.json()
        self.assertTrue(latest.get("has_data"))
        self.assertEqual(latest.get("batch_id"), scan.get("batch_id"))
        self.assertEqual(len(latest.get("items", [])), 4)
        self.assertEqual(latest.get("source"), "manual")
        self.assertEqual(latest.get("market_rows_available"), scan.get("market_rows_available"))
        self.assertEqual(latest.get("filter_fallback"), scan.get("filter_fallback"))

    def test_ibkr_settings_scan_persists_scanner_name_in_latest(self):
        payload = {
            "profile": "paper",
            "regime": "NORMAL",
            "top_n": 4,
            "source": "ibkr_settings",
            "scanner_name": "TOP_PERC_GAIN",
        }
        s = self.client.post("/opz/universe/scan", json=payload)
        self.assertEqual(s.status_code, 200, s.text)
        scan = s.json()
        self.assertEqual(scan.get("scanner_name"), "TOP_PERC_GAIN")
        self.assertTrue(scan.get("ibkr_settings_path"))

        l = self.client.get("/opz/universe/latest")
        self.assertEqual(l.status_code, 200, l.text)
        latest = l.json()
        self.assertEqual(latest.get("batch_id"), scan.get("batch_id"))
        self.assertEqual(latest.get("source"), "ibkr_settings")
        self.assertEqual(latest.get("scanner_name"), "TOP_PERC_GAIN")
        self.assertEqual(latest.get("ibkr_settings_path"), scan.get("ibkr_settings_path"))
        self.assertEqual(latest.get("ibkr_settings_exists"), scan.get("ibkr_settings_exists"))


    def test_provenance_exposes_field_sources_without_ocr_dependency(self):
        payload = {
            "profile": "paper",
            "symbols": ["SPY", "QQQ", "IWM"],
            "regime": "NORMAL",
            "top_n": 3,
            "source": "manual",
        }
        s = self.client.post("/opz/universe/scan", json=payload)
        self.assertEqual(s.status_code, 200, s.text)

        p = self.client.get("/opz/universe/provenance?regime=NORMAL")
        self.assertEqual(p.status_code, 200, p.text)
        j = p.json()
        self.assertIn("policy_version", j)
        self.assertEqual(j.get("ocr_rows"), 0)
        rows = j.get("rows", [])
        if rows:
            self.assertIn("field_sources", rows[0])
            self.assertIn("source", rows[0])
            self.assertIn("mismatch_fields", rows[0])

    def test_provenance_can_follow_latest_batch_symbols(self):
        payload = {
            "profile": "paper",
            "symbols": ["AAPL", "MSFT"],
            "regime": "NORMAL",
            "top_n": 2,
            "source": "manual",
        }
        s = self.client.post("/opz/universe/scan", json=payload)
        self.assertEqual(s.status_code, 200, s.text)
        batch_id = s.json().get("batch_id")
        self.assertTrue(batch_id)

        p = self.client.get("/opz/universe/provenance", params={"regime": "NORMAL", "batch_id": batch_id})
        self.assertEqual(p.status_code, 200, p.text)
        j = p.json()
        self.assertEqual(j.get("batch_id"), batch_id)
        self.assertEqual(j.get("symbol_scope"), "batch")
        syms = {str(r.get("symbol")) for r in j.get("rows", [])}
        self.assertTrue({"AAPL", "MSFT"}.issubset(syms), j)
        self.assertNotIn("SPY", syms)

    def test_provenance_uses_persisted_settings_path_for_batch(self):
        persisted_settings = Path("docs/test_ibkr_settings.xml")
        persisted_settings.write_text("""<root><QuoteElement symbol="AAPL" exchange="SMART" /></root>""", encoding="utf-8")
        alt_settings = Path("docs/alt_settings.xml")
        alt_settings.write_text("<root></root>", encoding="utf-8")

        payload = {
            "profile": "paper",
            "regime": "NORMAL",
            "top_n": 2,
            "source": "ibkr_settings",
            "scanner_name": "TOP_PERC_GAIN",
            "settings_path": str(persisted_settings),
        }
        s = self.client.post("/opz/universe/scan", json=payload)
        self.assertEqual(s.status_code, 200, s.text)
        batch_id = s.json().get("batch_id")
        self.assertTrue(batch_id)

        p = self.client.get(
            "/opz/universe/provenance",
            params={"regime": "NORMAL", "batch_id": batch_id, "settings_path": str(alt_settings)},
        )
        self.assertEqual(p.status_code, 200, p.text)
        j = p.json()
        self.assertEqual(Path(j.get("settings_path")).name, persisted_settings.name)
        self.assertTrue(j.get("settings_exists"))

        p2 = self.client.get(
            "/opz/universe/provenance",
            params={"regime": "NORMAL", "batch_id": batch_id},
        )
        self.assertEqual(p2.status_code, 200, p2.text)
        j2 = p2.json()
        self.assertEqual(Path(j2.get("settings_path")).name, persisted_settings.name)
        self.assertTrue(j2.get("settings_exists"))

    def test_scan_rejects_invalid_regime(self):
        r = self.client.post(
            "/opz/universe/scan",
            json={"profile": "paper", "symbols": ["SPY", "QQQ"], "regime": "BAD", "top_n": 2},
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalid regime", r.text)


if __name__ == "__main__":
    unittest.main()



