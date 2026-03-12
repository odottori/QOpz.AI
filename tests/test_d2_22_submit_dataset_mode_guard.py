import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


class TestD2_22_SubmitDatasetModeGuard(unittest.TestCase):
    def _run_submit(self, argv):
        from scripts import submit_order

        buf = io.StringIO()
        prev = sys.argv
        try:
            sys.argv = ["submit_order.py", *argv]
            with redirect_stdout(buf):
                code = submit_order.main()
        finally:
            sys.argv = prev
        payload = json.loads(buf.getvalue().strip())
        return code, payload

    def test_paper_rejects_synthetic_mode_when_config_provided(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "paper.toml"
            cfg.write_text("[dataset]\nmode='synthetic'\n", encoding="utf-8")
            code, payload = self._run_submit([
                "--profile", "paper",
                "--config", str(cfg),
                "--symbol", "AAPL",
                "--side", "BUY",
                "--qty", "1",
                "--run-id", "TESTRUN",
                "--client-order-id", "TESTRUN-ORD-1",
            ])
        self.assertEqual(code, 10)
        self.assertEqual(payload["status"], "REJECTED_DATA_MODE")

    def test_paper_accepts_matching_mode_and_keeps_boundary_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "paper.toml"
            cfg.write_text("[dataset]\nmode='paper'\n", encoding="utf-8")
            code, payload = self._run_submit([
                "--profile", "paper",
                "--config", str(cfg),
                "--symbol", "AAPL",
                "--side", "BUY",
                "--qty", "1",
                "--run-id", "TESTRUN",
                "--client-order-id", "TESTRUN-ORD-2",
            ])
        self.assertEqual(code, 10)
        self.assertEqual(payload["status"], "REJECTED_BROKER_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
