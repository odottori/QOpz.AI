from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.opz_api import app


CLIENT = TestClient(app, raise_server_exceptions=False)


class TestControlStatusApi(unittest.TestCase):
    def test_control_status_merges_sources(self):
        with (
            patch(
                "api.opz_api.opz_system_status",
                return_value={
                    "kill_switch_active": True,
                    "ibkr_connected": False,
                    "ibkr_port": None,
                    "ibkr_source_system": "ibkr_live",
                    "ibkr_connected_at": None,
                    "regime": "UNKNOWN",
                    "data_mode": "VENDOR_REAL_CHAIN",
                    "history_readiness": {"score_pct": 10.0},
                },
            ),
            patch(
                "api.opz_api._control_api_json",
                return_value={
                    "ok": True,
                    "ibwr": {"service_state": "OFF", "reason": "STOPPED"},
                    "services": {"api": {"state": "ON"}},
                },
            ),
        ):
            r = CLIENT.get("/opz/control/status")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["observer"]["state"], "OFF")
        self.assertEqual(body["ibwr"]["service_state"], "OFF")
        self.assertTrue(body["vm"]["control_plane_ok"])

    def test_control_status_handles_control_plane_failure(self):
        with (
            patch(
                "api.opz_api.opz_system_status",
                return_value={
                    "kill_switch_active": False,
                    "ibkr_connected": True,
                    "ibkr_port": 4004,
                    "ibkr_source_system": "ibkr_live",
                    "ibkr_connected_at": "2026-03-20T00:00:00Z",
                    "regime": "NORMAL",
                    "data_mode": "VENDOR_REAL_CHAIN",
                    "history_readiness": {},
                },
            ),
            patch(
                "api.opz_api._control_api_json",
                side_effect=HTTPException(status_code=502, detail="boom"),
            ),
        ):
            r = CLIENT.get("/opz/control/status")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["observer"]["state"], "ON")
        self.assertFalse(body["vm"]["control_plane_ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
