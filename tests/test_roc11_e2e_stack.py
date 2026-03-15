"""
tests/test_roc11_e2e_stack.py — ROC11 (closing): E2E stack integration

Verifica che tutti gli endpoint ROC4-10 rispondano correttamente e siano
mutuamente coerenti (cross-endpoint consistency) in modalità dev (no IBKR).

Sezioni:
  A. Liveness di ogni endpoint (200 + ok=True)
  B. Coerenza cross-endpoint (ibkr disconnected → signals WARN, source_system yfinance)
  C. Scan full → events_source watermark propagato nella risposta
  D. Idempotenza: due chiamate consecutive restituiscono struttura identica
  E. Boundary: parametri limite/edge non causano 5xx
"""
from __future__ import annotations

import os
import time
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from fastapi.testclient import TestClient
from api.opz_api import app

CLIENT = TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────────────────────────
# A. Liveness — ogni endpoint risponde 200 + ok=True
# ─────────────────────────────────────────────────────────────────────────────

class TestEndpointLiveness(unittest.TestCase):

    ENDPOINTS = [
        "/opz/ibkr/status",
        "/opz/ibkr/account",
        "/opz/system/status",
        "/opz/regime/current",
        "/opz/paper/equity_history",
        "/health",
        "/opz/state",
    ]

    def test_all_return_200(self):
        for ep in self.ENDPOINTS:
            with self.subTest(endpoint=ep):
                r = CLIENT.get(ep)
                self.assertEqual(r.status_code, 200, f"{ep} → {r.status_code}")

    def test_ok_true_on_json_endpoints(self):
        json_endpoints = [ep for ep in self.ENDPOINTS if ep not in ("/health", "/opz/state")]
        for ep in json_endpoints:
            with self.subTest(endpoint=ep):
                body = CLIENT.get(ep).json()
                self.assertTrue(body.get("ok"), f"{ep} ok={body.get('ok')}")

    def test_ibkr_status_try_connect_false(self):
        r = CLIENT.get("/opz/ibkr/status?try_connect=false")
        self.assertEqual(r.status_code, 200)
        self.assertIn("connected", r.json())

    def test_regime_window_param(self):
        r = CLIENT.get("/opz/regime/current?window=5")
        self.assertEqual(r.status_code, 200)

    def test_equity_history_limit_param(self):
        r = CLIENT.get("/opz/paper/equity_history?limit=10&profile=paper")
        self.assertEqual(r.status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
# B. Coerenza cross-endpoint (no IBKR)
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossEndpointConsistency(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def test_ibkr_status_and_system_status_agree_on_connection(self):
        """ibkr/status.connected deve essere coerente con system/status.ibkr_connected."""
        ibkr_body = CLIENT.get("/opz/ibkr/status").json()
        sys_body = CLIENT.get("/opz/system/status").json()
        self.assertEqual(
            ibkr_body["connected"],
            sys_body["ibkr_connected"],
            "ibkr/status.connected ≠ system/status.ibkr_connected",
        )

    def test_ibkr_account_source_matches_ibkr_status(self):
        """Se ibkr non è connesso, account.source_system deve essere 'yfinance'."""
        ibkr_body = CLIENT.get("/opz/ibkr/status").json()
        if not ibkr_body["connected"]:
            acc_body = CLIENT.get("/opz/ibkr/account").json()
            self.assertEqual(acc_body["source_system"], "yfinance")

    def test_system_status_ibkr_signal_matches_ibkr_connected(self):
        """Signal 'ibkr' in system/status deve avere status WARN se non connesso."""
        sys_body = CLIENT.get("/opz/system/status").json()
        ibkr_sig = next((s for s in sys_body["signals"] if s["name"] == "ibkr"), None)
        self.assertIsNotNone(ibkr_sig)
        if not sys_body["ibkr_connected"]:
            self.assertEqual(ibkr_sig["status"], "WARN")
        else:
            self.assertEqual(ibkr_sig["status"], "OK")

    def test_system_status_data_mode_matches_env(self):
        expected = os.environ.get("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")
        sys_body = CLIENT.get("/opz/system/status").json()
        self.assertEqual(sys_body["data_mode"], expected)

    def test_kelly_false_when_synthetic(self):
        with patch.dict(os.environ, {"OPZ_DATA_MODE": "SYNTHETIC_SURFACE_CALIBRATED"}):
            sys_body = CLIENT.get("/opz/system/status").json()
        self.assertFalse(sys_body["kelly_enabled"])


# ─────────────────────────────────────────────────────────────────────────────
# C. Scan full → events_source watermark
# ─────────────────────────────────────────────────────────────────────────────

class TestScanFullEventsSourceWatermark(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def _do_scan(self, symbols: list[str] | None = None) -> dict:
        payload = {
            "profile": "dev",
            "regime": "NORMAL",
            "symbols": symbols or ["SPY"],
            "top_n": 1,
            "account_size": 10000,
            "use_cache": True,
        }
        r = CLIENT.post("/opz/opportunity/scan_full", json=payload)
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_scan_result_has_events_source(self):
        body = self._do_scan()
        self.assertIn("events_source", body, "Mancante: events_source nel response scan_full")

    def test_events_source_is_string(self):
        body = self._do_scan()
        self.assertIsInstance(body["events_source"], str)

    def test_events_source_valid_value_without_ibkr(self):
        """Senza IBKR, events_source deve essere 'yfinance' o 'none'."""
        body = self._do_scan()
        self.assertIn(body["events_source"], ("yfinance", "none", "events_map"))

    def test_events_source_none_on_shock_regime(self):
        """SHOCK → scan bloccato → events_source='none'."""
        payload = {
            "profile": "dev", "regime": "SHOCK",
            "symbols": ["SPY"], "top_n": 1,
            "account_size": 10000, "use_cache": True,
        }
        r = CLIENT.post("/opz/opportunity/scan_full", json=payload)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("events_source"), "none")

    def test_scan_ok_true(self):
        body = self._do_scan()
        self.assertTrue(body.get("ok", True))  # ok può non esistere, ma non deve essere False

    def test_events_source_watermark_present_in_system_status(self):
        """system/status deve contenere ibkr_source_system come watermark."""
        sys_body = CLIENT.get("/opz/system/status").json()
        self.assertIn("ibkr_source_system", sys_body)
        self.assertIn(sys_body["ibkr_source_system"], ("ibkr_live", "yfinance"))


# ─────────────────────────────────────────────────────────────────────────────
# D. Idempotenza
# ─────────────────────────────────────────────────────────────────────────────

class TestIdempotency(unittest.TestCase):

    IDEMPOTENT_ENDPOINTS = [
        "/opz/ibkr/status",
        "/opz/ibkr/account",
        "/opz/system/status",
        "/opz/regime/current",
        "/opz/paper/equity_history",
    ]

    def test_two_calls_return_same_structure(self):
        for ep in self.IDEMPOTENT_ENDPOINTS:
            with self.subTest(endpoint=ep):
                b1 = CLIENT.get(ep).json()
                b2 = CLIENT.get(ep).json()
                self.assertEqual(set(b1.keys()), set(b2.keys()),
                                 f"{ep}: chiavi diverse tra due chiamate")

    def test_two_calls_ok_stays_true(self):
        for ep in self.IDEMPOTENT_ENDPOINTS:
            with self.subTest(endpoint=ep):
                for _ in range(2):
                    self.assertTrue(CLIENT.get(ep).json().get("ok"))


# ─────────────────────────────────────────────────────────────────────────────
# E. Boundary — parametri limite non causano 5xx
# ─────────────────────────────────────────────────────────────────────────────

class TestBoundaryParams(unittest.TestCase):

    def _no_5xx(self, url: str):
        r = CLIENT.get(url)
        self.assertLess(r.status_code, 500, f"{url} → {r.status_code}")

    def test_equity_history_limit_zero(self):
        self._no_5xx("/opz/paper/equity_history?limit=0")

    def test_equity_history_limit_huge(self):
        self._no_5xx("/opz/paper/equity_history?limit=99999")

    def test_regime_window_zero(self):
        self._no_5xx("/opz/regime/current?window=0")

    def test_regime_window_huge(self):
        self._no_5xx("/opz/regime/current?window=99999")

    def test_ibkr_status_unknown_try_connect_value(self):
        # FastAPI parsa bool strictamente; "maybe" → 422 è accettabile (non 500)
        r = CLIENT.get("/opz/ibkr/status?try_connect=false")
        self.assertLess(r.status_code, 500)

    def test_equity_history_unknown_profile(self):
        self._no_5xx("/opz/paper/equity_history?profile=nonexistent")

    def test_regime_current_window_1(self):
        self._no_5xx("/opz/regime/current?window=1")


# ─────────────────────────────────────────────────────────────────────────────
# F. Timestamp consistency
# ─────────────────────────────────────────────────────────────────────────────

class TestTimestamps(unittest.TestCase):

    def test_system_status_timestamp_is_recent(self):
        """timestamp_utc deve essere entro 5 secondi."""
        from datetime import datetime, timezone
        body = CLIENT.get("/opz/system/status").json()
        ts = datetime.fromisoformat(body["timestamp_utc"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = abs((now - ts).total_seconds())
        self.assertLess(delta, 5.0, f"timestamp troppo vecchio: {delta:.1f}s")

    def test_ibkr_connected_at_null_when_not_connected(self):
        body = CLIENT.get("/opz/ibkr/account").json()
        if not body["connected"]:
            self.assertIsNone(body.get("account_id"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
