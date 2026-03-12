import json
import unittest
from pathlib import Path
from uuid import uuid4

from scripts import run_backtest


def _case_root() -> Path:
    root = Path('.tmp_test') / f"case_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


class TestF2T5RunBacktest(unittest.TestCase):
    def _write_dataset(self, path: Path, prices: list[float]):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "capture_id,captured_ts_utc,source,symbol,page_type,observed_ts_utc,bid,ask,last,iv,delta,underlying_price,fingerprint_sha256,model,prompt_version,backend,raw_path,output_path"
        ]
        for i, px in enumerate(prices, start=1):
            lines.append(
                f"{i},2026-03-05T10:00:0{i}Z,ibkr_demo,IWM,quote,2026-03-05T10:00:0{i}Z,{px-0.1},{px+0.1},{px},0.25,0.2,210.0,fp{i},qwen2.5,v1,json-pass,raw{i},out{i}"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_backtest_pass_with_enough_returns(self):
        root = _case_root()
        ds = root / "datasets" / "demo_dataset.csv"
        out_dir = root / "reports"
        self._write_dataset(ds, [1.0, 1.1, 1.05, 1.2])

        rc = run_backtest.main(
            [
                "--dataset-csv",
                str(ds),
                "--out-dir",
                str(out_dir),
                "--run-name",
                "r1",
                "--min-returns",
                "2",
            ]
        )
        self.assertEqual(rc, 0)

        payload = json.loads((out_dir / "r1.json").read_text(encoding="utf-8"))
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["n_returns"], 2)

    def test_backtest_fails_with_too_few_returns(self):
        root = _case_root()
        ds = root / "datasets" / "demo_dataset.csv"
        out_dir = root / "reports"
        self._write_dataset(ds, [1.0, 1.01])

        rc = run_backtest.main(
            [
                "--dataset-csv",
                str(ds),
                "--out-dir",
                str(out_dir),
                "--run-name",
                "r2",
                "--min-returns",
                "5",
            ]
        )
        self.assertEqual(rc, 2)

        payload = json.loads((out_dir / "r2.json").read_text(encoding="utf-8"))
        self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
