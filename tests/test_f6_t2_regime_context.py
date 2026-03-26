from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from fastapi.testclient import TestClient
from api.opz_api import app

CLIENT = TestClient(app, raise_server_exceptions=False)
ENDPOINT = "/opz/regime/context"


def _make_conn_mock(*, candidates: list[tuple], universe: list[tuple], trades: list[tuple]) -> MagicMock:
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
    conn.close.return_value = None
    return conn


class TestRegimeContext(unittest.TestCase):
    def test_context_uses_universe_when_opportunity_missing(self):
        conn = _make_conn_mock(
            candidates=[],
            universe=[("CAUTION", "2026-03-26T08:50:00"), ("CAUTION", "2026-03-26T08:40:00"), ("NORMAL", "2026-03-26T08:30:00")],
            trades=[],
        )
        with patch("duckdb.connect", return_value=conn), patch("pathlib.Path.exists", return_value=True):
            body = CLIENT.get(f"{ENDPOINT}?window=30").json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["resolved"]["source"], "universe")
        self.assertEqual(body["resolved"]["regime"], "CAUTION")
        self.assertEqual(body["sources"]["universe"]["sample_count"], 3)

    def test_context_prioritizes_opportunity(self):
        conn = _make_conn_mock(
            candidates=[("SHOCK", "2026-03-26T09:00:00"), ("SHOCK", "2026-03-26T08:59:00")],
            universe=[("NORMAL", "2026-03-26T08:50:00")],
            trades=[("CAUTION", "2026-03-26T08:10:00")],
        )
        with patch("duckdb.connect", return_value=conn), patch("pathlib.Path.exists", return_value=True):
            body = CLIENT.get(ENDPOINT).json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["resolved"]["source"], "opportunity")
        self.assertEqual(body["resolved"]["regime"], "SHOCK")
        self.assertEqual(body["sources"]["opportunity"]["sample_count"], 2)

    def test_context_empty_returns_unknown(self):
        conn = _make_conn_mock(candidates=[], universe=[], trades=[])
        with patch("duckdb.connect", return_value=conn), patch("pathlib.Path.exists", return_value=True):
            body = CLIENT.get(ENDPOINT).json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["resolved"]["source"], "none")
        self.assertEqual(body["resolved"]["regime"], "UNKNOWN")
        self.assertEqual(body["sources"]["opportunity"]["sample_count"], 0)
        self.assertEqual(body["sources"]["universe"]["sample_count"], 0)
        self.assertEqual(body["sources"]["paper_trade"]["sample_count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
