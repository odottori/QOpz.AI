from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.opz_api import app


CLIENT = TestClient(app, raise_server_exceptions=False)


class TestObserverSwitchApi(unittest.TestCase):
    def setUp(self):
        self.root = Path("C:/.dev/QOpz.AI/.tmp/test_observer_switch")
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _post(self, payload: dict):
        return CLIENT.post("/opz/execution/observer", json=payload)

    def test_observer_off_forces_kill_switch_on(self):
        with patch("api.opz_api.ROOT", self.root), \
             patch("api.opz_api._send_telegram_text", return_value=(True, None)), \
             patch("execution.ibkr_connection.get_manager") as gm:
            gm.return_value.connection_info.return_value = {"connected": True}
            r = self._post({"action": "off", "notify_telegram": True})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["observer_state"], "OFF")
        self.assertTrue(body["kill_switch_active"])
        self.assertEqual(body["reason"], "MANUAL_OFF")

    def test_observer_on_blocked_if_ibkr_disconnected(self):
        with patch("api.opz_api.ROOT", self.root), \
             patch("api.opz_api._send_telegram_text", return_value=(True, None)), \
             patch("execution.ibkr_connection.get_manager") as gm:
            gm.return_value.connection_info.return_value = {"connected": False}
            r = self._post({"action": "on", "notify_telegram": True})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["observer_state"], "OFF")
        self.assertEqual(body["reason"], "IBKR_DISCONNECTED")
        self.assertTrue(body["kill_switch_active"])

    def test_observer_on_when_ibkr_connected(self):
        ks = self.root / "ops" / "kill_switch.trigger"
        ks.parent.mkdir(parents=True, exist_ok=True)
        ks.write_text("{}", encoding="utf-8")

        with patch("api.opz_api.ROOT", self.root), \
             patch("api.opz_api._send_telegram_text", return_value=(True, None)), \
             patch("execution.ibkr_connection.get_manager") as gm:
            gm.return_value.connection_info.return_value = {"connected": True, "port": 4004}
            r = self._post({"action": "on", "notify_telegram": True})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["observer_state"], "ON")
        self.assertEqual(body["reason"], "READY")
        self.assertFalse(body["kill_switch_active"])
        self.assertTrue(body["telegram_notified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

