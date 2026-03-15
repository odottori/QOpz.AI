"""
tests/test_roc1_scan_api.py — ROC1-T2

Test suite per POST /opz/opportunity/scan_full:
  - 400 regime non valido
  - 400 symbols vuota (non SHOCK)
  - SHOCK -> 200, ranking_suspended=True, candidati vuoti
  - NORMAL -> 200, candidati, batch_id presente
  - batch_id formato hex 16 chars
  - errore scan_opportunities -> 502
  - errore save -> 200 ok (warning only, non blocca risposta)
  - data_mode watermark nella risposta
  - signal_map e signal_pct_map passati correttamente
  - candidati serializzati come dict (nessun dataclass grezzo)
  - save_opportunity_scan chiamato con batch_id e profile corretti
  - account_size e min_score forwarded a scan_opportunities
  - top_n rispettato (max candidati = top_n)
  - use_cache forwarded

Nessuna rete, nessun IBKR, nessun DB reale: tutto mockato.
"""
from __future__ import annotations

import dataclasses
import os
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, call, patch

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from fastapi.testclient import TestClient

from api.opz_api import app

CLIENT = TestClient(app, raise_server_exceptions=False)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_candidate(symbol: str = "TEST", score: float = 75.0):
    """Minimal OpportunityCandidate dataclass instance."""
    from strategy.opportunity_scanner import OpportunityCandidate
    return OpportunityCandidate(
        symbol=symbol,
        strategy="BULL_PUT",
        score=score,
        score_breakdown={"vol_edge": 20, "liquidity": 20, "risk_reward": 20, "regime_align": 15},
        expiry="2026-04-17",
        dte=33,
        strikes=[495.0, 490.0],
        delta=0.30,
        iv=0.28,
        iv_zscore_30=1.2,
        iv_zscore_60=0.9,
        iv_interp="expensive",
        expected_move=0.035,
        signal_vs_em_ratio=None,
        spread_pct=2.5,
        open_interest=500,
        volume=120,
        max_loss=160.0,
        max_loss_pct=1.6,
        breakeven=491.60,
        breakeven_pct=1.68,
        credit_or_debit=3.40,
        sizing_suggested=2.0,
        kelly_fraction=None,
        events_flag=None,
        human_review_required=False,
        stress_base=-96.0,
        stress_shock=-152.0,
        data_quality="cache",
        source="csv_delayed",
        underlying_price=500.0,
    )


