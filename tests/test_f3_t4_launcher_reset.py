from __future__ import annotations

import unittest
from pathlib import Path


class LauncherResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]

    def _read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8", errors="replace")

    def test_root_launchers_use_single_helper_path(self) -> None:
        start = self._read("QOPZ_START.bat")
        stop = self._read("QOPZ_STOP.bat")
        self.assertIn("minimal launcher startup", start)
        self.assertIn('scripts\\opz_launcher_reset.py start', start)
        self.assertNotIn("wt.exe -w", start)
        self.assertIn("minimal launcher shutdown", stop)
        self.assertIn('scripts\\opz_launcher_reset.py stop', stop)

    def test_reset_helper_builds_wt_command_without_cmd_c_wrappers(self) -> None:
        text = self._read("scripts/opz_launcher_reset.py")
        self.assertIn('WINDOW_NAME = "qopz-ai"', text)
        self.assertIn('"wt.exe"', text)
        self.assertIn('"new-tab"', text)
        self.assertIn('"--startingDirectory"', text)
        self.assertIn('"QOPZ API"', text)
        self.assertIn('"QOPZ UI"', text)
        self.assertIn('"api.opz_api:app"', text)
        self.assertIn('"npm.cmd"', text)
        self.assertNotIn('"cmd.exe"', text)
        self.assertNotIn('opz_run_api_tab.cmd', text)
        self.assertNotIn('opz_run_ui_tab.cmd', text)

    def test_tab_runners_remain_non_active_path(self) -> None:
        api = self._read("scripts/opz_run_api_tab.cmd")
        ui = self._read("scripts/opz_run_ui_tab.cmd")
        self.assertIn("uvicorn api.opz_api:app --host 127.0.0.1 --port 8765", api)
        self.assertIn("npm.cmd run dev -- --host 127.0.0.1 --port 8173", ui)


if __name__ == "__main__":
    unittest.main()
