import json
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
        self.assertIn('"raw_path":', log_lines[0])
        self.assertIn('"symbol": "IWM"', log_lines[0])
        self.assertIn('"event": "needs_review"', log_lines[1])
        self.assertIn('"page_type": "quote"', log_lines[1])

        con = dpl.connect_db(db)
        row = con.execute("SELECT status FROM extractions LIMIT 1").fetchone()
        con.close()
        self.assertEqual(row[0], "NEEDS_REVIEW")

    def test_json_pass_real_tesseract_row_extracts_quote_cluster(self):
        real_rows = dpl.parse_json(Path("data/ibkr_screens/tesseract_extraction.json"))
        rows = real_rows.get("rows") or []
        nvda_row = next(
            r for r in rows
            if str(r.get("symbol") or "").upper() == "NVDA" and str(r.get("tab") or "").lower() == "opzioni"
        )

        root = _case_root()
        db = root / "index.duckdb"
        out_dir = root / "extracted"
        log = root / "extract.jsonl"
        raw_path = root / "raw" / "nvda_quote_row.json"
        payload = {
            "symbol": "NVDA",
            "page_type": "opzioni",
            "raw_line": nvda_row["raw_line"],
            "source_file": nvda_row.get("file"),
        }
        self._seed_capture(
            db,
            raw_path,
            symbol="NVDA",
            page_type="opzioni",
            payload=json.dumps(payload, ensure_ascii=False),
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
        out_payload = dpl.parse_json(out_dir / "1.json")
        rec = out_payload["record"]
        self.assertEqual(rec["symbol"], "NVDA")
        self.assertEqual(rec["page_type"], "opzioni")
        self.assertAlmostEqual(float(rec["last"]), 180.83, places=2)
        self.assertAlmostEqual(float(rec["bid"]), 180.84, places=2)
        self.assertAlmostEqual(float(rec["ask"]), 180.86, places=2)

    def test_json_pass_real_tesseract_row_extracts_amzn_quote_cluster(self):
        real_rows = dpl.parse_json(Path("data/ibkr_screens/tesseract_extraction.json"))
        rows = real_rows.get("rows") or []
        amzn_row = next(
            r for r in rows
            if str(r.get("symbol") or "").upper() == "AMZN"
            and str(r.get("tab") or "").lower() == "opzioni"
            and "216.79 216.85" in str(r.get("raw_line") or "")
        )

        root = _case_root()
        db = root / "index.duckdb"
        out_dir = root / "extracted"
        log = root / "extract.jsonl"
        raw_path = root / "raw" / "amzn_quote_row.json"
        payload = {
            "symbol": "AMZN",
            "page_type": "opzioni",
            "raw_line": amzn_row["raw_line"],
            "source_file": amzn_row.get("file"),
        }
        self._seed_capture(
            db,
            raw_path,
            symbol="AMZN",
            page_type="opzioni",
            payload=json.dumps(payload, ensure_ascii=False),
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
        self.assertEqual(s["valid"], 1)
        self.assertEqual(s["needs_review"], 0)
        out_payload = dpl.parse_json(out_dir / "1.json")
        rec = out_payload["record"]
        self.assertAlmostEqual(float(rec["last"]), 216.85, places=2)
        self.assertAlmostEqual(float(rec["bid"]), 216.79, places=2)
        self.assertAlmostEqual(float(rec["ask"]), 216.85, places=2)

    def test_json_pass_real_tesseract_row_normalizes_missing_decimal(self):
        real_rows = dpl.parse_json(Path("data/ibkr_screens/tesseract_extraction.json"))
        rows = real_rows.get("rows") or []
        msft_row = next(
            r for r in rows
            if str(r.get("symbol") or "").upper() == "MSFT"
            and str(r.get("tab") or "").lower() == "opzioni"
            and "41249 + 412.45 412.61" in str(r.get("raw_line") or "")
        )

        root = _case_root()
        db = root / "index.duckdb"
        out_dir = root / "extracted"
        log = root / "extract.jsonl"
        raw_path = root / "raw" / "msft_quote_row.json"
        payload = {
            "symbol": "MSFT",
            "page_type": "opzioni",
            "raw_line": msft_row["raw_line"],
            "source_file": msft_row.get("file"),
        }
        self._seed_capture(
            db,
            raw_path,
            symbol="MSFT",
            page_type="opzioni",
            payload=json.dumps(payload, ensure_ascii=False),
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
        out_payload = dpl.parse_json(out_dir / "1.json")
        rec = out_payload["record"]
        self.assertAlmostEqual(float(rec["last"]), 412.49, places=2)
        self.assertAlmostEqual(float(rec["bid"]), 412.45, places=2)
        self.assertAlmostEqual(float(rec["ask"]), 412.61, places=2)


if __name__ == "__main__":
    unittest.main()
