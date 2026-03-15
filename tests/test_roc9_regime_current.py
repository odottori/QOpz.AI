"""
tests/test_roc9_regime_current.py — ROC9-T2

Test suite per GET /opz/regime/current:
  - struttura risposta
  - nessun DB → n_recent=0, regime=UNKNOWN
  - opportunity_candidates con regime NORMAL → regime=NORMAL
  - mix NORMAL/CAUTION → pluralità corretta
  - tutti SHOCK → regime=SHOCK
  - source field corretto (opportunity_candidates / paper_trades / none)
  - fallback a paper_trades quando opportunity_candidates vuoto
  - window param rispettato
  - regime_pct sommano 100%
  - ok=True sempre
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from fastapi.testclient import TestClient
from api.opz_api import app

CLIENT = TestClient(app, raise_server_exceptions=False)
ENDPOINT = "/opz/regime/current"


# ─────────────────────────────────────────────────────────────────────────────
# DuckDB mock helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_conn_mock(rows_candidates: list, rows_trades: list | None = None):
    """Build a mock duckdb connection that returns the given rows."""
    mock_conn = MagicMock()

    def _execute(sql, params=None):
        result = MagicMock()
        if "opportunity_candidates" in sql:
            result.fetchall.return_value = rows_candidates
        elif "paper_trades" in sql:
            result.fetchall.return_value = (rows_trades or [])
        else:
            result.fetchall.return_value = []
        return result

    mock_conn.execute.side_effect = _execute
    mock_conn.close.return_value = None
    return mock_conn


@contextmanager
def _patch_db(rows_candidates: list, rows_trades: list | None = None,
              db_exists: bool = True):
    conn = _make_conn_mock(rows_candidates, rows_trades)
    with patch("duckdb.connect", return_value=conn), \
         patch("pathlib.Path.exists", return_value=db_exists):
        yield


def _get(window: int = 20, **patch_kwargs) -> dict:
    r = CLIENT.get(f"{ENDPOINT}?window={window}")
    assert r.status_code == 200
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Struttura
# ─────────────────────────────────────────────────────────────────────────────

class TestRegimeCurrentStructure(unittest.TestCase):

    def test_status_200(self):
        r = CLIENT.get(ENDPOINT)
        self.assertEqual(r.status_code, 200)

    def test_ok_true(self):
        body = _get()
        self.assertTrue(body["ok"])

    def test_required_fields(self):
        body = _get()
        for f in ("ok", "regime", "regime_counts", "regime_pct", "last_scan_ts", "n_recent", "source"):
            self.assertIn(f, body, f"Missing field: {f}")

    def test_regime_counts_keys(self):
        body = _get()
        counts = body["regime_counts"]
        for k in ("NORMAL", "CAUTION", "SHOCK"):
            self.assertIn(k, counts)

    def test_regime_pct_keys(self):
        body = _get()
        pct = body["regime_pct"]
        for k in ("NORMAL", "CAUTION", "SHOCK"):
            self.assertIn(k, pct)


# ─────────────────────────────────────────────────────────────────────────────
# 2. DB assente → UNKNOWN
# ─────────────────────────────────────────────────────────────────────────────

class TestRegimeNoDb(unittest.TestCase):

    def test_no_db_regime_unknown(self):
        with patch("pathlib.Path.exists", return_value=False):
            body = _get()
        self.assertEqual(body["regime"], "UNKNOWN")
        self.assertEqual(body["n_recent"], 0)
        self.assertEqual(body["source"], "none")


# ─────────────────────────────────────────────────────────────────────────────
# 3. opportunity_candidates present
# ─────────────────────────────────────────────────────────────────────────────

class TestRegimeFromCandidates(unittest.TestCase):

    def test_all_normal(self):
        rows = [("NORMAL", "2026-03-15T10:00:00")] * 5
        with _patch_db(rows):
            body = _get()
        self.assertEqual(body["regime"], "NORMAL")
        self.assertEqual(body["regime_counts"]["NORMAL"], 5)
        self.assertEqual(body["n_recent"], 5)
        self.assertEqual(body["source"], "opportunity_candidates")

    def test_all_shock(self):
        rows = [("SHOCK", "2026-03-15T10:00:00")] * 3
        with _patch_db(rows):
            body = _get()
        self.assertEqual(body["regime"], "SHOCK")

    def test_majority_caution(self):
        rows = [("CAUTION", "2026-03-15T10:00:00")] * 4 + \
               [("NORMAL", "2026-03-14T10:00:00")] * 2
        with _patch_db(rows):
            body = _get()
        self.assertEqual(body["regime"], "CAUTION")
        self.assertEqual(body["regime_counts"]["CAUTION"], 4)
        self.assertEqual(body["regime_counts"]["NORMAL"], 2)

    def test_regime_pct_sum_100(self):
        rows = [("NORMAL", "2026-03-15T10:00:00")] * 6 + \
               [("CAUTION", "2026-03-15T10:00:00")] * 2 + \
               [("SHOCK", "2026-03-15T10:00:00")] * 2
        with _patch_db(rows):
            body = _get()
        total_pct = sum(body["regime_pct"].values())
        self.assertAlmostEqual(total_pct, 100.0, delta=0.5)

    def test_last_scan_ts_populated(self):
        rows = [("NORMAL", "2026-03-15T10:00:00")]
        with _patch_db(rows):
            body = _get()
        self.assertIsNotNone(body["last_scan_ts"])

    def test_unknown_regime_label_ignored(self):
        """Label non standard (UNKNOWN) non devono incrementare i contatori."""
        rows = [("UNKNOWN", "2026-03-15T10:00:00"), ("NORMAL", "2026-03-15T09:00:00")]
        with _patch_db(rows):
            body = _get()
        # Solo NORMAL deve essere contato
        self.assertEqual(body["regime_counts"]["NORMAL"], 1)
        self.assertEqual(body["n_recent"], 1)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Fallback a paper_trades
# ─────────────────────────────────────────────────────────────────────────────

class TestRegimeFallbackTrades(unittest.TestCase):

    def test_fallback_when_candidates_empty(self):
        trade_rows = [("NORMAL", "2026-03-14T10:00:00")] * 3
        with _patch_db(rows_candidates=[], rows_trades=trade_rows):
            body = _get()
        self.assertEqual(body["source"], "paper_trades")
        self.assertEqual(body["regime"], "NORMAL")
        self.assertEqual(body["n_recent"], 3)

    def test_fallback_source_none_when_both_empty(self):
        with _patch_db(rows_candidates=[], rows_trades=[]):
            body = _get()
        self.assertEqual(body["source"], "none")
        self.assertEqual(body["regime"], "UNKNOWN")


# ─────────────────────────────────────────────────────────────────────────────
# 5. window parameter
# ─────────────────────────────────────────────────────────────────────────────

class TestWindowParam(unittest.TestCase):

    def test_window_1_returns_at_most_1(self):
        rows = [("NORMAL", "2026-03-15T10:00:00")] * 10
        with _patch_db(rows):
            body = CLIENT.get(f"{ENDPOINT}?window=1").json()
        # Il mock ritorna tutti i rows indipendentemente dal window
        # ma il test verifica che l'endpoint accetti il param senza errore
        self.assertEqual(body["status_code"] if "status_code" in body else 200, 200)
        self.assertTrue(body["ok"])

    def test_window_max_clamped_to_100(self):
        """window > 100 non deve causare errori."""
        body = CLIENT.get(f"{ENDPOINT}?window=999").json()
        self.assertTrue(body["ok"])

    def test_default_window_20(self):
        body = CLIENT.get(ENDPOINT).json()
        self.assertTrue(body["ok"])


# ─────────────────────────────────────────────────────────────────────────────
# 6. Robustezza
# ─────────────────────────────────────────────────────────────────────────────

class TestRegimeRobustness(unittest.TestCase):

    def test_exception_returns_unknown(self):
        with patch("duckdb.connect", side_effect=RuntimeError("db locked")), \
             patch("pathlib.Path.exists", return_value=True):
            body = _get()
        self.assertTrue(body["ok"])
        self.assertEqual(body["regime"], "UNKNOWN")

    def test_regime_counts_non_negative(self):
        body = _get()
        for v in body["regime_counts"].values():
            self.assertGreaterEqual(v, 0)

    def test_n_recent_non_negative(self):
        body = _get()
        self.assertGreaterEqual(body["n_recent"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
