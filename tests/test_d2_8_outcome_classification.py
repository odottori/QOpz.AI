import unittest
from pathlib import Path

from execution.dry_run_adapter import execute_smart_limit
from execution.order_schema import Order
from execution.storage import _connect, init_execution_schema
from execution.reconcile import reconcile


class TestD2_8_OutcomeClassification(unittest.TestCase):
    def setUp(self):
        for d in ("db", "logs", "data", "reports"):
            Path(d).mkdir(parents=True, exist_ok=True)

        # Reset runtime DB between tests
        for dbp in (Path("db/execution.duckdb"),):
            if dbp.exists():
                dbp.unlink(missing_ok=True)
        init_execution_schema()

    def test_outcome_rejected_on_wide_spread(self):
        o = Order(symbol="AAPL", side="BUY", quantity=1)
        execute_smart_limit(
            o,
            "D2_8_REJECT_1",
            run_id="R",
            profile="dev",
            bid=100.0,
            ask=130.0,
            tick=0.01,
        )

        con = _connect()
        row = con.execute(
            "SELECT state, outcome FROM orders WHERE client_order_id=?",
            ("D2_8_REJECT_1",),
        ).fetchone()
        con.close()
        self.assertEqual(row[0], "REJECTED")
        self.assertEqual(row[1], "REJECTED")

        self.assertTrue(reconcile(run_id="R")["ok"])

    def test_outcome_filled(self):
        o = Order(symbol="AAPL", side="BUY", quantity=1)
        execute_smart_limit(
            o,
            "D2_8_FILL_1",
            run_id="R",
            profile="dev",
            bid=100.0,
            ask=100.1,
            tick=0.05,
            spread_reject_abs=0.50,
            simulate_fill_step=2,
        )

        con = _connect()
        row = con.execute(
            "SELECT state, outcome, fill_price FROM orders WHERE client_order_id=?",
            ("D2_8_FILL_1",),
        ).fetchone()
        con.close()
        self.assertEqual(row[0], "FILLED")
        self.assertEqual(row[1], "FILLED")
        self.assertIsNotNone(row[2])

        self.assertTrue(reconcile(run_id="R")["ok"])

    def test_outcome_abandoned(self):
        o = Order(symbol="AAPL", side="BUY", quantity=1)
        execute_smart_limit(
            o,
            "D2_8_ABANDON_1",
            run_id="R",
            profile="dev",
            bid=100.0,
            ask=100.1,
            tick=0.05,
            spread_reject_abs=0.50,
            simulate_fill_step=None,
        )

        con = _connect()
        row = con.execute(
            "SELECT state, outcome FROM orders WHERE client_order_id=?",
            ("D2_8_ABANDON_1",),
        ).fetchone()
        con.close()
        self.assertEqual(row[0], "CANCELLED")
        self.assertEqual(row[1], "ABANDONED")

        self.assertTrue(reconcile(run_id="R")["ok"])

    def test_outcome_timeout_simulated(self):
        o = Order(symbol="AAPL", side="BUY", quantity=1)
        execute_smart_limit(
            o,
            "D2_8_TIMEOUT_1",
            run_id="R",
            profile="dev",
            bid=100.0,
            ask=100.1,
            tick=0.05,
            spread_reject_abs=0.50,
            simulate_fill_step=None,
            simulate_timeout_step=2,
        )

        con = _connect()
        row = con.execute(
            "SELECT state, outcome FROM orders WHERE client_order_id=?",
            ("D2_8_TIMEOUT_1",),
        ).fetchone()
        con.close()
        self.assertEqual(row[0], "CANCELLED")
        self.assertEqual(row[1], "TIMEOUT")

        self.assertTrue(reconcile(run_id="R")["ok"])


if __name__ == "__main__":
    unittest.main()

