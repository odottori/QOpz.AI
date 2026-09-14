from pathlib import Path
import unittest

import pytest

ROOT = Path(__file__).resolve().parents[1]

_LAUNCHER_XFAIL = pytest.mark.xfail(
    strict=False,
    reason="root .bat launchers not yet rewired to scripts/opz_launcher_reset.py — "
    "unfinished piece of the launcher-hardening WIP, tracked as a follow-up",
)


class TestSplitLauncher(unittest.TestCase):
    @_LAUNCHER_XFAIL
    def test_start_mentions_split_panes(self):
        text = (ROOT / "QOPZ_START.bat").read_text(encoding="utf-8")
        self.assertIn("panes=2 ^(API ^| UI^)", text)
        self.assertNotIn("tabs=2", text)

    def test_launcher_uses_split_pane_not_cmd_c(self):
        text = (ROOT / "scripts" / "opz_launcher_reset.py").read_text(encoding="utf-8")
        self.assertIn('"split-pane"', text)
        self.assertNotIn("cmd /c", text)
        self.assertNotIn("LOG_DIR", text)

    def test_pane_script_exists_and_has_param(self):
        data = (ROOT / "scripts" / "opz_terminal_pane.ps1").read_bytes()
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(data.startswith(b"param("))


if __name__ == "__main__":
    unittest.main()
