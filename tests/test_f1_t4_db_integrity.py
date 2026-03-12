import unittest

import duckdb  # type: ignore

from scripts import db_integrity


class TestF1T4DbIntegrity(unittest.TestCase):
    def test_pass_on_seeded_synthetic(self):
        with duckdb.connect(":memory:") as con:
            db_integrity.seed_execution_synthetic(con, n_orders=200, events_per_order=2)
            res = db_integrity.run_execution_integrity_checks(con)
            self.assertTrue(res.ok, msg=res.errors)

    def test_fk_violation_detected(self):
        with duckdb.connect(":memory:") as con:
            db_integrity.seed_execution_synthetic(con, n_orders=5, events_per_order=1)
            # inject orphan event
            con.execute(
                "INSERT OR REPLACE INTO order_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("orphan", "missing_order", "run0", "dev", "EV", "S0", "S1", "2026-01-01T00:00:00Z", "{}"),
            )
            res = db_integrity.run_execution_integrity_checks(con)
            self.assertFalse(res.ok)
            self.assertTrue(any("FK violations" in e for e in res.errors))

    def test_pk_violation_detected(self):
        # break PK uniqueness by duplicating event_id in a table without PK.
        with duckdb.connect(":memory:") as con:
            con.execute("CREATE TABLE orders (client_order_id TEXT, run_id TEXT)")
            con.execute("CREATE TABLE order_events (event_id TEXT, client_order_id TEXT, ts_utc TEXT, event_type TEXT)")
            con.execute("INSERT INTO orders VALUES ('o1','r')")
            con.execute("INSERT INTO order_events VALUES ('e1','o1','2026-01-01T00:00:00Z','EV')")
            con.execute("INSERT INTO order_events VALUES ('e1','o1','2026-01-01T00:00:00Z','EV')")
            res = db_integrity.run_execution_integrity_checks(con)
            self.assertFalse(res.ok)
            self.assertTrue(any("PK not unique" in e for e in res.errors))


if __name__ == "__main__":
    unittest.main()
