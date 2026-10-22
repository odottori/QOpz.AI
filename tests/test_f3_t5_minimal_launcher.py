import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class TestMinimalLauncher(unittest.TestCase):
    def test_start_does_not_stop_first(self):
        text = (ROOT / 'QOPZ_START.bat').read_text(encoding='utf-8')
        self.assertIn('-Action start', text)
        self.assertNotIn('STOP.bat', text)
        self.assertNotIn('taskkill', text)

    def test_all_stop_aliases_are_owned(self):
        for rel in ['QOPZ_STOP.bat', 'stop.bat', 'scripts/opz_kill_sessions.bat']:
            text = (ROOT / rel).read_text(encoding='utf-8')
            self.assertIn('opz_local.ps1', text)
            self.assertIn('-Action stop', text)
            self.assertNotIn('taskkill', text)

    def test_build_failure_cannot_fall_back_to_stale_dist(self):
        text = (ROOT / 'scripts/opz_local.ps1').read_text(encoding='utf-8')
        self.assertIn('run build -- --outDir', text)
        self.assertIn('if ($buildRc -ne 0) { throw', text)
        self.assertNotIn('OPZ_UI_BUILD_MODE', text)
