from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestWindowsTerminalLauncher(unittest.TestCase):
    def test_root_batches_point_to_new_script(self):
        start = (ROOT / 'QOPZ_START.bat').read_text(encoding='utf-8')
        stop = (ROOT / 'QOPZ_STOP.bat').read_text(encoding='utf-8')
        self.assertIn('opz_wt_launcher.ps1', start)
        self.assertIn('opz_wt_launcher.ps1', stop)
        self.assertNotIn('opz_launcher_reset.py', start)
        self.assertNotIn('opz_launcher_reset.py', stop)

    def test_ps1_is_bom_free_and_uses_new_tab_and_split(self):
        ps1 = ROOT / 'scripts' / 'opz_wt_launcher.ps1'
        data = ps1.read_bytes()
        self.assertFalse(data.startswith(b'\xef\xbb\xbf'))
        text = data.decode('utf-8')
        self.assertIn("'new-tab'", text)
        self.assertIn("'split-pane'", text)
        self.assertIn("'-w', $WindowName", text)
        self.assertIn('Start-Process -FilePath $wtExe', text)

    def test_no_old_helper_cmds_in_active_path(self):
        start = (ROOT / 'QOPZ_START.bat').read_text(encoding='utf-8')
        self.assertNotIn('opz_run_api_tab.cmd', start)
        self.assertNotIn('opz_run_ui_tab.cmd', start)


if __name__ == '__main__':
    unittest.main()
