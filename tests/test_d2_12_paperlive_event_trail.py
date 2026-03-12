import unittest
from pathlib import Path

from execution.boundary_adapter import make_adapter, BrokerUnavailableError

DUCK_PATH = Path("db/execution.duckdb")


class TestD2_12_PaperLiveEventTrail(unittest.TestCase):
    def setUp(self):
        if DUCK_PATH.exists():
            DUCK_PATH.unlink(missing_ok=True)

    def _fetch(self, sql: str, params: tuple):
        import duckdb  # type: ignore

        con = duckdb.connect(str(DUCK_PATH))
        try:
            return con.execute(sql, params).fetchall()
        finally:
            con.close()

    def _fetchone(self, sql: str, params: tuple):
        rows = self._fetch(sql, params)
        return rows[0] if rows else None

    def test_paper_unavailable_writes_journal_events(self):
        adapter = make_adapter("paper")
        with self.assertRaises(BrokerUnavailableError):
            adapter.submit_limit(
                symbol="AAPL",
                side="BUY",
                qty=1,
                limit_price=0.0,
                run_id="TESTRUN_D2_12",
                client_order_id="TESTRUN_D2_12-ORD-1",
            )

        events = self._fetch(
            "SELECT event_type FROM order_events WHERE client_order_id = ?",
            ("TESTRUN_D2_12-ORD-1",),
        )
        self.assertGreaterEqual(len(events), 2)
        event_types = [e[0] for e in events]
        self.assertIn("SUBMIT_ATTEMPT", event_types)
        self.assertIn("REJECTED_BROKER_UNAVAILABLE", event_types)

        row = self._fetchone(
            "SELECT state, outcome FROM orders WHERE client_order_id = ?",
            ("TESTRUN_D2_12-ORD-1",),
        )
        self.assertIsNotNone(row)
        state, outcome = row
        self.assertEqual(state, "REJECTED")
        self.assertEqual(outcome, "REJECTED_BROKER_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
