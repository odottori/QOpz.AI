import os
import unittest

try:
    from fastapi.testclient import TestClient
    from api.opz_api import app
except Exception:
    TestClient = None
    app = None


@unittest.skipIf(TestClient is None or app is None, "fastapi not installed in this environment")
class TestF6T2ApiSecurity(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_tutorial_path_outside_docs_rejected(self):
        r = self.client.get("/opz/narrator/tutorial", params={"path": "../api/opz_api.py"})
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("outside allowed roots", r.text)

    def test_universe_settings_path_outside_docs_rejected(self):
        r = self.client.get("/opz/universe/ibkr_context", params={"settings_path": "../api/opz_api.py"})
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("outside allowed roots", r.text)

    def test_universe_ocr_path_outside_allowed_roots_rejected(self):
        r = self.client.get("/opz/universe/provenance", params={"ocr_path": "../api/opz_api.py"})
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("outside allowed roots", r.text)

    def test_tts_invalid_template_rejected(self):
        old = os.environ.get("QWEN_TTS_PLAY_CMD")
        os.environ["QWEN_TTS_PLAY_CMD"] = '"broken {text}'
        try:
            r = self.client.post("/opz/narrator/tts", json={"action": "play", "text": "ciao"})
            self.assertEqual(r.status_code, 500, r.text)
            self.assertIn("invalid QWEN_TTS_PLAY_CMD template", r.text)
        finally:
            if old is None:
                os.environ.pop("QWEN_TTS_PLAY_CMD", None)
            else:
                os.environ["QWEN_TTS_PLAY_CMD"] = old


if __name__ == "__main__":
    unittest.main()
