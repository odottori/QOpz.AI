from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "scripts" / "telegram_command_bot.py"

spec = importlib.util.spec_from_file_location("telegram_command_bot", MOD_PATH)
assert spec and spec.loader
bot = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bot
spec.loader.exec_module(bot)


class TestTelegramCommandBot(unittest.TestCase):
    def test_normalize_help(self):
        self.assertEqual(bot._normalize_command("help"), "HELP")
        self.assertEqual(bot._normalize_command("/help"), "HELP")

    def test_normalize_status(self):
        self.assertEqual(bot._normalize_command("STATUS"), "STATUS")
        self.assertEqual(bot._normalize_command("/status"), "STATUS")

    def test_normalize_observer_aliases(self):
        self.assertEqual(bot._normalize_command("observer_on"), "OBSERVER ON")
        self.assertEqual(bot._normalize_command("observer-off"), "OBSERVER OFF")
        self.assertEqual(bot._normalize_command("observer yes"), "OBSERVER ON")
        self.assertEqual(bot._normalize_command("observer no"), "OBSERVER OFF")

    def test_build_status_text(self):
        status = {
            "kill_switch_active": True,
            "ibkr_connected": False,
            "regime": "CAUTION",
            "data_mode": "VENDOR_REAL_CHAIN",
            "history_readiness": {
                "score_pct": 72.5,
                "days_observed": 7,
                "target_days": 10,
                "events_observed": 28,
                "target_events": 40,
                "eta_days": 3,
            },
        }
        txt = bot._build_status_text(status)
        self.assertIn("OBSERVER: OFF", txt)
        self.assertIn("IBWR/IBG: OFF", txt)
        self.assertIn("REGIME: CAUTION", txt)
        self.assertIn("READINESS: 72.5%", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
