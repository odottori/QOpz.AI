"""
tests/test_roc3_ev_report.py — ROC3-T3

Test suite per GET /opz/opportunity/ev_report:
  - DB vuoto → ok, total_candidates=0
  - window_days invalido → 400
  - candidati presenti → conteggi corretti
  - score_distribution corretto (<70 / 70-80 / 80+)
  - strategies e regimes aggregati
  - human_review_required conta correttamente
  - events_flagged conta correttamente
  - window_days filtra per data (solo candidati nel range)
  - data_mode restituisce il watermark corretto
  - total_tracked da opportunity_ev_tracking

Nessun DB reale: usa tempdir per isolare ogni test.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from fastapi.testclient import TestClient
from api.opz_api import app

CLIENT = TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

class _TmpDb:
    """Context manager: swap EXEC_DB_PATH con un DB temporaneo per il test."""

    def __enter__(self):
        import execution.storage as st
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig = st.EXEC_DB_PATH
        st.EXEC_DB_PATH = Path(self._tmpdir.name) / "test.duckdb"
        st._SCHEMA_READY = False
        from execution.storage import init_execution_schema
        init_execution_schema()
        self._st = st
        return st.EXEC_DB_PATH, st

    def __exit__(self, *_):
        self._st.EXEC_DB_PATH = self._orig
        self._st._SCHEMA_READY = False
        self._tmpdir.cleanup()


def _insert_candidate(
    db_path: Path,
    *,
    profile: str = "paper",
    scan_ts: str | None = None,
    score: float = 72.0,
    strategy: str = "BULL_PUT",
    regime: str = "NORMAL",
    human_review: bool = False,
    events_flag: str | None = None,
    data_mode: str = "SYNTHETIC_SURFACE_CALIBRATED",
):
    import duckdb, uuid
    if scan_ts is None:
        scan_ts = datetime.now(timezone.utc).isoformat()
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            INSERT INTO opportunity_candidates (
                candidate_id, batch_id, profile, scan_ts, regime, data_mode,
                symbol, strategy, score,
                score_breakdown_json, expiry, dte, strikes_json,
                delta, iv, spread_pct, open_interest, volume,
                max_loss, max_loss_pct, breakeven, breakeven_pct,
                credit_or_debit, sizing_suggested,
                human_review_required, events_flag,
                stress_base, stress_shock,
                data_quality, source, underlying_price,
                source_system, source_mode, source_quality, asof_ts, received_ts
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(uuid.uuid4()), "testbatch", profile, scan_ts, regime, data_mode,
                "TEST", strategy, score,
                "{}", "2026-04-17", 33, "[495.0,490.0]",
                0.30, 0.28, 2.5, 500, 120,
                160.0, 1.6, 491.60, 1.68,
                3.40, 2.0,
                human_review, events_flag,
                -96.0, -152.0,
                "cache", "csv_delayed", 500.0,
                "qopz_ai", data_mode, profile,
                scan_ts, scan_ts,
            ),
        )
        if hasattr(con, "commit"):
            con.commit()
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Validazione input
# ─────────────────────────────────────────────────────────────────────────────

class TestEvReportValidation(unittest.TestCase):

    def test_window_days_zero_returns_400(self):
        r = CLIENT.get("/opz/opportunity/ev_report?window_days=0")
        self.assertEqual(r.status_code, 400)

    def test_window_days_366_returns_400(self):
        r = CLIENT.get("/opz/opportunity/ev_report?window_days=366")
        self.assertEqual(r.status_code, 400)

    def test_window_days_365_ok(self):
        with _TmpDb():
            r = CLIENT.get("/opz/opportunity/ev_report?window_days=365")
        self.assertEqual(r.status_code, 200)

    def test_default_params_ok(self):
        with _TmpDb():
            r = CLIENT.get("/opz/opportunity/ev_report")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])


# ─────────────────────────────────────────────────────────────────────────────
# 2. DB vuoto
# ─────────────────────────────────────────────────────────────────────────────

class TestEvReportEmptyDb(unittest.TestCase):

    def test_empty_db_returns_ok(self):
        with _TmpDb():
            r = CLIENT.get("/opz/opportunity/ev_report?profile=paper")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_empty_db_total_zero(self):
        with _TmpDb():
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        self.assertEqual(body["total_candidates"], 0)

    def test_empty_db_tracked_zero(self):
        with _TmpDb():
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        self.assertEqual(body["total_tracked"], 0)

    def test_empty_db_score_dist_zeros(self):
        with _TmpDb():
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        sd = body["score_distribution"]
        self.assertEqual(sd["below_70"], 0)
        self.assertEqual(sd["score_70_80"], 0)
        self.assertEqual(sd["score_80_plus"], 0)

    def test_empty_db_watermark_present(self):
        with _TmpDb():
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        self.assertIn("data_mode", body)
        self.assertTrue(len(body["data_mode"]) > 0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Conteggi con candidati
# ─────────────────────────────────────────────────────────────────────────────

class TestEvReportCounts(unittest.TestCase):

    def test_total_candidates_counted(self):
        with _TmpDb() as (db_path, _st):
            _insert_candidate(db_path, score=65.0)
            _insert_candidate(db_path, score=75.0)
            _insert_candidate(db_path, score=82.0)
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        self.assertEqual(body["total_candidates"], 3)

    def test_score_below_70(self):
        with _TmpDb() as (db_path, _st):
            _insert_candidate(db_path, score=65.0)
            _insert_candidate(db_path, score=69.9)
            _insert_candidate(db_path, score=75.0)
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        self.assertEqual(body["score_distribution"]["below_70"], 2)

    def test_score_70_80(self):
        with _TmpDb() as (db_path, _st):
            _insert_candidate(db_path, score=70.0)
            _insert_candidate(db_path, score=79.9)
            _insert_candidate(db_path, score=80.0)  # non in 70-80
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        self.assertEqual(body["score_distribution"]["score_70_80"], 2)

    def test_score_80_plus(self):
        with _TmpDb() as (db_path, _st):
            _insert_candidate(db_path, score=80.0)
            _insert_candidate(db_path, score=85.0)
            _insert_candidate(db_path, score=75.0)  # non in 80+
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        self.assertEqual(body["score_distribution"]["score_80_plus"], 2)

    def test_strategies_aggregated(self):
        with _TmpDb() as (db_path, _st):
            _insert_candidate(db_path, strategy="BULL_PUT")
            _insert_candidate(db_path, strategy="BULL_PUT")
            _insert_candidate(db_path, strategy="IRON_CONDOR")
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        self.assertEqual(body["strategies"]["BULL_PUT"], 2)
        self.assertEqual(body["strategies"]["IRON_CONDOR"], 1)

    def test_regimes_aggregated(self):
        with _TmpDb() as (db_path, _st):
            _insert_candidate(db_path, regime="NORMAL")
            _insert_candidate(db_path, regime="NORMAL")
            _insert_candidate(db_path, regime="CAUTION")
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        self.assertEqual(body["regimes"]["NORMAL"], 2)
        self.assertEqual(body["regimes"]["CAUTION"], 1)

    def test_human_review_count(self):
        with _TmpDb() as (db_path, _st):
            _insert_candidate(db_path, human_review=True)
            _insert_candidate(db_path, human_review=True)
            _insert_candidate(db_path, human_review=False)
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        self.assertEqual(body["human_review_required"], 2)

    def test_events_flagged_count(self):
        with _TmpDb() as (db_path, _st):
            _insert_candidate(db_path, events_flag="EARNINGS_7D")
            _insert_candidate(db_path, events_flag="DIVIDEND_5D")
            _insert_candidate(db_path, events_flag=None)
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        self.assertEqual(body["events_flagged"], 2)

    def test_data_mode_from_candidates(self):
        with _TmpDb() as (db_path, _st):
            _insert_candidate(db_path, data_mode="SYNTHETIC_SURFACE_CALIBRATED")
            body = CLIENT.get("/opz/opportunity/ev_report").json()
        self.assertIn("SYNTHETIC_SURFACE_CALIBRATED", body["data_mode"])


# ─────────────────────────────────────────────────────────────────────────────
# 4. Filtro per window_days
# ─────────────────────────────────────────────────────────────────────────────

class TestEvReportWindowFilter(unittest.TestCase):

    def test_old_candidates_excluded(self):
        """Candidati con scan_ts > window_days fa devono essere esclusi."""
        with _TmpDb() as (db_path, _st):
            recent = datetime.now(timezone.utc).isoformat()
            old    = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
            _insert_candidate(db_path, scan_ts=recent, score=75.0)
            _insert_candidate(db_path, scan_ts=old,    score=80.0)
            body = CLIENT.get("/opz/opportunity/ev_report?window_days=30").json()
        # Solo il candidato recente deve essere contato
        self.assertEqual(body["total_candidates"], 1)

    def test_all_recent_included(self):
        with _TmpDb() as (db_path, _st):
            for _ in range(3):
                _insert_candidate(db_path)
            body = CLIENT.get("/opz/opportunity/ev_report?window_days=30").json()
        self.assertEqual(body["total_candidates"], 3)

    def test_profile_isolation(self):
        """Candidati di un altro profilo non devono comparire."""
        with _TmpDb() as (db_path, _st):
            _insert_candidate(db_path, profile="paper")
            _insert_candidate(db_path, profile="live")
            body = CLIENT.get("/opz/opportunity/ev_report?profile=paper").json()
        self.assertEqual(body["total_candidates"], 1)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Struttura risposta
# ─────────────────────────────────────────────────────────────────────────────

class TestEvReportStructure(unittest.TestCase):

    def _get(self):
        with _TmpDb():
            return CLIENT.get("/opz/opportunity/ev_report").json()

    def test_ok_field(self):
        self.assertTrue(self._get()["ok"])

    def test_profile_field(self):
        with _TmpDb():
            body = CLIENT.get("/opz/opportunity/ev_report?profile=paper").json()
        self.assertEqual(body["profile"], "paper")

    def test_window_days_echo(self):
        with _TmpDb():
            body = CLIENT.get("/opz/opportunity/ev_report?window_days=14").json()
        self.assertEqual(body["window_days"], 14)

    def test_generated_at_present(self):
        body = self._get()
        self.assertIn("generated_at", body)
        self.assertIsInstance(body["generated_at"], str)

    def test_required_keys_present(self):
        body = self._get()
        for key in ("ok", "profile", "window_days", "generated_at", "data_mode",
                    "total_candidates", "total_tracked", "score_distribution",
                    "strategies", "regimes", "human_review_required", "events_flagged"):
            self.assertIn(key, body, f"Chiave mancante: {key}")

    def test_score_distribution_keys(self):
        body = self._get()
        sd = body["score_distribution"]
        for key in ("below_70", "score_70_80", "score_80_plus"):
            self.assertIn(key, sd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
