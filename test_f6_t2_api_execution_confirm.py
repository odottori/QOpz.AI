import json
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from api.opz_api import app
except Exception:
    TestClient = None
    app = None

from execution.storage import init_execution_schema


@unittest.skipIf(TestClient is None or app is None, "fastapi not installed in this environment")
class TestF6T2ApiExecutionConfirm(unittest.TestCase):
    def setUp(self):
        for d in ("db", "logs", "data", "reports"):
            Path(d).mkdir(parents=True, exist_ok=True)
        dbp = Path("db/execution.duckdb")
        if dbp.exists():
            dbp.unlink(missing_ok=True)
        for log_name in ("operator_previews.jsonl", "operator_confirms.jsonl"):
            lp = Path("logs") / log_name
            if lp.exists():
                lp.unlink(missing_ok=True)
        init_execution_schema()
        self.client = TestClient(app)

    def _create_preview(self):
        payload = {
            "symbol": "IWM",
            "strategy": "BULL_PUT",
            "payload": {"legs": [185, 180], "meta": {"score": 0.72}},
        }
        r = self.client.post(
            "/opz/execution/preview",
            json={"symbol": payload["symbol"], "strategy": payload["strategy"], "payload": payload["payload"]},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return payload, r.json()["confirm_token"]

    def test_confirm_accepts_matching_preview_once(self):
        payload, token = self._create_preview()
        r = self.client.post(
            "/opz/execution/confirm",
            json={"confirm_token": token, "operator": "tester", "decision": "APPROVE", "payload": payload},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body["event"]["confirm_token"], token)

        confirms = Path("logs/operator_confirms.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(confirms), 1)
        event = json.loads(confirms[0])
        self.assertEqual(event["operator"], "tester")

    def test_confirm_rejects_unknown_token(self):
        payload = {"symbol": "IWM", "strategy": "BULL_PUT", "payload": {"legs": [185, 180]}}
        r = self.client.post(
            "/opz/execution/confirm",
            json={"confirm_token": "missing-token", "operator": "tester", "decision": "APPROVE", "payload": payload},
        )
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("preview not found", r.text)

    def test_confirm_rejects_payload_mismatch(self):
        payload, token = self._create_preview()
        bad_payload = {**payload, "payload": {"legs": [186, 180], "meta": {"score": 0.72}}}
        r = self.client.post(
            "/opz/execution/confirm",
            json={"confirm_token": token, "operator": "tester", "decision": "APPROVE", "payload": bad_payload},
        )
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("does not match preview", r.text)

    def test_confirm_rejects_token_reuse(self):
        payload, token = self._create_preview()
        first = self.client.post(
            "/opz/execution/confirm",
            json={"confirm_token": token, "operator": "tester", "decision": "APPROVE", "payload": payload},
        )
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post(
            "/opz/execution/confirm",
            json={"confirm_token": token, "operator": "tester", "decision": "REJECT", "payload": payload},
        )
        self.assertEqual(second.status_code, 409, second.text)
        self.assertIn("already used", second.text)


if __name__ == "__main__":
    unittest.main()
