import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestLaunchReadinessScripts(unittest.TestCase):
    def _read_bytes(self, rel: str) -> bytes:
        return (REPO_ROOT / rel).read_bytes()

    def _read_text(self, rel: str) -> str:
        return (REPO_ROOT / rel).read_text(encoding="utf-8")

    def test_start_and_stop_ps1_are_bom_free_and_begin_with_param(self):
        for rel in (
            "scripts/opz_start_tracked_process.ps1",
            "scripts/opz_stop_tracked_process.ps1",
        ):
            data = self._read_bytes(rel)
            self.assertFalse(data.startswith(b"\xef\xbb\xbf"), rel)
            self.assertTrue(data.startswith(b"param("), rel)

    def test_start_ps1_supports_argumentsline_and_comma_fallback(self):
        text = self._read_text("scripts/opz_start_tracked_process.ps1")
        self.assertIn('[string]$ArgumentsLine = ""', text)
        self.assertIn("$effectiveArgumentLine", text)
        self.assertIn("Split(',')", text)
        self.assertIn("$psi.ArgumentList = $effectiveArgumentLine", text)

    def test_api_launcher_uses_argumentsline_not_powershell_array_literals(self):
        text = self._read_text("scripts/opz_start_api_if_needed.bat")
        self.assertIn('-Action start -Role api', text)
        self.assertIn('opz_local.ps1', text)
        self.assertNotIn('-ArgumentList "-m","uvicorn"', text)

    def test_ui_launcher_uses_argumentsline_not_powershell_array_literals(self):
        text = self._read_text("scripts/opz_start_ui_if_needed.bat")
        self.assertIn('-Action start -Role ui', text)
        self.assertIn('opz_local.ps1', text)
        self.assertNotIn('-ArgumentList "run","dev"', text)


if __name__ == "__main__":
    unittest.main()
