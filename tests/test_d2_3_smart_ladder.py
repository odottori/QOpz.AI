import os
import unittest
from pathlib import Path

from execution.order_schema import Order
from execution.dry_run_adapter import execute_smart_limit
from execution.storage import init_execution_schema, _connect


class TestD2_3_SmartLadder(unittest.TestCase):
    def setUp(self):
        # Ensure runtime dirs exist (Phase0 requires them too)
        for d in ("db", "logs", "data", "reports"):
            Path(d).mkdir(parents=True, exist_ok=True)

        # Reset execution DB between tests (runtime-only, gitignored)
        for dbp in (Path("db/execution.duckdb"),):
            if dbp.exists():
                dbp.unlink(missing_ok=True)
        init_execution_schema()

    def _events(self, client_order_id: str):
        con = _connect()
        rows = con.execute(
            "SELECT event_type, details_json FROM order_events WHERE client_order_id=? ORDER BY ts_utc",
            (client_order_id,),
        ).fetchall()
        con.close()
        return rows

    def test_reject_on_wide_spread(self):
        o = Order(symbol="AAPL", side="BUY", quantity=1)
        cid = "D2_3_REJECT_1"
        res = execute_smart_limit(o, cid, run_id="T", profile="dev", bid=100.0, ask=101.0, tick=0.01, spread_reject_abs=0.50)
        self.assertEqual(res["status"], "REJECTED")
        ev = [e[0] for e in self._events(cid)]
        self.assertIn("REJECT_SPREAD", ev)

    def test_fill_on_step_2(self):
        o = Order(symbol="AAPL", side="BUY", quantity=1)
        cid = "D2_3_FILL_2"
        res = execute_smart_limit(o, cid, run_id="T", profile="dev", bid=100.00, ask=100.10, tick=0.05, spread_reject_abs=0.50, simulate_fill_step=2)
        self.assertEqual(res["status"], "FILLED")
        ev = [e[0] for e in self._events(cid)]
        # Step placed for 1 and 2, with timeout at step 1, fill at step 2
        self.assertIn("LADDER_STEP_PLACED", ev)
        self.assertIn("LADDER_STEP_TIMEOUT", ev)
        self.assertIn("FILLED", ev)

    def test_abandon_after_last_step(self):
        o = Order(symbol="AAPL", side="BUY", quantity=1)
        cid = "D2_3_ABANDON"
        res = execute_smart_limit(o, cid, run_id="T", profile="dev", bid=100.00, ask=100.10, tick=0.05, spread_reject_abs=0.50, simulate_fill_step=None)
        self.assertEqual(res["status"], "CANCELLED")
        ev = [e[0] for e in self._events(cid)]
        self.assertIn("ABANDON", ev)
        # 4 ladder steps placed
        self.assertEqual(ev.count("LADDER_STEP_PLACED"), 4)


if __name__ == "__main__":
    unittest.main()

