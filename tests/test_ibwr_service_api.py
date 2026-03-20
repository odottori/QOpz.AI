from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.opz_api import app


CLIENT = TestClient(app, raise_server_exceptions=False)


class TestIbwrServiceApi(unittest.TestCase):
    def _post(self, payload: dict):
        return CLIENT.post("/opz/ibwr/service", json=payload)

    def test_status_ok(self):
        with patch(
            "api.opz_api._docker_ibg_service_action",
            return_value={
                "ok": True,
                "requested_action": "status",
                "applied_action": "status",
                "service_state": "OFF",
                "reason": "STOPPED",
                "ts_utc": "2026-03-20T00:00:00Z",
            },
        ):
            r = self._post({"action": "status", "notify_telegram": False})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["service_state"], "OFF")
        self.assertEqual(body["reason"], "STOPPED")
        self.assertFalse(body["telegram_notified"])

    def test_on_with_notify(self):
        with (
            patch(
                "api.opz_api._docker_ibg_service_action",
                return_value={
                    "ok": True,
                    "requested_action": "on",
                    "applied_action": "start",
                    "service_state": "ON",
                    "reason": "STARTED",
                    "ts_utc": "2026-03-20T00:00:00Z",
                },
            ),
            patch("api.opz_api._send_telegram_text", return_value=(True, None)),
        ):
            r = self._post({"action": "on", "notify_telegram": True})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["service_state"], "ON")
        self.assertTrue(body["telegram_notified"])

    def test_invalid_action(self):
        r = self._post({"action": "wrong"})
        self.assertEqual(r.status_code, 400, r.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
