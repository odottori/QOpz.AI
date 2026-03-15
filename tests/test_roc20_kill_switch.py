"""
tests/test_roc20_kill_switch.py — ROC20

Test suite per POST /opz/execution/kill_switch:
  - activate: crea ops/kill_switch.trigger
  - deactivate: rimuove trigger file (was_active True/False)
  - action invalida → 400
  - kill switch attivo blocca execution_confirm (HTTP 503)
  - idempotenza: doppia activate non rompe
  - sistema_status riflette stato aggiornato
"""
from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from fastapi.testclient import TestClient
from api.opz_api import app

CLIENT = TestClient(app, raise_server_exceptions=False)
ENDPOINT = "/opz/execution/kill_switch"


def _ks_path_from_response(body: dict) -> Path:
    """Deriva il path trigger da ROOT come fa l'API."""
    from api.opz_api import ROOT
    return ROOT / "ops" / "kill_switch.trigger"


class TestKillSwitchActivate(unittest.TestCase):

    def setUp(self):
        # Assicura partenza con KS disattivato
        ks = _ks_path_from_response({})
        if ks.exists():
            ks.unlink()

    def tearDown(self):
        ks = _ks_path_from_response({})
        if ks.exists():
            ks.unlink()

    def test_activate_returns_200(self):
        r = CLIENT.post(ENDPOINT, json={"action": "activate"})
        self.assertEqual(r.status_code, 200)

    def test_activate_ok_true(self):
        body = CLIENT.post(ENDPOINT, json={"action": "activate"}).json()
        self.assertTrue(body["ok"])

    def test_activate_kill_switch_active_true(self):
        body = CLIENT.post(ENDPOINT, json={"action": "activate"}).json()
        self.assertTrue(body["kill_switch_active"])

    def test_activate_creates_trigger_file(self):
        CLIENT.post(ENDPOINT, json={"action": "activate"})
        self.assertTrue(_ks_path_from_response({}).exists())

    def test_activate_trigger_file_contains_json(self):
        CLIENT.post(ENDPOINT, json={"action": "activate"})
        content = _ks_path_from_response({}).read_text(encoding="utf-8")
        data = json.loads(content)
        self.assertIn("activated_at", data)
        self.assertEqual(data["source"], "operator_ui")

    def test_activate_twice_idempotent(self):
        CLIENT.post(ENDPOINT, json={"action": "activate"})
        r2 = CLIENT.post(ENDPOINT, json={"action": "activate"})
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json()["ok"])

    def test_response_has_ts_utc(self):
        body = CLIENT.post(ENDPOINT, json={"action": "activate"}).json()
        self.assertIn("ts_utc", body)
        from datetime import datetime
        datetime.fromisoformat(body["ts_utc"].replace("Z", "+00:00"))


class TestKillSwitchDeactivate(unittest.TestCase):

    def setUp(self):
        # Parti con KS attivo
        ks = _ks_path_from_response({})
        ks.parent.mkdir(parents=True, exist_ok=True)
        ks.write_text('{"activated_at":"2026-01-01","source":"test"}', encoding="utf-8")

    def tearDown(self):
        ks = _ks_path_from_response({})
        if ks.exists():
            ks.unlink()

    def test_deactivate_returns_200(self):
        r = CLIENT.post(ENDPOINT, json={"action": "deactivate"})
        self.assertEqual(r.status_code, 200)

    def test_deactivate_ok_true(self):
        body = CLIENT.post(ENDPOINT, json={"action": "deactivate"}).json()
        self.assertTrue(body["ok"])

    def test_deactivate_kill_switch_active_false(self):
        body = CLIENT.post(ENDPOINT, json={"action": "deactivate"}).json()
        self.assertFalse(body["kill_switch_active"])

    def test_deactivate_removes_trigger_file(self):
        CLIENT.post(ENDPOINT, json={"action": "deactivate"})
        self.assertFalse(_ks_path_from_response({}).exists())

    def test_deactivate_was_active_true(self):
        body = CLIENT.post(ENDPOINT, json={"action": "deactivate"}).json()
        self.assertTrue(body["was_active"])

    def test_deactivate_when_already_inactive(self):
        # Prima deactivate (rimuove)
        CLIENT.post(ENDPOINT, json={"action": "deactivate"})
        # Seconda deactivate — idempotent
        body = CLIENT.post(ENDPOINT, json={"action": "deactivate"}).json()
        self.assertTrue(body["ok"])
        self.assertFalse(body["kill_switch_active"])
        self.assertFalse(body["was_active"])


class TestKillSwitchInvalidInput(unittest.TestCase):

    def test_invalid_action_returns_400(self):
        r = CLIENT.post(ENDPOINT, json={"action": "launch_missiles"})
        self.assertEqual(r.status_code, 400)

    def test_missing_action_returns_422(self):
        r = CLIENT.post(ENDPOINT, json={})
        self.assertEqual(r.status_code, 422)

    def test_empty_action_returns_400(self):
        r = CLIENT.post(ENDPOINT, json={"action": ""})
        self.assertEqual(r.status_code, 400)


class TestKillSwitchBlocksConfirm(unittest.TestCase):
    """Con KS attivo, execution_confirm deve ritornare 503."""

    def setUp(self):
        ks = _ks_path_from_response({})
        ks.parent.mkdir(parents=True, exist_ok=True)
        ks.write_text('{"activated_at":"2026-01-01","source":"test"}', encoding="utf-8")

    def tearDown(self):
        ks = _ks_path_from_response({})
        if ks.exists():
            ks.unlink()

    def test_confirm_blocked_503_when_ks_active(self):
        payload = {
            "confirm_token": "fake-token",
            "operator": "test",
            "decision": "APPROVE",
            "payload": {},
        }
        r = CLIENT.post("/opz/execution/confirm", json=payload)
        self.assertEqual(r.status_code, 503)

    def test_confirm_unblocked_after_deactivate(self):
        # Disattiva KS
        CLIENT.post(ENDPOINT, json={"action": "deactivate"})
        # Confirm ora non blocca per KS (può fallire per altri motivi ma non 503 KS)
        payload = {
            "confirm_token": "fake-token-xyz",
            "operator": "test",
            "decision": "APPROVE",
            "payload": {},
        }
        r = CLIENT.post("/opz/execution/confirm", json=payload)
        # Non deve essere 503 (kill switch) — può essere 409 (token non trovato)
        self.assertNotEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
