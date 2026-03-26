from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

import execution.storage as st


class TestSymbolSnapshotTrend(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = Path(".tmp_test") / f"snap_trend_{uuid.uuid4().hex}"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._orig_db = st.EXEC_DB_PATH
        self._orig_ready = st._SCHEMA_READY
        st.EXEC_DB_PATH = self._tmp_dir / "test_execution.duckdb"
        st._SCHEMA_READY = False
        st.init_execution_schema()

    def tearDown(self) -> None:
        st.EXEC_DB_PATH = self._orig_db
        st._SCHEMA_READY = self._orig_ready
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    @staticmethod
    def _row(rows: list[dict], symbol: str) -> dict:
        for r in rows:
            if str(r.get("symbol", "")).upper() == symbol.upper():
                return r
        raise AssertionError(f"symbol not found: {symbol}")

    def test_first_snapshot_trend_is_flat(self) -> None:
        st.save_symbol_snapshots(
            [
                {
                    "symbol": "AAPL",
                    "underlying_price": 250.0,
                    "atm_strike": 250.0,
                    "atm_iv": 0.20,
                    "greeks_complete": 4,
                    "contracts_count": 6,
                    "error": None,
                }
            ],
            profile="paper",
        )
        row = self._row(st.list_symbol_snapshots(profile="paper"), "AAPL")
        self.assertIsNone(row.get("trend_dir"))

    def test_trend_flat_when_two_consecutive_snapshots_are_equal(self) -> None:
        payload = {
            "symbol": "AAPL",
            "underlying_price": 250.0,
            "atm_strike": 250.0,
            "atm_iv": 0.20,
            "greeks_complete": 4,
            "contracts_count": 6,
            "error": None,
        }
        st.save_symbol_snapshots([payload], profile="paper")
        st.save_symbol_snapshots([payload], profile="paper")
        row = self._row(st.list_symbol_snapshots(profile="paper"), "AAPL")
        self.assertEqual(row.get("trend_dir"), "flat")

    def test_trend_up_when_snapshot_improves(self) -> None:
        st.save_symbol_snapshots(
            [
                {
                    "symbol": "MSFT",
                    "underlying_price": None,
                    "atm_strike": 388.0,
                    "atm_iv": None,
                    "greeks_complete": 0,
                    "contracts_count": 6,
                    "error": "PRE-MKT - IV ATM non disponibile prima apertura USA (09:30 ET)",
                }
            ],
            profile="paper",
        )
        st.save_symbol_snapshots(
            [
                {
                    "symbol": "MSFT",
                    "underlying_price": 369.0,
                    "atm_strike": 388.0,
                    "atm_iv": 0.12,
                    "greeks_complete": 4,
                    "contracts_count": 6,
                    "error": None,
                }
            ],
            profile="paper",
        )
        row = self._row(st.list_symbol_snapshots(profile="paper"), "MSFT")
        self.assertEqual(row.get("trend_dir"), "up")

    def test_trend_down_even_if_latest_is_sticky_last_good(self) -> None:
        st.save_symbol_snapshots(
            [
                {
                    "symbol": "NVDA",
                    "underlying_price": 177.0,
                    "atm_strike": 177.0,
                    "atm_iv": 0.28,
                    "greeks_complete": 4,
                    "contracts_count": 6,
                    "error": None,
                }
            ],
            profile="paper",
        )
        st.save_symbol_snapshots(
            [
                {
                    "symbol": "NVDA",
                    "underlying_price": None,
                    "atm_strike": 177.0,
                    "atm_iv": None,
                    "greeks_complete": 0,
                    "contracts_count": 6,
                    "error": "qualifyContracts opzioni ATM fallito",
                }
            ],
            profile="paper",
        )
        row = self._row(st.list_symbol_snapshots(profile="paper"), "NVDA")
        self.assertEqual(int(row.get("greeks_complete") or 0), 4)  # last-good retained
        self.assertEqual(row.get("trend_dir"), "down")             # raw incoming worsened


if __name__ == "__main__":
    unittest.main()
