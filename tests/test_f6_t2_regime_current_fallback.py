from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from fastapi.testclient import TestClient
from api.opz_api import app

CLIENT = TestClient(app, raise_server_exceptions=False)
ENDPOINT = "/opz/regime/current"


def _mock_conn(*, candidates: list[tuple], universe: list[tuple], trades: list[tuple]) -> MagicMock:
    conn = MagicMock()

    def _execute(sql: str, _params=None):
        out = MagicMock()
        if "opportunity_candidates" in sql:
            out.fetchall.return_value = candidates
        elif "universe_scan_batches" in sql:
            out.fetchall.return_value = universe
        elif "paper_trades" in sql:
            out.fetchall.return_value = trades
        else:
            out.fetchall.return_value = []
        return out

    conn.execute.side_effect = _execute
    return conn


class TestRegimeCurrentFallback(unittest.TestCase):
    def test_uses_universe_batches_when_candidates_empty(self):
        conn = _mock_conn(
            candidates=[],
            universe=[("CAUTION", "2026-03-26T08:50:00"), ("CAUTION", "2026-03-26T08:40:00"), ("NORMAL", "2026-03-26T08:30:00")],
            trades=[],
        )
        with patch("duckdb.connect", return_value=conn), patch("pathlib.Path.exists", return_value=True):
            body = CLIENT.get(ENDPOINT).json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["source"], "universe_scan_batches")
        self.assertEqual(body["regime"], "CAUTION")
        self.assertEqual(body["n_recent"], 3)

    def test_candidates_keep_priority_over_universe(self):
        conn = _mock_conn(
            candidates=[("SHOCK", "2026-03-26T09:00:00"), ("SHOCK", "2026-03-26T08:59:00")],
            universe=[("NORMAL", "2026-03-26T08:50:00")],
            trades=[("CAUTION", "2026-03-26T08:10:00")],
        )
        with patch("duckdb.connect", return_value=conn), patch("pathlib.Path.exists", return_value=True):
            body = CLIENT.get(ENDPOINT).json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["source"], "opportunity_candidates")
        self.assertEqual(body["regime"], "SHOCK")
        self.assertEqual(body["n_recent"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
