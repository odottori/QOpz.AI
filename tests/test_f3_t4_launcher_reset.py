import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class LauncherResetTests(unittest.TestCase):
    def test_root_launchers_share_controller(self):
        for name, action in [('QOPZ_START.bat', 'start'), ('QOPZ_STOP.bat', 'stop')]:
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertIn('scripts\\opz_local.ps1', text)
            self.assertIn(f'-Action {action}', text)
            self.assertIn('exit /b %errorlevel%', text)

    def test_stop_requires_identity_not_just_pid(self):
        text = (ROOT / 'scripts/opz_local.ps1').read_text(encoding='utf-8')
        self.assertIn('StartTime.ToUniversalTime().Ticks', text)
        self.assertIn('$proc.Path -ne', text)
        self.assertIn('$proc = Get-OwnedProcess $name', text)

    def test_concurrent_start_is_serialized(self):
        text = (ROOT / 'scripts/opz_local.ps1').read_text(encoding='utf-8')
        self.assertIn("'ReadWrite', 'None'", text)
        self.assertIn('$lock.Dispose()', text)
