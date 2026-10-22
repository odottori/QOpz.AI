import subprocess
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class TestWindowsTerminalLauncher(unittest.TestCase):
    def test_ps1_is_bom_free(self):
        data = (ROOT / 'scripts/opz_local.ps1').read_bytes()
        self.assertFalse(data.startswith(b'\xef\xbb\xbf'))
        self.assertTrue(data.startswith(b'param('))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows PowerShell syntax')
    def test_powershell_parser_accepts_controller(self):
        command = "$e=$null; [void][Management.Automation.Language.Parser]::ParseFile('scripts/opz_local.ps1',[ref]$null,[ref]$e); if($e){$e; exit 1}"
        p = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_batch_entrypoints_propagate_failure(self):
        for rel in ['QOPZ_START.bat', 'QOPZ_STOP.bat', 'scripts/opz_start_local.bat', 'scripts/opz_start_tabs.bat']:
            text = (ROOT / rel).read_text(encoding='utf-8')
            self.assertIn('exit /b %errorlevel%', text)
            self.assertNotIn('start "', text)
