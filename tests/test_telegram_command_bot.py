from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


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
        self.assertEqual(bot._normalize_command("\\status"), "STATUS")

    def test_normalize_observer_aliases(self):
        self.assertEqual(bot._normalize_command("observer_on"), "OBSERVER ON")
        self.assertEqual(bot._normalize_command("observer-off"), "OBSERVER OFF")
        self.assertEqual(bot._normalize_command("observer yes"), "OBSERVER ON")
        self.assertEqual(bot._normalize_command("observer no"), "OBSERVER OFF")
        self.assertEqual(bot._normalize_command("/observer status"), "OBSERVER STATUS")

    def test_normalize_ibwr_aliases(self):
        self.assertEqual(bot._normalize_command("/ibwr"), "IBWR STATUS")
        self.assertEqual(bot._normalize_command("ibwr on"), "IBWR ON")
        self.assertEqual(bot._normalize_command("ibwr off"), "IBWR OFF")
        self.assertEqual(bot._normalize_command("ibg status"), "IBWR STATUS")

    def test_build_status_text(self):
        status = {
            "observer": {"state": "OFF", "kill_switch_active": True, "reason": "KILL_SWITCH_ACTIVE"},
            "ibwr": {"service_state": "OFF", "reason": "STOPPED"},
            "ibkr": {"connected": False, "port": None},
            "vm": {"services": {"api": {"state": "ON"}, "nginx": {"state": "ON"}, "tg-bot": {"state": "ON"}, "ibg": {"state": "OFF"}}},
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
        self.assertIn("esito=OK", txt)
        self.assertIn("observer=OFF", txt)
        self.assertIn("kill_switch=ON", txt)
        self.assertIn("ibwr=OFF", txt)
        self.assertIn("vm=api=ON", txt)
        self.assertIn("regime=CAUTION", txt)
        self.assertIn("readiness_pct=72.5", txt)

    def test_help_uses_slash_commands(self):
        txt = bot._build_help_text()
        self.assertIn("/status", txt)
        self.assertIn("/ibwr status", txt)
        self.assertIn("/ibwr on", txt)
        self.assertIn("/ibwr off", txt)
        self.assertIn("/observer on", txt)
        self.assertIn("/observer off", txt)
        self.assertIn("/observer status", txt)
        self.assertIn("/help", txt)

    def test_observer_on_blocked_message_is_explicit(self):
        cfg = bot.BotConfig(
            token="x",
            allowed_chat_ids={"1"},
            api_base="http://api",
            poll_timeout_sec=30,
            poll_sleep_sec=1.0,
            offset_path=Path("offset.txt"),
        )
        with (
            mock.patch.object(
                bot,
                "_api_json",
                return_value={"observer_state": "OFF", "reason": "IBKR_DISCONNECTED", "applied_action": "blocked", "kill_switch_active": True},
            ),
            mock.patch.object(bot, "_send_message") as send,
        ):
            bot._handle_command(object(), cfg, "1", "OBSERVER ON")
        self.assertTrue(send.called)
        text = send.call_args.args[3]
        self.assertIn("OBSERVER ON NON ATTIVO", text)
        self.assertIn("esito=BLOCCATO", text)
        self.assertIn("stato_corrente=OFF", text)
        self.assertIn("motivo=IBKR_DISCONNECTED", text)
        self.assertIn("transizione=BLOCCATO", text)

    def test_observer_off_message_reports_active(self):
        cfg = bot.BotConfig(
            token="x",
            allowed_chat_ids={"1"},
            api_base="http://api",
            poll_timeout_sec=30,
            poll_sleep_sec=1.0,
            offset_path=Path("offset.txt"),
        )
        with (
            mock.patch.object(
                bot,
                "_api_json",
                return_value={"observer_state": "OFF", "reason": "MANUAL_OFF", "applied_action": "activate", "kill_switch_active": True},
            ),
            mock.patch.object(bot, "_send_message") as send,
        ):
            bot._handle_command(object(), cfg, "1", "OBSERVER OFF")
        self.assertTrue(send.called)
        text = send.call_args.args[3]
        self.assertIn("OBSERVER OFF ATTIVO", text)
        self.assertIn("esito=OK", text)
        self.assertIn("kill_switch=ON", text)
        self.assertIn("motivo=MANUAL_OFF", text)
        self.assertIn("transizione=KILL_SWITCH_ON", text)

    def test_ibwr_on_message(self):
        cfg = bot.BotConfig(
            token="x",
            allowed_chat_ids={"1"},
            api_base="http://api",
            poll_timeout_sec=30,
            poll_sleep_sec=1.0,
            offset_path=Path("offset.txt"),
        )
        with (
            mock.patch.object(
                bot,
                "_api_json",
                return_value={"service_state": "ON", "reason": "STARTED", "applied_action": "start"},
            ),
            mock.patch.object(bot, "_send_message") as send,
        ):
            bot._handle_command(object(), cfg, "1", "IBWR ON")
        self.assertTrue(send.called)
        text = send.call_args.args[3]
        self.assertIn("IBWR ON", text)
        self.assertIn("esito=OK", text)
        self.assertIn("stato_corrente=ON", text)
        self.assertIn("motivo=STARTED", text)
        self.assertIn("transizione=AVVIO_SERVIZIO", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
