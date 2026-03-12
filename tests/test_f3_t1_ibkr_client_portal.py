from __future__ import annotations

import io
import urllib.error
import urllib.request
import unittest
from unittest.mock import patch

from execution.ibkr_client_portal import (
    IBKRClientPortalClient,
    extract_auth_status_from_tickle,
    pick_first_account_id,
)


class _FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestIBKRClientPortalHelpers(unittest.TestCase):
    def test_pick_first_account_id(self) -> None:
        payload = [{"accountId": "U1234567", "displayName": "Paper"}]
        self.assertEqual(pick_first_account_id(payload), "U1234567")

        payload2 = {"accounts": [{"id": "U7654321"}]}
        self.assertEqual(pick_first_account_id(payload2), "U7654321")

        self.assertIsNone(pick_first_account_id([]))
        self.assertIsNone(pick_first_account_id({}))

    def test_extract_auth_status_from_tickle(self) -> None:
        tickle = {
            "iserver": {
                "authStatus": {"authenticated": True, "connected": True}
            }
        }
        self.assertEqual(extract_auth_status_from_tickle(tickle), (True, True))
        self.assertEqual(extract_auth_status_from_tickle({}), (None, None))


class TestIBKRClientPortalClient(unittest.TestCase):
    def test_sso_validate_parses_json(self) -> None:
        client = IBKRClientPortalClient(base_url="https://localhost:5000/v1/api", insecure=True, timeout_s=1)

        def _fake_urlopen(req: urllib.request.Request, timeout: float, context=None):
            self.assertEqual(req.get_method(), "GET")
            self.assertEqual(req.full_url, "https://localhost:5000/v1/api/sso/validate")
            return _FakeResponse(200, b'{"RESULT": true, "USER_NAME": "u"}')

        with patch("urllib.request.urlopen", new=_fake_urlopen):
            res = client.sso_validate()
        self.assertTrue(res.ok)
        self.assertEqual(res.status, 200)
        self.assertIsInstance(res.data, dict)
        self.assertEqual(res.data.get("RESULT"), True)

    def test_urlerror_is_captured(self) -> None:
        client = IBKRClientPortalClient(base_url="https://localhost:5000/v1/api", insecure=True, timeout_s=1)

        def _fake_urlopen(req: urllib.request.Request, timeout: float, context=None):
            raise urllib.error.URLError("boom")

        with patch("urllib.request.urlopen", new=_fake_urlopen):
            res = client.portfolio_accounts()
        self.assertFalse(res.ok)
        self.assertEqual(res.status, 0)
        self.assertIn("URLError", res.error or "")


if __name__ == "__main__":
    unittest.main()
