from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.opz_api import app
from execution.ibkr_readiness import run_ibkr_readiness


class ReadinessModuleTests(unittest.TestCase):
    def test_readiness_without_option_chain_uses_probe_payload(self):
        fake = {
            "connectivity": {"ok": True, "port": 7497},
            "account_summary": {"ok": True, "summary_keys": ["BuyingPower", "NetLiquidation"]},
            "positions": {"ok": True, "count": 2},
            "option_chain": None,
        }
        fake_scan = {"host": "127.0.0.1", "tested_ports": [7497, 7496, 4002, 4001], "open_count": 1, "open_ports": [{"port": 7497, "label": "tws_paper", "transport": "tws", "trading_mode": "paper"}]}
        with patch("execution.ibkr_readiness._run_readonly_readiness_probe", return_value=fake) as mocked, \
             patch("execution.ibkr_readiness._scan_common_ibkr_ports", return_value=fake_scan):
            body = run_ibkr_readiness(profile="paper", include_option_chain=False)
        self.assertTrue(body["ok"])
        self.assertEqual(body["configured"]["port"], 7497)
        self.assertIsNone(body["probes"]["option_chain"])
        self.assertEqual(body["probes"]["port_scan"]["open_count"], 1)
        mocked.assert_called_once()

    def test_readiness_connectivity_failure_emits_actionable_hints(self):
        from execution.ibkr_tws import IbkrConnectivityError
        fake_scan = {
            "host": "127.0.0.1",
            "tested_ports": [7497, 7496, 4002, 4001],
            "open_count": 1,
            "open_ports": [{"port": 4002, "label": "gateway_paper", "transport": "gateway", "trading_mode": "paper"}],
        }
        with patch("execution.ibkr_readiness._run_readonly_readiness_probe", side_effect=IbkrConnectivityError("boom")), \
             patch("execution.ibkr_readiness._scan_common_ibkr_ports", return_value=fake_scan):
            body = run_ibkr_readiness(profile="paper")
        self.assertFalse(body["ok"])
        self.assertEqual(body["probes"]["connectivity"]["error_type"], "connectivity")
        self.assertTrue(any("4002" in h for h in body["hints"]))
        self.assertTrue(any("gateway" in w for w in body["warnings"]))

    def test_readiness_no_listener_explains_qopz_app_is_not_broker(self):
        from execution.ibkr_tws import IbkrConnectivityError
        fake_scan = {"host": "127.0.0.1", "tested_ports": [7497, 7496, 4002, 4001], "open_count": 0, "open_ports": []}
        with patch("execution.ibkr_readiness._run_readonly_readiness_probe", side_effect=IbkrConnectivityError("boom")), \
             patch("execution.ibkr_readiness._scan_common_ibkr_ports", return_value=fake_scan):
            body = run_ibkr_readiness(profile="paper")
        self.assertFalse(body["ok"])
        self.assertTrue(any("QOpz application start does not start the broker runtime" in h for h in body["hints"]))


class ReadinessApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_readiness_endpoint_returns_probe_payload(self):
        fake = {
            "ok": True,
            "profile": "paper",
            "configured": {"host": "127.0.0.1", "port": 7497, "client_id": 7, "port_label": "tws_paper", "port_trading_mode": "paper"},
            "expected": {"target_mode": "paper", "tws_port": 7497, "gateway_port": 4002, "recommended_port": 7497, "recommended_port_label": "tws_paper"},
            "warnings": [],
            "hints": [],
            "probes": {
                "port_scan": {"host": "127.0.0.1", "tested_ports": [7497, 7496, 4002, 4001], "open_count": 1, "open_ports": [{"port": 7497, "label": "tws_paper", "transport": "tws", "trading_mode": "paper"}]},
                "connectivity": {"ok": True},
                "account_summary": {"ok": True, "summary_keys": ["NetLiquidation"]},
                "positions": {"ok": True, "count": 0},
                "option_chain": {"ok": True, "symbol": "SPY", "expiries_count": 12, "strikes_count": 40},
            },
            "message": "broker readiness OK",
        }
        with patch("api.opz_api.run_ibkr_readiness", return_value=fake):
            r = self.client.get("/opz/ibkr/readiness?profile=paper&symbol=SPY")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["probes"]["option_chain"]["symbol"], "SPY")

    def test_preflight_alias_returns_same_shape(self):
        fake = {
            "ok": False,
            "profile": "paper",
            "configured": {"host": "127.0.0.1", "port": 7497, "client_id": 7, "port_label": "tws_paper", "port_trading_mode": "paper"},
            "expected": {"target_mode": "paper", "tws_port": 7497, "gateway_port": 4002, "recommended_port": 7497, "recommended_port_label": "tws_paper"},
            "warnings": ["x"],
            "hints": ["y"],
            "probes": {
                "port_scan": {"host": "127.0.0.1", "tested_ports": [7497, 7496, 4002, 4001], "open_count": 0, "open_ports": []},
                "connectivity": {"ok": False, "error_type": "connectivity"},
                "account_summary": {"ok": False},
                "positions": {"ok": False},
                "option_chain": {"ok": False},
            },
            "message": "broker readiness failed: connectivity error",
        }
        with patch("api.opz_api.run_ibkr_readiness", return_value=fake):
            r = self.client.get("/opz/ibkr/preflight?profile=paper&symbol=SPY")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["ok"])
        self.assertIn("connectivity", body["probes"])


if __name__ == "__main__":
    unittest.main()
