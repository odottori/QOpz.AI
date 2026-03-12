import unittest
import io
import json
import sys
from contextlib import redirect_stdout


from execution.boundary_adapter import make_adapter, BrokerUnavailableError, DevSimulationAdapter


class TestD2_11_AdapterBoundary(unittest.TestCase):
    def test_make_adapter_dev(self):
        ad = make_adapter("dev")
        self.assertIsInstance(ad, DevSimulationAdapter)
        res = ad.submit_limit(symbol="AAPL", side="BUY", qty=1, limit_price=100.0, run_id="R1", client_order_id="R1-1")
        self.assertEqual(res.client_order_id, "R1-1")
        self.assertEqual(res.ack.status.value, "ACKED")

    def test_make_adapter_paper_unavailable(self):
        ad = make_adapter("paper")
        with self.assertRaises(BrokerUnavailableError):
            ad.submit_limit(symbol="AAPL", side="BUY", qty=1, limit_price=100.0, run_id="R1", client_order_id="R1-1")

    def test_submit_cli_paper_rejects_broker_unavailable(self):
        # Import script module (PowerShell entrypoint wraps this).
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
                "--client-order-id", "TESTRUN-ORD-1",
            ]
            with redirect_stdout(buf):
                code = submit_order.main()
        finally:
            sys.argv = argv_prev

        self.assertEqual(code, 10)
        payload = json.loads(buf.getvalue().strip())
        self.assertEqual(payload["status"], "REJECTED_BROKER_UNAVAILABLE")
