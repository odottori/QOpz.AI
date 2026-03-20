"""
tests/test_session_runner.py — Test suite per scripts/session_runner.py

Copre:
  - nyse_holidays: anni noti, festività fisse e mobili
  - is_trading_day: weekend, festivo, giorno normale
  - _next_session_dt: ordine corretto, skip non-trading days
  - CLI --check-day
  - run_morning / run_eod: mock httpx, verifica struttura output
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date, datetime, time as time_cls, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.session_runner import (
    _next_session_dt,
    is_trading_day,
    nyse_holidays,
    run_eod,
    run_morning,
)


# ─────────────────────────────────────────────────────────────────────────────
# NYSE holidays
# ─────────────────────────────────────────────────────────────────────────────

class TestNyseHolidays(unittest.TestCase):

    def test_2026_new_years(self):
        h = nyse_holidays(2026)
        self.assertIn(date(2026, 1, 1), h)

    def test_2026_christmas(self):
        h = nyse_holidays(2026)
        self.assertIn(date(2026, 12, 25), h)

    def test_2026_independence_day(self):
        # July 4 2026 is Saturday → observed Friday July 3
        h = nyse_holidays(2026)
        self.assertIn(date(2026, 7, 3), h)
        self.assertNotIn(date(2026, 7, 4), h)  # sabato non nel set (weekend)

    def test_2026_thanksgiving(self):
        # 4° giovedì novembre 2026 = 26 novembre
        h = nyse_holidays(2026)
        self.assertIn(date(2026, 11, 26), h)

    def test_2026_mlk(self):
        # 3° lunedì gennaio 2026 = 19 gennaio
        h = nyse_holidays(2026)
        self.assertIn(date(2026, 1, 19), h)

    def test_2026_good_friday(self):
        # Pasqua 2026 = 5 aprile → Good Friday = 3 aprile
        h = nyse_holidays(2026)
        self.assertIn(date(2026, 4, 3), h)

    def test_2026_juneteenth(self):
        # Juneteenth 2026 = June 19 (venerdì → nessuno shift)
        h = nyse_holidays(2026)
        self.assertIn(date(2026, 6, 19), h)

    def test_count_reasonable(self):
        h = nyse_holidays(2026)
        # NYSE chiude tipicamente 9-10 giorni l'anno
        self.assertGreaterEqual(len(h), 9)
        self.assertLessEqual(len(h), 12)

    def test_2025_holidays_exist(self):
        h = nyse_holidays(2025)
        self.assertIn(date(2025, 1, 1), h)  # New Year's
        self.assertIn(date(2025, 12, 25), h)  # Christmas


# ─────────────────────────────────────────────────────────────────────────────
# is_trading_day
# ─────────────────────────────────────────────────────────────────────────────

class TestIsTradingDay(unittest.TestCase):

    def test_saturday_not_trading(self):
        # 2026-03-21 è sabato
        self.assertFalse(is_trading_day(date(2026, 3, 21)))

    def test_sunday_not_trading(self):
        # 2026-03-22 è domenica
        self.assertFalse(is_trading_day(date(2026, 3, 22)))

    def test_monday_trading(self):
        # 2026-03-23 è lunedì normale
        self.assertTrue(is_trading_day(date(2026, 3, 23)))

    def test_holiday_not_trading(self):
        # MLK Day 2026 = 19 gennaio (lunedì)
        self.assertFalse(is_trading_day(date(2026, 1, 19)))

    def test_regular_friday_trading(self):
        # 2026-03-20 è venerdì (non festivo)
        self.assertTrue(is_trading_day(date(2026, 3, 20)))

    def test_christmas_not_trading(self):
        self.assertFalse(is_trading_day(date(2026, 12, 25)))

    def test_default_uses_today(self):
        # Non solleva eccezioni con default
        result = is_trading_day()
        self.assertIsInstance(result, bool)


# ─────────────────────────────────────────────────────────────────────────────
# _next_session_dt
# ─────────────────────────────────────────────────────────────────────────────

class TestNextSessionDt(unittest.TestCase):

    def _make_now(self, iso: str) -> datetime:
        """Crea datetime UTC da stringa ISO."""
        return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)

    def test_morning_before_morning_time(self):
        # Mercoledì 2026-03-18 ore 08:00 EST → prossima = morning 09:00 stesso giorno
        now = self._make_now("2026-03-18T13:00:00")  # 13:00 UTC = 09:00 EST
        morning_t = time_cls(9, 0)
        eod_t = time_cls(16, 30)
        # alle 13:00 UTC siamo GIA alle 09:00 EST, quindi morning è passata
        # next = EOD 16:30 EST = 21:30 UTC
        dt, typ = _next_session_dt(now, morning_t, eod_t, "America/New_York")
        self.assertEqual(typ, "eod")

    def test_morning_far_before(self):
        # Mercoledì 2026-03-18 ore 07:00 EST (12:00 UTC) → prossima = morning 09:00 EST
        now = self._make_now("2026-03-18T12:00:00")  # 12:00 UTC = 08:00 EST
        morning_t = time_cls(9, 0)
        eod_t = time_cls(16, 30)
        dt, typ = _next_session_dt(now, morning_t, eod_t, "America/New_York")
        self.assertEqual(typ, "morning")
        self.assertEqual(dt.hour, 9)
        self.assertEqual(dt.minute, 0)

    def test_after_eod_goes_to_next_trading_day(self):
        # Venerdì 2026-03-20 ore 17:00 EST (22:00 UTC) → prossima = lunedì 09:00 EST
        now = self._make_now("2026-03-20T22:00:00")  # 17:00 EST venerdì
        morning_t = time_cls(9, 0)
        eod_t = time_cls(16, 30)
        dt, typ = _next_session_dt(now, morning_t, eod_t, "America/New_York")
        self.assertEqual(typ, "morning")
        # Deve essere lunedì 23 marzo (il weekend viene saltato)
        from zoneinfo import ZoneInfo
        dt_local = dt.astimezone(ZoneInfo("America/New_York"))
        self.assertEqual(dt_local.weekday(), 0)  # lunedì

    def test_result_is_future(self):
        now = datetime.now(timezone.utc)
        morning_t = time_cls(9, 0)
        eod_t = time_cls(16, 30)
        dt, typ = _next_session_dt(now, morning_t, eod_t, "America/New_York")
        dt_utc = dt.astimezone(timezone.utc)
        self.assertGreater(dt_utc, now)

    def test_skips_weekend(self):
        # Sabato 2026-03-21 ore 10:00 UTC → prossima sessione = lunedì mattina
        now = self._make_now("2026-03-21T10:00:00")
        morning_t = time_cls(9, 0)
        eod_t = time_cls(16, 30)
        dt, typ = _next_session_dt(now, morning_t, eod_t, "America/New_York")
        self.assertEqual(typ, "morning")
        from zoneinfo import ZoneInfo
        dt_local = dt.astimezone(ZoneInfo("America/New_York"))
        self.assertGreaterEqual(dt_local.weekday(), 0)  # non sabato/domenica
        self.assertLessEqual(dt_local.weekday(), 4)


# ─────────────────────────────────────────────────────────────────────────────
# run_morning / run_eod — mock httpx
# ─────────────────────────────────────────────────────────────────────────────

def _mock_response(data: dict, status: int = 200) -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.json.return_value = data
    m.raise_for_status = MagicMock()
    return m


class TestRunMorning(unittest.TestCase):

    def test_structure(self):
        ev = MagicMock()
        ev.block_trade = False
        ev.earnings_flag = None
        ev.dividend_flag = None
        ev.days_to_earnings = None

        with patch("scripts.session_runner._get") as mock_get, \
             patch("scripts.session_runner._post") as mock_post, \
             patch("scripts.fetch_iv_history.fetch_iv_history", return_value=[]) as _miv, \
             patch("scripts.fetch_iv_history.save_iv_history") as _msv, \
             patch("scripts.events_calendar.check_events", return_value=ev):

            mock_get.side_effect = lambda base, path, params=None: (
                (True, {"regime": "NORMAL", "n_recent": 30}) if "regime" in path else
                (True, {"quote_symbols": ["SPY", "QQQ"]}) if "ibkr_context" in path else
                (True, {"universe_size": 2})
            )
            mock_post.return_value = (True, {"ok": True, "mp3_path": None})

            result = run_morning(profile="dev", api_base="http://localhost:9999")

        self.assertIn("type", result)
        self.assertEqual(result["type"], "morning")
        self.assertIn("steps", result)
        self.assertIn("regime", result["steps"])
        self.assertIn("briefing", result["steps"])
        self.assertIn("started_at", result)
        self.assertIn("finished_at", result)
        self.assertIsInstance(result["errors"], list)
        self.assertIsInstance(result["ok"], bool)


class TestRunEod(unittest.TestCase):

    def test_structure(self):
        with patch("scripts.session_runner._get") as mock_get:
            mock_get.side_effect = lambda base, path, params=None: (
                (True, {"trades": 5, "sharpe_annualized": 0.8, "max_drawdown": 0.05,
                        "win_rate": 0.6, "profit_factor": 1.3}) if "summary" in path else
                (True, {"candidates": [{"exit_score": 6, "symbol": "SPY"}]}) if "exit_candidates" in path else
                (True, {"regime": "NORMAL", "n_recent": 25}) if "regime" in path else
                (True, {"data_mode": "SYNTHETIC", "kelly_enabled": False, "kill_switch_active": False})
            )
            result = run_eod(profile="dev", api_base="http://localhost:9999")

        self.assertEqual(result["type"], "eod")
        self.assertIn("steps", result)
        self.assertIn("paper_summary", result["steps"])
        self.assertIn("exit_candidates", result["steps"])
        self.assertEqual(result["steps"]["exit_candidates"]["urgent"], 1)
        self.assertEqual(result["steps"]["paper_summary"]["trades"], 5)
        self.assertIsInstance(result["ok"], bool)


# ─────────────────────────────────────────────────────────────────────────────
# CLI --check-day
# ─────────────────────────────────────────────────────────────────────────────

class TestCliCheckDay(unittest.TestCase):

    def test_check_day_json(self):
        import subprocess
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "session_runner.py"),
             "--check-day", "--format", "json"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout.strip())
        self.assertIn("date", data)
        self.assertIn("is_trading_day", data)
        self.assertIsInstance(data["is_trading_day"], bool)
        self.assertIn("holidays_this_year", data)

    def test_check_day_text(self):
        import subprocess
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "session_runner.py"), "--check-day"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.strip())


if __name__ == "__main__":
    unittest.main()
