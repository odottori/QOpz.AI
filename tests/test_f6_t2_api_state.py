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
class TestF6T2ApiState(unittest.TestCase):
    def setUp(self):
        for d in ("db", "logs", "data", "reports"):
            Path(d).mkdir(parents=True, exist_ok=True)
        dbp = Path("db/execution.duckdb")
        if dbp.exists():
            dbp.unlink(missing_ok=True)
        init_execution_schema()
        self.client = TestClient(app)

    def test_state_endpoint_returns_dict(self):
        r = self.client.get("/opz/state")
        self.assertEqual(r.status_code, 200, r.text)
        payload = r.json()
        # May be empty dict in test env (no state file) — that is valid
        self.assertIsInstance(payload, dict)

    def test_release_status_returns_md_content(self):
        r = self.client.get("/opz/release_status")
        self.assertEqual(r.status_code, 200, r.text)
        payload = r.json()
        self.assertEqual(payload.get("format"), "md")
        content = payload.get("content", "")
        self.assertIsInstance(content, str)
        self.assertGreater(len(content.strip()), 0, "release_status content must not be empty")


if __name__ == "__main__":
    unittest.main()
