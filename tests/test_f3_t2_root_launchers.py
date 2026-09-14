from __future__ import annotations

import unittest
from pathlib import Path


class RootLauncherHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]

    def test_root_start_stop_and_aliases_exist(self) -> None:
        for rel in ("QOPZ_START.bat", "QOPZ_STOP.bat", "start.bat", "stop.bat"):
            self.assertTrue((self.root / rel).exists(), f"missing launcher: {rel}")

    def test_setup_uses_py_launcher_and_correct_next_step(self) -> None:
        text = (self.root / "QOPZ_SETUP.bat").read_text(encoding="utf-8", errors="replace")
        self.assertIn('set "OPZ_BOOT_PY=py"', text)
        self.assertIn('QOPZ_START.bat', text)
        self.assertNotIn('OPZ_START.bat', text.replace('QOPZ_START.bat', ''))

    def test_root_stop_uses_reset_shutdown(self) -> None:
        text = (self.root / "QOPZ_STOP.bat").read_text(encoding="utf-8", errors="replace")
        self.assertIn('scripts\\opz_launcher_reset.py stop', text)
        self.assertIn('policy=kill-by-port-and-clean-state', text)

    def test_manual_start_wrappers_delegate_without_hardcoded_repo_root(self) -> None:
        for rel, needle in (
            ("scripts/start_api.bat", 'opz_run_api_tab.cmd'),
            ("scripts/start_ui.bat", 'opz_run_ui_tab.cmd'),
        ):
            text = (self.root / rel).read_text(encoding="utf-8", errors="replace")
            self.assertIn(needle, text)
            self.assertNotIn(r'C:\.dev\QOpz.AI', text)


if __name__ == "__main__":
    unittest.main()
