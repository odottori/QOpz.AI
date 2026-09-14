from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestMinimalLauncher(unittest.TestCase):
    def test_start_uses_helper_not_inline_wt_quoting(self) -> None:
        text = (ROOT / "QOPZ_START.bat").read_text(encoding="utf-8")
        self.assertIn('scripts\\opz_launcher_reset.py start', text)
        self.assertNotIn('wt.exe -w %OPZ_WINDOW%', text)
        self.assertNotIn('cmd /c "cd /d', text)

    def test_stop_uses_helper_not_portkill_direct(self) -> None:
        text = (ROOT / "QOPZ_STOP.bat").read_text(encoding="utf-8")
        self.assertIn('scripts\\opz_launcher_reset.py stop', text)
        self.assertNotIn('scripts\\opz_kill_ports.py --ports 8765 8173', text)

    def test_helper_scripts_compile(self) -> None:
        for rel in ["scripts/opz_wait_http.py", "scripts/opz_kill_ports.py", "scripts/opz_launcher_reset.py"]:
            src = (ROOT / rel).read_text(encoding="utf-8")
            compile(src, rel, "exec")


if __name__ == "__main__":
    unittest.main()
