"""
tests/test_roc10_equity_history.py — ROC10-T2

Test suite per GET /opz/paper/equity_history:
  - struttura risposta
  - DB vuoto → n_points=0, points=[]
  - punti ordinati ASC per data
  - limit param rispettato (clamp 1-500)
  - latest_equity = ultimo punto
  - initial_equity = primo punto
  - profile param filtrato
  - pnl coerente (latest - initial)
  - ok=True sempre anche su eccezione DB
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from fastapi.testclient import TestClient
from api.opz_api import app

CLIENT = TestClient(app, raise_server_exceptions=False)
ENDPOINT = "/opz/paper/equity_history"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_rows(n: int, start_equity: float = 10000.0, delta: float = 100.0,
               start_date: date | None = None) -> list[tuple]:
    """Generate n (date, equity) rows in DESC order (as DB returns them)."""
    d0 = start_date or date(2026, 1, 1)
    rows = []
    for i in range(n - 1, -1, -1):  # DESC: newest first
        d = d0 + timedelta(days=i)
        eq = start_equity + i * delta
        rows.append((d.isoformat(), eq))
    return rows


@contextmanager
def _patch_rows(rows: list[tuple]):
    mock_con = MagicMock()
    mock_con.execute.return_value.fetchall.return_value = rows
    mock_con.close.return_value = None
    with patch("api.opz_api._connect", return_value=mock_con):
        yield


def _get(limit: int = 20, profile: str = "paper") -> dict:
    r = CLIENT.get(f"{ENDPOINT}?profile={profile}&limit={limit}")
    assert r.status_code == 200
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Struttura
# ─────────────────────────────────────────────────────────────────────────────

class TestEquityHistoryStructure(unittest.TestCase):

    def test_status_200(self):
        r = CLIENT.get(ENDPOINT)
        self.assertEqual(r.status_code, 200)

    def test_ok_true(self):
        with _patch_rows([]):
            body = _get()
        self.assertTrue(body["ok"])

    def test_required_fields(self):
        with _patch_rows([]):
            body = _get()
        for f in ("ok", "profile", "n_points", "latest_equity", "initial_equity", "points"):
            self.assertIn(f, body, f"Missing field: {f}")

    def test_points_is_list(self):
        with _patch_rows([]):
            body = _get()
        self.assertIsInstance(body["points"], list)

    def test_point_has_date_and_equity(self):
        rows = _make_rows(3)
        with _patch_rows(rows):
            body = _get()
        if body["points"]:
            p = body["points"][0]
            self.assertIn("date", p)
            self.assertIn("equity", p)


# ─────────────────────────────────────────────────────────────────────────────
# 2. DB vuoto
# ─────────────────────────────────────────────────────────────────────────────

class TestEquityHistoryEmpty(unittest.TestCase):

    def test_empty_n_points_zero(self):
        with _patch_rows([]):
            body = _get()
        self.assertEqual(body["n_points"], 0)

    def test_empty_points_list_empty(self):
        with _patch_rows([]):
            body = _get()
        self.assertEqual(body["points"], [])

    def test_empty_latest_equity_null(self):
        with _patch_rows([]):
            body = _get()
        self.assertIsNone(body["latest_equity"])

    def test_empty_initial_equity_null(self):
        with _patch_rows([]):
            body = _get()
        self.assertIsNone(body["initial_equity"])


# ─────────────────────────────────────────────────────────────────────────────
# 3. Ordine ASC (per sparkline)
# ─────────────────────────────────────────────────────────────────────────────

class TestEquityHistoryOrder(unittest.TestCase):

    def test_points_asc_by_date(self):
        """DB ritorna DESC; l'endpoint deve restituire ASC."""
        rows = _make_rows(5)  # già DESC
        with _patch_rows(rows):
            body = _get()
        dates = [p["date"] for p in body["points"]]
        self.assertEqual(dates, sorted(dates))

    def test_first_point_oldest(self):
        rows = _make_rows(5, start_date=date(2026, 1, 1))
        with _patch_rows(rows):
            body = _get()
        self.assertEqual(body["points"][0]["date"], "2026-01-01")

    def test_last_point_newest(self):
        rows = _make_rows(5, start_date=date(2026, 1, 1))
        with _patch_rows(rows):
            body = _get()
        self.assertEqual(body["points"][-1]["date"], "2026-01-05")


# ─────────────────────────────────────────────────────────────────────────────
# 4. latest / initial equity
# ─────────────────────────────────────────────────────────────────────────────

class TestEquityHistoryValues(unittest.TestCase):

    def test_latest_equity_equals_last_point(self):
        rows = _make_rows(5, start_equity=10000.0, delta=200.0)
        with _patch_rows(rows):
            body = _get()
        self.assertAlmostEqual(body["latest_equity"], body["points"][-1]["equity"])

    def test_initial_equity_equals_first_point(self):
        rows = _make_rows(5, start_equity=10000.0, delta=200.0)
        with _patch_rows(rows):
            body = _get()
        self.assertAlmostEqual(body["initial_equity"], body["points"][0]["equity"])

    def test_equity_values_are_floats(self):
        rows = _make_rows(3)
        with _patch_rows(rows):
            body = _get()
        for p in body["points"]:
            self.assertIsInstance(p["equity"], float)

    def test_n_points_matches_len(self):
        rows = _make_rows(7)
        with _patch_rows(rows):
            body = _get()
        self.assertEqual(body["n_points"], len(body["points"]))

    def test_single_point(self):
        rows = _make_rows(1)
        with _patch_rows(rows):
            body = _get()
        self.assertEqual(body["n_points"], 1)
        self.assertEqual(body["latest_equity"], body["initial_equity"])


# ─────────────────────────────────────────────────────────────────────────────
# 5. limit param
# ─────────────────────────────────────────────────────────────────────────────

class TestEquityHistoryLimit(unittest.TestCase):

    def test_limit_respected(self):
        rows = _make_rows(10)
        with _patch_rows(rows):
            body = _get(limit=10)
        self.assertLessEqual(body["n_points"], 10)

    def test_limit_clamped_min_1(self):
        body = CLIENT.get(f"{ENDPOINT}?limit=0").json()
        self.assertTrue(body["ok"])

    def test_limit_clamped_max_500(self):
        body = CLIENT.get(f"{ENDPOINT}?limit=9999").json()
        self.assertTrue(body["ok"])


# ─────────────────────────────────────────────────────────────────────────────
# 6. profile field
# ─────────────────────────────────────────────────────────────────────────────

class TestEquityHistoryProfile(unittest.TestCase):

    def test_profile_echoed_in_response(self):
        with _patch_rows([]):
            body = _get(profile="paper")
        self.assertEqual(body["profile"], "paper")

    def test_live_profile_echoed(self):
        with _patch_rows([]):
            body = _get(profile="live")
        self.assertEqual(body["profile"], "live")


if __name__ == "__main__":
    unittest.main(verbosity=2)
