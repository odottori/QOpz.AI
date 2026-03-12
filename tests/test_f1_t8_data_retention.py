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

        log_lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(any('"event": "pruned_file"' in line and '"reason": "ttl"' in line for line in log_lines))

    def test_retention_disk_cap_prunes_oldest_files(self):
        root = _case_root()
        inbox = root / "inbox"
        store = root / "raw"
        db = root / "index.duckdb"
        log = root / "capture.jsonl"
        inbox.mkdir(parents=True, exist_ok=True)

        payload_a = "A" * (700 * 1024)
        payload_b = "B" * (700 * 1024)
        (inbox / "IWM__quote__001.txt").write_text(payload_a, encoding="utf-8")
        (inbox / "IWM__quote__002.txt").write_text(payload_b, encoding="utf-8")

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
                "10",
            ]
        )
        capture_pages.run_capture(args)

        raw_files = sorted(x for x in store.rglob("*") if x.is_file())
        self.assertEqual(len(raw_files), 2)
        oldest = raw_files[0]
        newest = raw_files[1]
        os.utime(oldest, (1, 1))
        os.utime(newest, (2, 2))

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
                "0",
                "--max-store-mb",
                "1",
            ]
        )
        s = capture_pages.run_capture(args_ret)
        self.assertGreaterEqual(s["pruned_cap"], 1)
        self.assertLessEqual(s["bytes_on_disk"], 1024 * 1024)
        self.assertFalse(oldest.exists())
        self.assertTrue(newest.exists())

        con = dpl.connect_db(db)
        rows = con.execute("SELECT raw_path, status FROM captures ORDER BY id ASC").fetchall()
        con.close()
        status_by_path = {str(raw_path): status for raw_path, status in rows}
        self.assertEqual(status_by_path[oldest.as_posix()], "PRUNED")
        self.assertEqual(status_by_path[newest.as_posix()], "CAPTURED")

        log_lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(any('"event": "pruned_file"' in line and '"reason": "disk_cap"' in line for line in log_lines))


if __name__ == "__main__":
    unittest.main()
