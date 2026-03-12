import os
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
class TestF1T8DataRetention(unittest.TestCase):
    def test_retention_ttl_prunes_old_files(self):
        root = _case_root()
        inbox = root / "inbox"
        store = root / "raw"
        db = root / "index.duckdb"
        log = root / "capture.jsonl"
        inbox.mkdir(parents=True, exist_ok=True)

        p = inbox / "IWM__quote__001.json"
        p.write_text('{"bid": 1.1, "ask": 1.2}', encoding="utf-8")

        args = capture_pages.parse_args(
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
                "1024",
            ]
        )
        capture_pages.run_capture(args)

        raw_files = [x for x in store.rglob("*") if x.is_file()]
        self.assertEqual(len(raw_files), 1)
        old = raw_files[0]

        old_epoch = 1
        os.utime(old, (old_epoch, old_epoch))

        args_ret = capture_pages.parse_args(
            [
                "--source-dir",
                str(inbox),
                "--store-dir",
                str(store),
                "--db",
                str(db),
                "--log-path",
                str(log),
                "--limit",
                "0",
                "--freshness-minutes",
                "0",
                "--retention-days",
                "1",
                "--max-store-mb",
                "1024",
            ]
        )
        s = capture_pages.run_capture(args_ret)
        self.assertGreaterEqual(s["pruned_ttl"], 1)
        self.assertFalse(old.exists())

        con = dpl.connect_db(db)
        row = con.execute("SELECT status FROM captures LIMIT 1").fetchone()
        con.close()
        self.assertEqual(row[0], "PRUNED")


if __name__ == "__main__":
    unittest.main()
