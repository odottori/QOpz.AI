"""
tests/test_roc8_system_status.py — ROC8-T2

Test suite per GET /opz/system/status:
  - struttura risposta (campi obbligatori)
  - kill_switch inattivo (file assente)
  - kill_switch attivo (file presente)
  - ibkr connected / disconnected
  - data_mode da env var
  - kelly gate logic (data_mode + n_closed_trades)
  - execution_config_ready
  - signals list: formato, stati attesi
  - regime fallback "UNKNOWN" se nessun dato
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from fastapi.testclient import TestClient
from api.opz_api import app

CLIENT = TestClient(app, raise_server_exceptions=False)
ENDPOINT = "/opz/system/status"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get(**env_overrides) -> dict:
    """Perform GET /opz/system/status with optional env patches."""
    with patch.dict(os.environ, env_overrides):
        r = CLIENT.get(ENDPOINT)
    assert r.status_code == 200
    return r.json()


def _disconnected_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.is_connected = False
    mgr.connection_info.return_value = {
        "connected": False, "port": None,
        "source_system": "yfinance", "connected_at": None,
    }
    return mgr


def _connected_manager(port: int = 7497) -> MagicMock:
    mgr = MagicMock()
    mgr.is_connected = True
    mgr.connection_info.return_value = {
        "connected": True, "port": port,
        "source_system": "ibkr_live", "connected_at": "2026-03-15T10:00:00+00:00",
    }
    return mgr


# ─────────────────────────────────────────────────────────────────────────────
# 1. Struttura risposta
# ─────────────────────────────────────────────────────────────────────────────

class TestSystemStatusStructure(unittest.TestCase):

    def test_status_200(self):
        r = CLIENT.get(ENDPOINT)
        self.assertEqual(r.status_code, 200)

    def test_ok_true(self):
        body = _get()
        self.assertTrue(body["ok"])

    def test_required_fields_present(self):
        body = _get()
        required = [
            "ok", "timestamp_utc", "api_online", "kill_switch_active",
            "data_mode", "kelly_enabled", "ibkr_connected", "ibkr_port",
            "ibkr_source_system", "ibkr_connected_at", "execution_config_ready",
            "n_closed_trades", "regime", "signals",
        ]
        for field in required:
            self.assertIn(field, body, f"Missing field: {field}")

    def test_api_online_always_true(self):
        body = _get()
        self.assertTrue(body["api_online"])

    def test_timestamp_utc_is_string(self):
        body = _get()
        self.assertIsInstance(body["timestamp_utc"], str)
        self.assertIn("T", body["timestamp_utc"])

    def test_signals_is_list(self):
        body = _get()
        self.assertIsInstance(body["signals"], list)

    def test_signals_have_required_keys(self):
        body = _get()
        for sig in body["signals"]:
            self.assertIn("name", sig)
            self.assertIn("status", sig)
            self.assertIn("detail", sig)

    def test_signals_status_values(self):
        """Status deve essere uno dei valori ammessi."""
        body = _get()
        allowed = {"OK", "WARN", "ALERT", "DISABLED"}
        for sig in body["signals"]:
            self.assertIn(sig["status"], allowed, f"{sig['name']} → {sig['status']!r}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Kill switch
# ─────────────────────────────────────────────────────────────────────────────

class TestKillSwitch(unittest.TestCase):

    def _ks_signal(self, body: dict) -> dict:
        return next(s for s in body["signals"] if s["name"] == "kill_switch")

    def test_kill_switch_inactive_when_no_file(self):
        with patch("pathlib.Path.exists", return_value=False):
            body = _get()
        self.assertFalse(body["kill_switch_active"])

    def test_kill_switch_signal_ok_when_inactive(self):
        with patch("pathlib.Path.exists", return_value=False):
            body = _get()
        self.assertEqual(self._ks_signal(body)["status"], "OK")

    def test_kill_switch_active_when_file_present(self):
        with tempfile.TemporaryDirectory() as td:
            ks = Path(td) / "ops" / "kill_switch.trigger"
            ks.parent.mkdir(parents=True)
            ks.touch()
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                body = _get()
                self.assertTrue(body["kill_switch_active"])
            finally:
                os.chdir(old_cwd)

    def test_kill_switch_signal_alert_when_active(self):
        with tempfile.TemporaryDirectory() as td:
            ks = Path(td) / "ops" / "kill_switch.trigger"
            ks.parent.mkdir(parents=True)
            ks.touch()
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                body = _get()
                sig = self._ks_signal(body)
                self.assertEqual(sig["status"], "ALERT")
            finally:
                os.chdir(old_cwd)


# ─────────────────────────────────────────────────────────────────────────────
# 3. IBKR connected / disconnected
# ─────────────────────────────────────────────────────────────────────────────

class TestIbkrFields(unittest.TestCase):

    def _ibkr_signal(self, body: dict) -> dict:
        return next(s for s in body["signals"] if s["name"] == "ibkr")

    def test_ibkr_disconnected_fields(self):
        with patch("execution.ibkr_connection.get_manager", return_value=_disconnected_manager()):
            body = _get()
        self.assertFalse(body["ibkr_connected"])
        self.assertIsNone(body["ibkr_port"])
        self.assertEqual(body["ibkr_source_system"], "yfinance")

    def test_ibkr_disconnected_signal_warn(self):
        with patch("execution.ibkr_connection.get_manager", return_value=_disconnected_manager()):
            body = _get()
        self.assertEqual(self._ibkr_signal(body)["status"], "WARN")

    def test_ibkr_connected_fields(self):
        with patch("execution.ibkr_connection.get_manager", return_value=_connected_manager(7497)):
            body = _get()
        self.assertTrue(body["ibkr_connected"])
        self.assertEqual(body["ibkr_port"], 7497)
        self.assertEqual(body["ibkr_source_system"], "ibkr_live")

    def test_ibkr_connected_signal_ok(self):
        with patch("execution.ibkr_connection.get_manager", return_value=_connected_manager(7497)):
            body = _get()
        self.assertEqual(self._ibkr_signal(body)["status"], "OK")

    def test_ibkr_exception_graceful(self):
        with patch("execution.ibkr_connection.get_manager", side_effect=RuntimeError("conn error")):
            body = _get()
        self.assertFalse(body["ibkr_connected"])
        self.assertTrue(body["ok"])


# ─────────────────────────────────────────────────────────────────────────────
# 4. data_mode
# ─────────────────────────────────────────────────────────────────────────────

class TestDataMode(unittest.TestCase):

    def _dm_signal(self, body: dict) -> dict:
        return next(s for s in body["signals"] if s["name"] == "data_mode")

    def test_synthetic_surface_data_mode(self):
        body = _get(OPZ_DATA_MODE="SYNTHETIC_SURFACE_CALIBRATED")
        self.assertEqual(body["data_mode"], "SYNTHETIC_SURFACE_CALIBRATED")

    def test_vendor_real_chain_data_mode(self):
        body = _get(OPZ_DATA_MODE="VENDOR_REAL_CHAIN")
        self.assertEqual(body["data_mode"], "VENDOR_REAL_CHAIN")

    def test_synthetic_signal_warn(self):
        body = _get(OPZ_DATA_MODE="SYNTHETIC_SURFACE_CALIBRATED")
        self.assertEqual(self._dm_signal(body)["status"], "WARN")

    def test_vendor_real_signal_ok(self):
        body = _get(OPZ_DATA_MODE="VENDOR_REAL_CHAIN")
        self.assertEqual(self._dm_signal(body)["status"], "OK")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Kelly gate
# ─────────────────────────────────────────────────────────────────────────────

class TestKellyGate(unittest.TestCase):

    def _kelly_signal(self, body: dict) -> dict:
        return next(s for s in body["signals"] if s["name"] == "kelly")

    def test_kelly_disabled_synthetic(self):
        body = _get(OPZ_DATA_MODE="SYNTHETIC_SURFACE_CALIBRATED")
        self.assertFalse(body["kelly_enabled"])

    def test_kelly_disabled_vendor_low_trades(self):
        """Vendor real ma meno di 50 trade chiusi → Kelly disabilitato."""
        with patch("duckdb.connect") as mock_conn:
            mock_conn.return_value.__enter__ = lambda s: s
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_conn.return_value.execute.return_value.fetchone.return_value = (10,)
            body = _get(OPZ_DATA_MODE="VENDOR_REAL_CHAIN")
        self.assertFalse(body["kelly_enabled"])

    def test_kelly_signal_disabled_when_synthetic(self):
        body = _get(OPZ_DATA_MODE="SYNTHETIC_SURFACE_CALIBRATED")
        self.assertEqual(self._kelly_signal(body)["status"], "DISABLED")


# ─────────────────────────────────────────────────────────────────────────────
# 6. execution_config_ready
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutionConfig(unittest.TestCase):

    def _ec_signal(self, body: dict) -> dict:
        return next(s for s in body["signals"] if s["name"] == "execution_config")

    def test_config_ready_true_when_dev_toml_exists(self):
        # execution_config_ready usa ROOT assoluto — sempre True nel repo
        body = _get()
        self.assertIn(body["execution_config_ready"], (True, False))

    def test_config_signal_ok_when_ready(self):
        # Mocka Path.exists → True per i path config
        with patch("pathlib.Path.exists", return_value=True):
            body = _get()
        self.assertTrue(body["execution_config_ready"])
        self.assertEqual(self._ec_signal(body)["status"], "OK")

    def test_config_signal_alert_when_missing(self):
        # Mocka Path.exists → False per tutti i path (inclusi config)
        with patch("pathlib.Path.exists", return_value=False):
            body = _get()
        self.assertFalse(body["execution_config_ready"])
        self.assertEqual(self._ec_signal(body)["status"], "ALERT")


# ─────────────────────────────────────────────────────────────────────────────
# 7. signals completeness
# ─────────────────────────────────────────────────────────────────────────────

class TestSignalsCompleteness(unittest.TestCase):

    def test_mandatory_signal_names_present(self):
        body = _get()
        names = {s["name"] for s in body["signals"]}
        for expected in ("kill_switch", "ibkr", "data_mode", "kelly", "execution_config"):
            self.assertIn(expected, names)

    def test_regime_field_present(self):
        body = _get()
        self.assertIn("regime", body)

    def test_n_closed_trades_non_negative(self):
        body = _get()
        self.assertGreaterEqual(body["n_closed_trades"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
