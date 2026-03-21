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
class TestBootstrapGuard(unittest.TestCase):
    def setUp(self):
        for d in ("db", "logs", "data", "reports"):
            Path(d).mkdir(parents=True, exist_ok=True)
        dbp = Path("db/execution.duckdb")
        if dbp.exists():
            dbp.unlink(missing_ok=True)
        init_execution_schema()
        self.client = TestClient(app)

    def test_startup_does_not_seed_demo_data(self):
        r = self.client.get("/opz/paper/summary?profile=paper&window_days=60&asof_date=2026-03-09")
        self.assertEqual(r.status_code, 200, r.text)
        payload = r.json()
        self.assertEqual(payload.get("equity_points"), 0)
        self.assertEqual(payload.get("trades"), 0)

    def test_bootstrap_requires_explicit_opt_in(self):
        r = self.client.post("/opz/bootstrap?profile=paper")
        self.assertEqual(r.status_code, 410, r.text)
        detail = r.json().get("detail", {})
        self.assertEqual(detail.get("stage"), "bootstrap")
        self.assertIn("removed", detail.get("reason", ""))
        self.assertEqual(detail.get("profile"), "paper")

    def test_bootstrap_is_disabled_even_with_allow_demo(self):
        r = self.client.post("/opz/bootstrap?profile=paper&allow_demo=true")
        self.assertEqual(r.status_code, 410, r.text)
        detail = r.json().get("detail", {})
        self.assertEqual(detail.get("stage"), "bootstrap")
        self.assertIn("removed", detail.get("reason", ""))
        self.assertEqual(detail.get("profile"), "paper")


if __name__ == "__main__":
    unittest.main()