def _make_scan_result(candidates=None, regime="NORMAL", suspended=False):
    """Minimal ScanResult."""
    from strategy.opportunity_scanner import ScanResult
    return ScanResult(
        profile="paper",
        regime=regime,
        data_mode="SYNTHETIC_SURFACE_CALIBRATED",
        scan_ts=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        symbols_scanned=1,
        symbols_with_chain=1,
        filtered_count=0,
        cache_used=True,
        cache_age_hours=0.5,
        candidates=candidates if candidates is not None else [_make_candidate()],
        ranking_suspended=suspended,
        suspension_reason="SHOCK regime — no new positions allowed" if suspended else None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1.  Validazione input
# ─────────────────────────────────────────────────────────────────────────────

class TestScanFullValidation(unittest.TestCase):
    def test_invalid_regime_returns_400(self):
        r = CLIENT.post("/opz/opportunity/scan_full", json={"regime": "PANIC", "symbols": ["TEST"]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("regime", r.text.lower())

    def test_empty_symbols_non_shock_returns_400(self):
        r = CLIENT.post("/opz/opportunity/scan_full", json={"regime": "NORMAL", "symbols": []})
        self.assertEqual(r.status_code, 400)

    def test_whitespace_only_symbols_returns_400(self):
        r = CLIENT.post("/opz/opportunity/scan_full", json={"regime": "NORMAL", "symbols": ["  ", " "]})
        self.assertEqual(r.status_code, 400)

    def test_shock_no_symbols_ok(self):
        """SHOCK con symbols vuota deve restituire 200 (sospeso, no crash)."""
        with patch("strategy.opportunity_scanner.scan_opportunities") as m:
            m.return_value = _make_scan_result(candidates=[], suspended=True, regime="SHOCK")
            with patch("execution.storage.init_execution_schema"):
                with patch("execution.storage.save_opportunity_scan"):
                    r = CLIENT.post("/opz/opportunity/scan_full", json={"regime": "SHOCK", "symbols": []})
        self.assertEqual(r.status_code, 200)

    def test_top_n_min_1(self):
        r = CLIENT.post("/opz/opportunity/scan_full", json={"regime": "NORMAL", "symbols": ["TEST"], "top_n": 0})
        self.assertEqual(r.status_code, 422)

    def test_top_n_max_50(self):
        r = CLIENT.post("/opz/opportunity/scan_full", json={"regime": "NORMAL", "symbols": ["TEST"], "top_n": 51})
        self.assertEqual(r.status_code, 422)

    def test_account_size_positive(self):
        r = CLIENT.post("/opz/opportunity/scan_full", json={"regime": "NORMAL", "symbols": ["TEST"], "account_size": 0})
        self.assertEqual(r.status_code, 422)

    def test_min_score_bounds(self):
        r = CLIENT.post("/opz/opportunity/scan_full", json={"regime": "NORMAL", "symbols": ["TEST"], "min_score": 101})
        self.assertEqual(r.status_code, 422)


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Risposta ok — NORMAL
# ─────────────────────────────────────────────────────────────────────────────

class TestScanFullOk(unittest.TestCase):

    def _call(self, payload=None, scan_result=None):
        if scan_result is None:
            scan_result = _make_scan_result()
        base = {"regime": "NORMAL", "symbols": ["TEST"], "profile": "paper"}
        if payload:
            base.update(payload)
        with patch("strategy.opportunity_scanner.scan_opportunities", return_value=scan_result):
            with patch("execution.storage.init_execution_schema"):
                with patch("execution.storage.save_opportunity_scan"):
                    return CLIENT.post("/opz/opportunity/scan_full", json=base)

    def test_status_200(self):
        self.assertEqual(self._call().status_code, 200)

    def test_ok_true(self):
        self.assertTrue(self._call().json()["ok"])

    def test_batch_id_present(self):
        body = self._call().json()
        self.assertIn("batch_id", body)
        self.assertIsInstance(body["batch_id"], str)
        self.assertGreater(len(body["batch_id"]), 0)

    def test_batch_id_is_hex_16(self):
        batch_id = self._call().json()["batch_id"]
        self.assertEqual(len(batch_id), 16)
        int(batch_id, 16)  # deve essere hex valido — solleva ValueError se no

    def test_data_mode_watermark(self):
        body = self._call().json()
        self.assertIn("data_mode", body)
        self.assertEqual(body["data_mode"], "SYNTHETIC_SURFACE_CALIBRATED")

    def test_candidates_list(self):
        body = self._call().json()
        self.assertIsInstance(body["candidates"], list)
        self.assertEqual(len(body["candidates"]), 1)

    def test_candidate_serialized_as_dict(self):
        """Candidati devono essere dict JSON-serializzabili, non dataclass."""
        body = self._call().json()
        c = body["candidates"][0]
        self.assertIsInstance(c, dict)
        self.assertEqual(c["symbol"], "TEST")
        self.assertEqual(c["strategy"], "BULL_PUT")

    def test_scan_ts_present(self):
        self.assertIn("scan_ts", self._call().json())

    def test_regime_echo(self):
        self.assertEqual(self._call().json()["regime"], "NORMAL")

    def test_profile_echo(self):
        self.assertEqual(self._call().json()["profile"], "paper")


# ─────────────────────────────────────────────────────────────────────────────
# 3.  SHOCK — sospeso
# ─────────────────────────────────────────────────────────────────────────────

class TestScanFullShock(unittest.TestCase):

    def _shock_call(self):
        result = _make_scan_result(candidates=[], suspended=True, regime="SHOCK")
        with patch("strategy.opportunity_scanner.scan_opportunities", return_value=result):
            with patch("execution.storage.init_execution_schema"):
                with patch("execution.storage.save_opportunity_scan"):
                    return CLIENT.post(
                        "/opz/opportunity/scan_full",
                        json={"regime": "SHOCK", "symbols": ["TEST"]},
                    )

    def test_shock_returns_200(self):
        self.assertEqual(self._shock_call().status_code, 200)

    def test_shock_ranking_suspended_true(self):
        self.assertTrue(self._shock_call().json()["ranking_suspended"])

    def test_shock_candidates_empty(self):
        self.assertEqual(self._shock_call().json()["candidates"], [])

    def test_shock_suspension_reason_present(self):
        body = self._shock_call().json()
        self.assertIsNotNone(body["suspension_reason"])
        self.assertIn("SHOCK", body["suspension_reason"])


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Errori
# ─────────────────────────────────────────────────────────────────────────────

class TestScanFullErrors(unittest.TestCase):

    def test_scan_raises_502(self):
        with patch(
            "strategy.opportunity_scanner.scan_opportunities",
            side_effect=RuntimeError("chain fetch failed"),
        ):
            with patch("execution.storage.init_execution_schema"):
                r = CLIENT.post(
                    "/opz/opportunity/scan_full",
                    json={"regime": "NORMAL", "symbols": ["TEST"]},
                )
        self.assertEqual(r.status_code, 502)
        body = r.json()
        self.assertIn("stage", body.get("detail", body))

    def test_save_failure_does_not_break_response(self):
        """Errore nel salvataggio DB → warning, ma risposta 200."""
        result = _make_scan_result()
        with patch("strategy.opportunity_scanner.scan_opportunities", return_value=result):
            with patch("execution.storage.init_execution_schema"):
                with patch(
                    "execution.storage.save_opportunity_scan",
                    side_effect=RuntimeError("db write error"),
                ):
                    r = CLIENT.post(
                        "/opz/opportunity/scan_full",
                        json={"regime": "NORMAL", "symbols": ["TEST"]},
                    )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])


# ─────────────────────────────────────────────────────────────────────────────
# 5.  Forwarding parametri a scan_opportunities
# ─────────────────────────────────────────────────────────────────────────────

class TestScanFullForwarding(unittest.TestCase):

    def _call_and_capture(self, payload: dict):
        result = _make_scan_result()
        mock_scan = MagicMock(return_value=result)
        with patch("strategy.opportunity_scanner.scan_opportunities", mock_scan):
            with patch("execution.storage.init_execution_schema"):
                with patch("execution.storage.save_opportunity_scan"):
                    CLIENT.post("/opz/opportunity/scan_full", json=payload)
        return mock_scan

    def test_account_size_forwarded(self):
        m = self._call_and_capture(
            {"regime": "NORMAL", "symbols": ["TEST"], "account_size": 25000}
        )
        _, kwargs = m.call_args
        self.assertEqual(kwargs["account_size"], 25000)

    def test_min_score_forwarded(self):
        m = self._call_and_capture(
            {"regime": "NORMAL", "symbols": ["TEST"], "min_score": 70.0}
        )
        _, kwargs = m.call_args
        self.assertEqual(kwargs["min_score"], 70.0)

    def test_top_n_forwarded(self):
        m = self._call_and_capture(
            {"regime": "NORMAL", "symbols": ["TEST", "SPY"], "top_n": 3}
        )
        _, kwargs = m.call_args
        self.assertEqual(kwargs["top_n"], 3)

    def test_use_cache_forwarded(self):
        m = self._call_and_capture(
            {"regime": "NORMAL", "symbols": ["TEST"], "use_cache": False}
        )
        _, kwargs = m.call_args
        self.assertFalse(kwargs["use_cache"])

    def test_signal_map_forwarded(self):
        m = self._call_and_capture(
            {"regime": "NORMAL", "symbols": ["TEST"], "signal_map": {"TEST": "bullish"}}
        )
        _, kwargs = m.call_args
        self.assertEqual(kwargs["signal_map"], {"TEST": "bullish"})

    def test_signal_pct_map_forwarded(self):
        m = self._call_and_capture(
            {"regime": "NORMAL", "symbols": ["TEST"], "signal_pct_map": {"TEST": 0.03}}
        )
        _, kwargs = m.call_args
        self.assertEqual(kwargs["signal_pct_map"], {"TEST": 0.03})

    def test_symbols_uppercased(self):
        m = self._call_and_capture(
            {"regime": "NORMAL", "symbols": ["test", "spy"]}
        )
        _, kwargs = m.call_args
        self.assertEqual(kwargs["symbols"], ["TEST", "SPY"])

    def test_regime_uppercased(self):
        m = self._call_and_capture(
            {"regime": "caution", "symbols": ["TEST"]}
        )
        _, kwargs = m.call_args
        self.assertEqual(kwargs["regime"], "CAUTION")

    def test_profile_forwarded(self):
        m = self._call_and_capture(
            {"regime": "NORMAL", "symbols": ["TEST"], "profile": "dev"}
        )
        _, kwargs = m.call_args
        self.assertEqual(kwargs["profile"], "dev")


# ─────────────────────────────────────────────────────────────────────────────
# 6.  Persistenza — save_opportunity_scan chiamato correttamente
# ─────────────────────────────────────────────────────────────────────────────

class TestScanFullPersistence(unittest.TestCase):

    def test_save_called_with_batch_id_and_profile(self):
        result = _make_scan_result()
        mock_save = MagicMock()
        with patch("strategy.opportunity_scanner.scan_opportunities", return_value=result):
            with patch("execution.storage.init_execution_schema"):
                with patch("execution.storage.save_opportunity_scan", mock_save):
                    r = CLIENT.post(
                        "/opz/opportunity/scan_full",
                        json={"regime": "NORMAL", "symbols": ["TEST"], "profile": "paper"},
                    )
        self.assertEqual(r.status_code, 200)
        mock_save.assert_called_once()
        _, kwargs = mock_save.call_args
        self.assertEqual(kwargs["profile"], "paper")
        batch_id = r.json()["batch_id"]
        self.assertEqual(kwargs["batch_id"], batch_id)

    def test_save_receives_scan_result_object(self):
        result = _make_scan_result()
        mock_save = MagicMock()
        with patch("strategy.opportunity_scanner.scan_opportunities", return_value=result):
            with patch("execution.storage.init_execution_schema"):
                with patch("execution.storage.save_opportunity_scan", mock_save):
                    CLIENT.post(
                        "/opz/opportunity/scan_full",
                        json={"regime": "NORMAL", "symbols": ["TEST"]},
                    )
        _, kwargs = mock_save.call_args
        self.assertIs(kwargs["scan_result"], result)


# ─────────────────────────────────────────────────────────────────────────────
# 7.  save_opportunity_scan — unit test diretto (senza DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveOpportunityScan(unittest.TestCase):
    """Testa save_opportunity_scan con un DB DuckDB su file temporaneo."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        import execution.storage as st

        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = st.EXEC_DB_PATH
        st.EXEC_DB_PATH = Path(self._tmpdir.name) / "test.duckdb"
        st._SCHEMA_READY = False

    def tearDown(self):
        import execution.storage as st
        st.EXEC_DB_PATH = self._orig_path
        st._SCHEMA_READY = False
        self._tmpdir.cleanup()

    def _query(self, sql: str):
        import execution.storage as st
        import duckdb
        con = duckdb.connect(str(st.EXEC_DB_PATH))
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()

    def test_save_inserts_candidate_row(self):
        from execution.storage import init_execution_schema, save_opportunity_scan
        init_execution_schema()
        result = _make_scan_result()
        save_opportunity_scan(batch_id="aabbccdd11223344", profile="paper", scan_result=result)

        rows = self._query("SELECT * FROM opportunity_candidates")
        self.assertEqual(len(rows), 1)

    def test_save_inserts_chain_snapshot(self):
        from execution.storage import init_execution_schema, save_opportunity_scan
        init_execution_schema()
        result = _make_scan_result()
        save_opportunity_scan(batch_id="aabbccdd11223344", profile="paper", scan_result=result)

        rows = self._query("SELECT * FROM opportunity_chain_snapshots")
        self.assertEqual(len(rows), 1)

    def test_save_batch_id_stored(self):
        from execution.storage import init_execution_schema, save_opportunity_scan
        init_execution_schema()
        bid = "deadbeef12345678"
        result = _make_scan_result()
        save_opportunity_scan(batch_id=bid, profile="paper", scan_result=result)

        row = self._query("SELECT batch_id FROM opportunity_candidates LIMIT 1")
        self.assertEqual(row[0][0], bid)

    def test_save_multiple_candidates_same_symbol_one_snapshot(self):
        from execution.storage import init_execution_schema, save_opportunity_scan
        init_execution_schema()
        result = _make_scan_result(candidates=[
            _make_candidate("TEST", 75.0),
            _make_candidate("TEST", 70.0),
        ])
        save_opportunity_scan(batch_id="batch001", profile="paper", scan_result=result)

        cand_rows = self._query("SELECT COUNT(*) FROM opportunity_candidates")[0][0]
        snap_rows = self._query("SELECT COUNT(*) FROM opportunity_chain_snapshots")[0][0]
        self.assertEqual(cand_rows, 2)
        self.assertEqual(snap_rows, 1)  # dedup per simbolo

    def test_save_two_symbols_two_snapshots(self):
        from execution.storage import init_execution_schema, save_opportunity_scan
        init_execution_schema()
        result = _make_scan_result(candidates=[
            _make_candidate("AAPL", 75.0),
            _make_candidate("SPY", 72.0),
        ])
        save_opportunity_scan(batch_id="batch002", profile="paper", scan_result=result)

        snap_rows = self._query("SELECT COUNT(*) FROM opportunity_chain_snapshots")[0][0]
        self.assertEqual(snap_rows, 2)

    def test_empty_candidates_no_rows(self):
        from execution.storage import init_execution_schema, save_opportunity_scan
        init_execution_schema()
        result = _make_scan_result(candidates=[])
        save_opportunity_scan(batch_id="emptybatch", profile="paper", scan_result=result)

        cand_rows = self._query("SELECT COUNT(*) FROM opportunity_candidates")[0][0]
        snap_rows = self._query("SELECT COUNT(*) FROM opportunity_chain_snapshots")[0][0]
        self.assertEqual(cand_rows, 0)
        self.assertEqual(snap_rows, 0)

    def test_ev_tracking_table_exists(self):
        from execution.storage import init_execution_schema
        init_execution_schema()
        rows = self._query("SELECT COUNT(*) FROM opportunity_ev_tracking")
        self.assertIsNotNone(rows)


if __name__ == "__main__":
    unittest.main(verbosity=2)
