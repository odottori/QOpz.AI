import unittest
from pathlib import Path
from uuid import uuid4

from scripts import demo_pipeline_lib as dpl
from scripts import extract_with_ollama


def _case_root() -> Path:
    root = Path('.tmp_test') / f"case_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


@unittest.skipUnless(dpl.duckdb_available(), "duckdb not installed")
class TestF1T6ExtractWithOllama(unittest.TestCase):
    def _seed_capture(self, db: Path, raw_path: Path, *, symbol: str, page_type: str, payload: str):
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(payload, encoding="utf-8")

        con = dpl.connect_db(db)
        dpl.init_db(con)
        con.execute(
            """
            INSERT INTO captures(
                captured_ts_utc, source, symbol, page_type, fingerprint_sha256,
                raw_path, payload_format, payload_bytes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CAPTURED')
            """,
            (
                dpl.utc_now_iso(),
                "ibkr_demo",
                symbol,
                page_type,
                dpl.sha256_bytes(payload.encode("utf-8")),
                raw_path.as_posix(),
                "json",
                len(payload),
            ),
        )
        con.close()

    def test_json_pass_valid(self):
        root = _case_root()
        db = root / "index.duckdb"
        out_dir = root / "extracted"
        log = root / "extract.jsonl"

        self._seed_capture(
            db,
            root / "raw" / "q1.json",
            symbol="IWM",
            page_type="quote",
            payload='{"bid":1.1,"ask":1.3,"iv":0.25,"delta":0.2}',
        )

        args = extract_with_ollama.parse_args(
            [
                "--db",
                str(db),
                "--out-dir",
                str(out_dir),
                "--log-path",
                str(log),
                "--backend",
                "json-pass",
            ]
        )
        s = extract_with_ollama.run_extract(args)
        self.assertEqual(s["valid"], 1)
        self.assertEqual(s["needs_review"], 0)
        out_file = out_dir / "1.json"
        self.assertTrue(out_file.exists())
        payload = dpl.parse_json(out_file)
        self.assertEqual(payload["validator_version"], "v1")
        self.assertEqual(payload["prompt_version"], extract_with_ollama.PROMPT_VERSION)
        log_lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(log_lines), 1)
        self.assertIn('"event": "validated"', log_lines[0])

    def test_needs_review_when_no_numeric(self):
        root = _case_root()
        db = root / "index.duckdb"
        out_dir = root / "extracted"
        log = root / "extract.jsonl"

        self._seed_capture(
            db,
            root / "raw" / "q2.json",
            symbol="IWM",
            page_type="quote",
            payload='{"note":"missing prices"}',
        )

        args = extract_with_ollama.parse_args(
            [
                "--db",
                str(db),
                "--out-dir",
                str(out_dir),
                "--log-path",
                str(log),
                "--backend",
                "json-pass",
                "--max-retries",
                "1",
            ]
        )
        s = extract_with_ollama.run_extract(args)
        self.assertEqual(s["valid"], 0)
        self.assertEqual(s["needs_review"], 1)
        log_lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(log_lines), 2)
        self.assertIn('"event": "invalid_json"', log_lines[0])
        self.assertIn('"event": "needs_review"', log_lines[1])

        con = dpl.connect_db(db)
        row = con.execute("SELECT status FROM extractions LIMIT 1").fetchone()
        con.close()
        self.assertEqual(row[0], "NEEDS_REVIEW")


if __name__ == "__main__":
    unittest.main()
