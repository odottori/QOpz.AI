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
class TestF6T2ApiOpportunity(unittest.TestCase):
    def setUp(self):
        for d in ("db", "logs", "data", "reports"):
            Path(d).mkdir(parents=True, exist_ok=True)

        dbp = Path("db/execution.duckdb")
        if dbp.exists():
            dbp.unlink(missing_ok=True)
        init_execution_schema()
        self.client = TestClient(app)

    def test_opportunity_decision_persists_and_is_exposed_in_last_actions(self):
        payload = {
            "profile": "paper",
            "batch_id": "batch-001",
            "symbol": "IWM",
            "strategy": "BULL_PUT",
            "score": 0.73,
            "regime": "NORMAL",
            "scanner_name": "TOP_PERC_GAIN",
            "source": "ibkr_settings",
            "decision": "APPROVE",
            "confidence": 4,
            "note": "align with operator thesis",
        }
        r = self.client.post("/opz/opportunity/decision", json=payload)
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()
        self.assertTrue(out.get("ok"))
        saved = out.get("decision", {})
        self.assertEqual(saved.get("symbol"), "IWM")
        self.assertEqual(saved.get("decision"), "APPROVE")
        self.assertEqual(saved.get("confidence"), 4)

        la = self.client.get("/opz/last_actions?limit=5")
        self.assertEqual(la.status_code, 200, la.text)
        decisions = la.json().get("opportunity_decisions", [])
        self.assertEqual(len(decisions), 1)
        d0 = decisions[0]
        self.assertEqual(d0.get("batch_id"), "batch-001")
        self.assertEqual(d0.get("symbol"), "IWM")
        self.assertEqual(d0.get("strategy"), "BULL_PUT")
        self.assertEqual(d0.get("decision"), "APPROVE")
        self.assertEqual(d0.get("confidence"), 4)

    def test_opportunity_decision_requires_note_for_reject(self):
        payload = {
            "profile": "paper",
            "symbol": "IWM",
            "decision": "REJECT",
            "confidence": 3,
            "note": "",
        }
        r = self.client.post("/opz/opportunity/decision", json=payload)
        self.assertEqual(r.status_code, 400, r.text)
        detail = r.json().get("detail", {})
        self.assertEqual(detail.get("stage"), "opportunity_decision")

    def test_opportunity_decision_allows_approve_without_note(self):
        payload = {
            "profile": "paper",
            "symbol": "IWM",
            "decision": "APPROVE",
            "confidence": 3,
            "note": "",
        }
        r = self.client.post("/opz/opportunity/decision", json=payload)
        self.assertEqual(r.status_code, 200, r.text)

    def test_opportunity_decision_rejects_invalid_confidence(self):
        payload = {
            "profile": "paper",
            "symbol": "IWM",
            "decision": "APPROVE",
            "confidence": 7,
        }
        r = self.client.post("/opz/opportunity/decision", json=payload)
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
