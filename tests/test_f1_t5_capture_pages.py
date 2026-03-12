import unittest
from pathlib import Path
from uuid import uuid4

from scripts import capture_pages
from scripts import demo_pipeline_lib as dpl


def _case_root() -> Path:
    root = Path('.tmp_test') / f"case_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


@unittest.skipUnless(dpl.duckdb_available(), "duckdb not installed")
class TestF1T5CapturePages(unittest.TestCase):
    def test_capture_and_dedup(self):
        root = _case_root()
        inbox = root / "inbox"
        store = root / "raw"
        db = root / "index.duckdb"
        log = root / "capture.jsonl"
        inbox.mkdir(parents=True, exist_ok=True)

        p = inbox / "IWM__quote__001.json"
        p.write_text('{"bid": 1.2, "ask": 1.4}', encoding="utf-8")

        args1 = capture_pages.parse_args(
            [
                "--source-dir",
                str(inbox),
                "--store-dir",
                str(store),
                "--db",
                str(db),
                "--log-path",
                str(log),
                "--freshness-minutes",
                "0",
                "--retention-days",
                "0",
                "--max-store-mb",
                "512",
            ]
        )
        s1 = capture_pages.run_capture(args1)
        self.assertEqual(s1["captured"], 1)
        self.assertEqual(s1["duplicates"], 0)

        args2 = capture_pages.parse_args(
            [
                "--source-dir",
                str(inbox),
                "--store-dir",
                str(store),
                "--db",
                str(db),
                "--log-path",
                str(log),
                "--freshness-minutes",
                "0",
                "--retention-days",
                "0",
                "--max-store-mb",
                "512",
            ]
        )
        s2 = capture_pages.run_capture(args2)
        self.assertEqual(s2["captured"], 0)
        self.assertEqual(s2["duplicates"], 1)

        con = dpl.connect_db(db)
        row = con.execute("SELECT symbol, page_type FROM captures LIMIT 1").fetchone()
        cnt = con.execute("SELECT COUNT(*) FROM captures").fetchone()[0]
        con.close()
        self.assertEqual(cnt, 1)
        self.assertEqual(row[0], 'IWM')
        self.assertEqual(row[1], 'quote')

    def test_freshness_skip_logs_event(self):
        root = _case_root()
        inbox = root / "inbox"
        store = root / "raw"
        db = root / "index.duckdb"
        log = root / "capture.jsonl"
        inbox.mkdir(parents=True, exist_ok=True)

        first = inbox / "IWM__quote__001.json"
        first.write_text('{"bid": 1.2, "ask": 1.4}', encoding="utf-8")
        args1 = capture_pages.parse_args(
            [
                "--source-dir",
                str(inbox),
                "--store-dir",
                str(store),
                "--db",
                str(db),
                "--log-path",
                str(log),
                "--freshness-minutes",
                "60",
                "--retention-days",
                "0",
                "--max-store-mb",
                "512",
                "--limit",
                "1",
            ]
        )
        s1 = capture_pages.run_capture(args1)
        self.assertEqual(s1["captured"], 1)
        self.assertGreater(s1["bytes_on_disk"], 0)

        first.write_text('{"bid": 1.25, "ask": 1.45}', encoding="utf-8")
        args2 = capture_pages.parse_args(
            [
                "--source-dir",
                str(inbox),
                "--store-dir",
                str(store),
                "--db",
                str(db),
                "--log-path",
                str(log),
                "--freshness-minutes",
                "60",
                "--retention-days",
                "0",
                "--max-store-mb",
                "512",
            ]
        )
        s2 = capture_pages.run_capture(args2)
        self.assertEqual(s2["captured"], 0)
        self.assertEqual(s2["duplicates"], 0)
        self.assertEqual(s2["skipped_fresh"], 1)

        events = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(events), 2)
        self.assertIn('"event": "captured"', events[0])
        self.assertIn('"event": "skipped_fresh"', events[1])


if __name__ == "__main__":
    unittest.main()

