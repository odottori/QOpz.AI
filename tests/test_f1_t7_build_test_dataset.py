import csv
import unittest
from pathlib import Path
from uuid import uuid4

from scripts import build_test_dataset
from scripts import demo_pipeline_lib as dpl


def _case_root() -> Path:
    root = Path('.tmp_test') / f"case_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


@unittest.skipUnless(dpl.duckdb_available(), "duckdb not installed")
class TestF1T7BuildTestDataset(unittest.TestCase):
    def _seed_valid_extraction(self, db: Path, out_payload: Path):
        out_payload.parent.mkdir(parents=True, exist_ok=True)
        dpl.write_json(
            out_payload,
            {
                "capture_id": 1,
                "model": "qwen2.5",
                "prompt_version": "v1",
                "backend": "json-pass",
                "record": {
                    "symbol": "IWM",
                    "page_type": "quote",
                    "observed_ts_utc": "2026-03-05T10:00:00Z",
                    "bid": 1.1,
                    "ask": 1.3,
                    "last": 1.2,
                    "iv": 0.25,
                    "delta": 0.2,
                    "underlying_price": 210.0,
                },
            },
        )

        con = dpl.connect_db(db)
        dpl.init_db(con)
        con.execute(
            """
            INSERT INTO captures(
                id, captured_ts_utc, source, symbol, page_type, fingerprint_sha256,
                raw_path, payload_format, payload_bytes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'CAPTURED')
            """,
            (
                1,
                dpl.utc_now_iso(),
                "ibkr_demo",
                "IWM",
                "quote",
                "abc123",
                "C:/tmp/raw1.json",
                "json",
                20,
            ),
        )
        con.execute(
            """
            INSERT INTO extractions(
                capture_id, extracted_ts_utc, model, prompt_version, backend,
                attempts, status, output_path, error_text
            ) VALUES (?, ?, ?, ?, ?, ?, 'VALID', ?, NULL)
            """,
            (1, dpl.utc_now_iso(), "qwen2.5", "v1", "json-pass", 1, out_payload.as_posix()),
        )
        con.close()

    def test_build_dataset_csv_and_provenance(self):
        root = _case_root()
        db = root / "index.duckdb"
        out_dir = root / "datasets"
        payload = root / "extracted" / "1.json"
        log = root / "dataset.jsonl"

        self._seed_valid_extraction(db, payload)

        args = build_test_dataset.parse_args(
            [
                "--db",
                str(db),
                "--out-dir",
                str(out_dir),
                "--dataset-name",
                "demo_dataset",
                "--log-path",
                str(log),
            ]
        )
        s = build_test_dataset.run_build(args)

        csv_path = out_dir / "demo_dataset.csv"
        prov_path = out_dir / "demo_dataset.provenance.json"
        self.assertTrue(csv_path.exists())
        self.assertTrue(prov_path.exists())
        self.assertEqual(s["records"], 1)

        with csv_path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "IWM")


if __name__ == "__main__":
    unittest.main()
