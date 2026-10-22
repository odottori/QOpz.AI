import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class TestSplitLauncher(unittest.TestCase):
    def test_start_does_not_require_windows_terminal(self):
        text = (ROOT / 'QOPZ_START.bat').read_text(encoding='utf-8')
        self.assertNotIn('wt.exe', text)
        self.assertIn('powershell.exe -NoProfile', text)

    def test_ui_served_without_npm_process_tree(self):
        text = (ROOT / 'scripts/opz_local.ps1').read_text(encoding='utf-8')
        self.assertIn('vite\\bin\\vite.js', text)
        self.assertIn('--strictPort', text)
        self.assertIn('-WindowStyle Hidden', text)

    def test_http_and_owner_checks_both_required(self):
        text = (ROOT / 'scripts/opz_local.ps1').read_text(encoding='utf-8')
        self.assertIn('if (-not (Test-ListenerOwned $name $port))', text)
        self.assertIn(".status -eq 'ok'", text)
        self.assertIn("$expected -replace '\\s'", text)
