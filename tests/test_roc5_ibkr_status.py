"""
tests/test_roc5_ibkr_status.py — ROC5-T3

Test suite per GET /opz/ibkr/status:
  - risposta struttura corretta (ok, connected, host, port, source_system, ...)
  - try_connect=false (default) → non tenta connessione
  - try_connect=true → chiama mgr.try_connect()
  - quando connesso → source_system="ibkr_live", port valorizzato
  - quando non connesso → source_system="yfinance", port=null
  - ports_probed sempre presente
  - message sempre stringa non vuota
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from fastapi.testclient import TestClient
from api.opz_api import app

CLIENT = TestClient(app, raise_server_exceptions=False)

ENDPOINT = "/opz/ibkr/status"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_mock_manager(connected: bool, port: int | None = None) -> MagicMock:
    mgr = MagicMock()
    mgr.is_connected = connected
    mgr.try_connect.return_value = connected
    mgr.connection_info.return_value = {
        "connected":     connected,
        "host":          "127.0.0.1",
        "port":          port,
        "client_id":     10,
        "source_system": "ibkr_live" if connected else "yfinance",
        "connected_at":  "2026-03-15T10:00:00+00:00" if connected else None,
    }
    return mgr


# ─────────────────────────────────────────────────────────────────────────────
# 1. Struttura risposta
# ─────────────────────────────────────────────────────────────────────────────

class TestIbkrStatusStructure(unittest.TestCase):

    def _get(self, **kwargs):
        from execution.ibkr_connection import reset_manager
        reset_manager()
        mock_mgr = _make_mock_manager(connected=False)
        with patch("execution.ibkr_connection.get_manager", return_value=mock_mgr), \
             patch("execution.ibkr_connection.IBKR_PORTS", [7497, 4002]):
            qs = "&".join(f"{k}={v}" for k, v in kwargs.items())
            url = f"{ENDPOINT}?{qs}" if qs else ENDPOINT
            return CLIENT.get(url)

    def test_status_200(self):
        r = self._get()
        self.assertEqual(r.status_code, 200)

    def test_ok_true(self):
        r = self._get()
        self.assertTrue(r.json()["ok"])

    def test_required_keys_present(self):
        body = self._get().json()
        for key in ("ok", "connected", "host", "port", "client_id",
                    "source_system", "connected_at", "ports_probed", "message"):
            self.assertIn(key, body, f"Chiave mancante: {key}")

    def test_ports_probed_is_list(self):
        body = self._get().json()
        self.assertIsInstance(body["ports_probed"], list)
        self.assertGreater(len(body["ports_probed"]), 0)

    def test_message_is_nonempty_string(self):
        body = self._get().json()
        self.assertIsInstance(body["message"], str)
        self.assertGreater(len(body["message"]), 0)

    def test_host_is_string(self):
        body = self._get().json()
        self.assertIsInstance(body["host"], str)

    def test_client_id_is_int(self):
        body = self._get().json()
        self.assertIsInstance(body["client_id"], int)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Stato disconnesso
# ─────────────────────────────────────────────────────────────────────────────

class TestIbkrStatusDisconnected(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def _get_disconnected(self, try_connect: bool = False):
        mock_mgr = _make_mock_manager(connected=False)
        with patch("execution.ibkr_connection.get_manager", return_value=mock_mgr):
            return CLIENT.get(f"{ENDPOINT}?try_connect={str(try_connect).lower()}"), mock_mgr

    def test_disconnected_connected_false(self):
        r, _ = self._get_disconnected()
        self.assertFalse(r.json()["connected"])

    def test_disconnected_port_null(self):
        r, _ = self._get_disconnected()
        self.assertIsNone(r.json()["port"])

    def test_disconnected_source_system_yfinance(self):
        r, _ = self._get_disconnected()
        self.assertEqual(r.json()["source_system"], "yfinance")

    def test_disconnected_connected_at_null(self):
        r, _ = self._get_disconnected()
        self.assertIsNone(r.json()["connected_at"])

    def test_default_no_try_connect_not_called(self):
        """try_connect=false (default) → mgr.try_connect() NON viene chiamato."""
        r, mock_mgr = self._get_disconnected(try_connect=False)
        mock_mgr.try_connect.assert_not_called()

    def test_try_connect_false_explicit_not_called(self):
        r, mock_mgr = self._get_disconnected(try_connect=False)
        mock_mgr.try_connect.assert_not_called()

    def test_try_connect_true_calls_try_connect(self):
        """try_connect=true → mgr.try_connect() viene chiamato."""
        mock_mgr = _make_mock_manager(connected=False)
        with patch("execution.ibkr_connection.get_manager", return_value=mock_mgr):
            CLIENT.get(f"{ENDPOINT}?try_connect=true")
        mock_mgr.try_connect.assert_called_once()

    def test_message_mentions_yfinance_on_try_connect_fail(self):
        """Quando try_connect=true e non connesso → messaggio menziona yfinance o non disponibile."""
        mock_mgr = _make_mock_manager(connected=False)
        with patch("execution.ibkr_connection.get_manager", return_value=mock_mgr):
            r = CLIENT.get(f"{ENDPOINT}?try_connect=true")
        msg = r.json()["message"].lower()
        self.assertTrue("yfinance" in msg or "non disponibile" in msg or "fallback" in msg)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Stato connesso
# ─────────────────────────────────────────────────────────────────────────────

class TestIbkrStatusConnected(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def _get_connected(self, port: int = 7497):
        mock_mgr = _make_mock_manager(connected=True, port=port)
        with patch("execution.ibkr_connection.get_manager", return_value=mock_mgr):
            return CLIENT.get(ENDPOINT), mock_mgr

    def test_connected_true(self):
        r, _ = self._get_connected()
        self.assertTrue(r.json()["connected"])

    def test_connected_port_valorizzato(self):
        r, _ = self._get_connected(port=7497)
        self.assertEqual(r.json()["port"], 7497)

    def test_connected_source_system_ibkr_live(self):
        r, _ = self._get_connected()
        self.assertEqual(r.json()["source_system"], "ibkr_live")

    def test_connected_at_not_null(self):
        r, _ = self._get_connected()
        self.assertIsNotNone(r.json()["connected_at"])

    def test_connected_message_mentions_port(self):
        r, _ = self._get_connected(port=7497)
        msg = r.json()["message"]
        self.assertIn("7497", msg)

    def test_connected_no_try_connect_when_already_connected(self):
        """Se già connesso, try_connect=true non ri-tenta (is_connected=True guard)."""
        mock_mgr = _make_mock_manager(connected=True, port=7497)
        with patch("execution.ibkr_connection.get_manager", return_value=mock_mgr):
            CLIENT.get(f"{ENDPOINT}?try_connect=true")
        # try_connect viene chiamato solo se not is_connected → non deve essere chiamato
        mock_mgr.try_connect.assert_not_called()

    def test_gateway_port_4002(self):
        r, _ = self._get_connected(port=4002)
        self.assertEqual(r.json()["port"], 4002)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Ports probed
# ─────────────────────────────────────────────────────────────────────────────

class TestIbkrStatusPortsProbed(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def test_ports_probed_contains_7497(self):
        mock_mgr = _make_mock_manager(connected=False)
        with patch("execution.ibkr_connection.get_manager", return_value=mock_mgr):
            r = CLIENT.get(ENDPOINT)
        self.assertIn(7497, r.json()["ports_probed"])

    def test_ports_probed_contains_4002(self):
        mock_mgr = _make_mock_manager(connected=False)
        with patch("execution.ibkr_connection.get_manager", return_value=mock_mgr):
            r = CLIENT.get(ENDPOINT)
        self.assertIn(4002, r.json()["ports_probed"])

    def test_ports_probed_order_7497_first(self):
        """7497 (TWS paper) deve essere il primo."""
        mock_mgr = _make_mock_manager(connected=False)
        with patch("execution.ibkr_connection.get_manager", return_value=mock_mgr):
            r = CLIENT.get(ENDPOINT)
        self.assertEqual(r.json()["ports_probed"][0], 7497)


if __name__ == "__main__":
    unittest.main(verbosity=2)
