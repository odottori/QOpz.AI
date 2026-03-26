from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from api.routers.pipeline import opz_data_refresh
except Exception:
    opz_data_refresh = None


class _DummyMgr:
    def disconnect(self) -> None:
        return None


@unittest.skipIf(opz_data_refresh is None, "fastapi not installed in this environment")
class TestDataRefreshIvHistoryStatus(unittest.TestCase):
    def test_ibkr_iv_history_is_partial_when_zero_points_with_premarket_error(self):
        recorded: list[dict] = []

        def _record_ingestion_run(**kwargs):
            recorded.append(kwargs)

        with patch("execution.storage.record_ingestion_run", side_effect=_record_ingestion_run), patch(
            "execution.storage.list_ingestion_runs", return_value=[]
        ), patch(
            "api.opz_api.opz_universe_latest",
            return_value={"items": [{"symbol": "AAPL"}]},
        ), patch(
            "scripts.fetch_iv_history.fetch_iv_history",
            return_value=[{"date": "2026-03-25", "iv": 0.2, "source": "yfinance"}],
        ), patch(
            "scripts.fetch_iv_history.save_iv_history",
            return_value=None,
        ), patch(
            "scripts.events_calendar.fetch_earnings_date",
            return_value=None,
        ), patch(
            "scripts.events_calendar.fetch_dividend_date",
            return_value=None,
        ), patch(
            "scripts.fetch_macro.fetch_macro_indicators",
            return_value={"n_series": 4, "n_saved": 4, "n_errors": 0},
        ), patch(
            "execution.ibkr_connection.get_manager",
            return_value=_DummyMgr(),
        ), patch(
            "api.opz_api.opz_ibkr_account",
            return_value={"connected": True, "positions": []},
        ), patch(
            "scripts.fetch_iv_history_ibkr.merge_today_iv_point",
            return_value=None,
        ), patch(
            "execution.storage.save_symbol_snapshots",
            return_value=None,
        ), patch(
            "scripts.fetch_iv_history_ibkr.capture_ibkr_universe_snapshot",
            return_value=[
                {
                    "symbol": "AAPL",
                    "underlying_price": 200.0,
                    "contracts_count": 6,
                    "greeks_complete": 0,
                    "atm_iv": None,
                    "error": "PRE-MKT - IV ATM non disponibile prima apertura USA (09:30 ET)",
                }
            ],
        ):
            out = opz_data_refresh(profile="paper")

        self.assertTrue(out["ok"])
        row = next((r for r in recorded if r.get("feed") == "ibkr_iv_history"), None)
        self.assertIsNotNone(row, "ibkr_iv_history run not recorded")
        self.assertEqual(row["status"], "partial")
        self.assertEqual(row["records_in"], 1)
        self.assertEqual(row["records_out"], 0)
        self.assertIn("PRE-MKT", str(row.get("error_msg", "")))

    def test_ibkr_greeks_is_error_when_no_symbol_has_4_of_4_greeks(self):
        recorded: list[dict] = []

        def _record_ingestion_run(**kwargs):
            recorded.append(kwargs)

        with patch("execution.storage.record_ingestion_run", side_effect=_record_ingestion_run), patch(
            "execution.storage.list_ingestion_runs", return_value=[]
        ), patch(
            "api.opz_api.opz_universe_latest",
            return_value={"items": [{"symbol": "AAPL"}]},
        ), patch(
            "scripts.fetch_iv_history.fetch_iv_history",
            return_value=[{"date": "2026-03-25", "iv": 0.2, "source": "yfinance"}],
        ), patch(
            "scripts.fetch_iv_history.save_iv_history",
            return_value=None,
        ), patch(
            "scripts.events_calendar.fetch_earnings_date",
            return_value=None,
        ), patch(
            "scripts.events_calendar.fetch_dividend_date",
            return_value=None,
        ), patch(
            "scripts.fetch_macro.fetch_macro_indicators",
            return_value={"n_series": 4, "n_saved": 4, "n_errors": 0},
        ), patch(
            "execution.ibkr_connection.get_manager",
            return_value=_DummyMgr(),
        ), patch(
            "api.opz_api.opz_ibkr_account",
            return_value={"connected": True, "positions": []},
        ), patch(
            "scripts.fetch_iv_history_ibkr.merge_today_iv_point",
            return_value=None,
        ), patch(
            "execution.storage.save_symbol_snapshots",
            return_value=None,
        ), patch(
            "scripts.fetch_iv_history_ibkr.capture_ibkr_universe_snapshot",
            return_value=[
                {
                    "symbol": "AAPL",
                    "underlying_price": 200.0,
                    "contracts_count": 6,
                    "greeks_complete": 3,
                    "atm_iv": 0.22,
                    "error": None,
                }
            ],
        ):
            out = opz_data_refresh(profile="paper")

        self.assertTrue(out["ok"])
        row = next((r for r in recorded if r.get("feed") == "ibkr_greeks"), None)
        self.assertIsNotNone(row, "ibkr_greeks run not recorded")
        self.assertEqual(row["status"], "error")
        self.assertEqual(row["records_in"], 1)
        self.assertEqual(row["records_out"], 0)

    def test_ibkr_greeks_uses_valid_symbol_count_when_usable(self):
        recorded: list[dict] = []

        def _record_ingestion_run(**kwargs):
            recorded.append(kwargs)

        with patch("execution.storage.record_ingestion_run", side_effect=_record_ingestion_run), patch(
            "execution.storage.list_ingestion_runs", return_value=[]
        ), patch(
            "api.opz_api.opz_universe_latest",
            return_value={"items": [{"symbol": "AAPL"}, {"symbol": "MSFT"}]},
        ), patch(
            "scripts.fetch_iv_history.fetch_iv_history",
            return_value=[{"date": "2026-03-25", "iv": 0.2, "source": "yfinance"}],
        ), patch(
            "scripts.fetch_iv_history.save_iv_history",
            return_value=None,
        ), patch(
            "scripts.events_calendar.fetch_earnings_date",
            return_value=None,
        ), patch(
            "scripts.events_calendar.fetch_dividend_date",
            return_value=None,
        ), patch(
            "scripts.fetch_macro.fetch_macro_indicators",
            return_value={"n_series": 4, "n_saved": 4, "n_errors": 0},
        ), patch(
            "execution.ibkr_connection.get_manager",
            return_value=_DummyMgr(),
        ), patch(
            "api.opz_api.opz_ibkr_account",
            return_value={"connected": True, "positions": []},
        ), patch(
            "scripts.fetch_iv_history_ibkr.merge_today_iv_point",
            return_value=None,
        ), patch(
            "execution.storage.save_symbol_snapshots",
            return_value=None,
        ), patch(
            "scripts.fetch_iv_history_ibkr.capture_ibkr_universe_snapshot",
            return_value=[
                {
                    "symbol": "AAPL",
                    "underlying_price": 200.0,
                    "contracts_count": 6,
                    "greeks_complete": 4,
                    "atm_strike": 200.0,
                    "atm_iv": 0.22,
                    "error": None,
                },
                {
                    "symbol": "MSFT",
                    "underlying_price": 300.0,
                    "contracts_count": 6,
                    "greeks_complete": 3,
                    "atm_strike": 300.0,
                    "atm_iv": 0.21,
                    "error": None,
                },
            ],
        ):
            out = opz_data_refresh(profile="paper")

        self.assertTrue(out["ok"])
        row = next((r for r in recorded if r.get("feed") == "ibkr_greeks"), None)
        self.assertIsNotNone(row, "ibkr_greeks run not recorded")
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["records_in"], 1)
        self.assertEqual(row["records_out"], 1)
        self.assertEqual(row["symbols_count"], 1)


if __name__ == "__main__":
    unittest.main()
