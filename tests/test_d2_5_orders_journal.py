import math
import unittest
from pathlib import Path

from execution.dry_run_adapter import execute_smart_limit
from execution.order_schema import Order
from execution.storage import _connect, init_execution_schema


class TestD2_5_OrdersJournal(unittest.TestCase):
    """Domain 2.5 â€” Canonical orders ledger/journal (F3-T4).

    These checks mirror canonici/02_TEST.md Â§4.4:
      - COUNT(*) from orders equals orders submitted
      - fill_price is not NULL for filled
      - slippage computed as (fill_price - limit_price)/limit_price
      - ORDER BY timestamp produces a coherent sequence
    """

    def setUp(self):
        # Ensure runtime dirs exist (Phase0 requires them too)
        for d in ("db", "logs", "data", "reports"):
            Path(d).mkdir(parents=True, exist_ok=True)

        # Reset execution DB between tests (runtime-only, gitignored)
        for dbp in (Path("db/execution.duckdb"),):
            if dbp.exists():
                dbp.unlink(missing_ok=True)
        init_execution_schema()

    def test_f3_t4_logging_and_journal_queries(self):
        o = Order(symbol="AAPL", side="BUY", quantity=1)

        # 1) Filled scenario
        execute_smart_limit(
            o,
            "D2_5_FILL_1",
            run_id="T",
            profile="dev",
            bid=100.00,
            ask=100.10,
            tick=0.05,
            spread_reject_abs=0.50,
            simulate_fill_step=2,
        )

        # 2) Abandon scenario
        execute_smart_limit(
            o,
            "D2_5_ABANDON_1",
            run_id="T",
            profile="dev",
            bid=100.00,
            ask=100.10,
            tick=0.05,
            spread_reject_abs=0.50,
            simulate_fill_step=None,
        )

        # 3) Reject scenario (spread > 10%)
        execute_smart_limit(
            o,
            "D2_5_REJECT_1",
            run_id="T",
            profile="dev",
            bid=100.0,
            ask=130.0,  # 30% spread vs mid
            tick=0.01,
            spread_reject_abs=None,
        )

        con = _connect()

        # Ogni ordine loggato
        n = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        self.assertEqual(int(n), 3)

        # Fill price registrata (â‰  NULL per filled)
        filled = con.execute(
            "SELECT limit_price, fill_price, slippage, status FROM orders WHERE client_order_id=?",
            ("D2_5_FILL_1",),
        ).fetchone()
        self.assertIsNotNone(filled)
        limit_price, fill_price, slippage, status = filled
        self.assertEqual(status, "FILLED")
        self.assertIsNotNone(fill_price)
        self.assertIsNotNone(limit_price)

        # Slippage calcolato (realistico)
        expected = (float(fill_price) - float(limit_price)) / float(limit_price)
        self.assertTrue(math.isfinite(float(slippage)))
        self.assertAlmostEqual(float(slippage), expected, places=10)

        # Timestamp precisi: ORDER BY timestamp deve restituire 3 righe con timestamp non-null
        rows = con.execute(
            "SELECT client_order_id, timestamp FROM orders ORDER BY timestamp"
        ).fetchall()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r[1] is not None for r in rows))

        con.close()


if __name__ == "__main__":
    unittest.main()

