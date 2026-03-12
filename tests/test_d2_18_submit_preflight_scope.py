import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


class TestD2_18_SubmitPreflightScope(unittest.TestCase):
    def test_dev_rejects_env_when_core_dep_missing(self):
        from scripts import submit_order

        buf = io.StringIO()
        argv_prev = sys.argv
        try:
            sys.argv = [
                "submit_order.py",
                "--profile", "dev",
                "--symbol", "AAPL",
                "--side", "BUY",
                "--qty", "1",
                "--run-id", "TESTRUN",
                "--client-order-id", "TESTRUN-ORD-DEV-1",
            ]
            with patch("scripts.submit_order.preflight_core_deps", return_value=(False, "missing duckdb")):
                with redirect_stdout(buf):
                    code = submit_order.main()
        finally:
            sys.argv = argv_prev

        self.assertEqual(code, 2)
        payload = json.loads(buf.getvalue().strip())
        self.assertEqual(payload["status"], "REJECTED_ENV")

    def test_paper_ignores_core_dep_preflight_and_returns_boundary_status(self):
        from scripts import submit_order

        buf = io.StringIO()
        argv_prev = sys.argv
        try:
            sys.argv = [
                "submit_order.py",
                "--profile", "paper",
                "--symbol", "AAPL",
                "--side", "BUY",
                "--qty", "1",
                "--run-id", "TESTRUN",
                "--client-order-id", "TESTRUN-ORD-PAPER-1",
            ]
            with patch("scripts.submit_order.preflight_core_deps", return_value=(False, "missing duckdb")):
                with redirect_stdout(buf):
                    code = submit_order.main()
        finally:
            sys.argv = argv_prev

        self.assertEqual(code, 10)
        payload = json.loads(buf.getvalue().strip())
        self.assertEqual(payload["status"], "REJECTED_BROKER_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
