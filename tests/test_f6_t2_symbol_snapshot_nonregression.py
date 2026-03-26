from __future__ import annotations

import unittest
import uuid
from pathlib import Path
import shutil

import execution.storage as st


class TestSymbolSnapshotNonRegression(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = Path(".tmp_test") / f"snap_nonreg_{uuid.uuid4().hex}"
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
    def _get(rows: list[dict], symbol: str) -> dict:
        for r in rows:
            if str(r.get("symbol", "")).upper() == symbol.upper():
                return r
        raise AssertionError(f"symbol not found: {symbol}")

    def test_same_day_regression_keeps_last_good_snapshot(self) -> None:
        profile = "paper"
        st.save_symbol_snapshots(
            [
                {
                    "symbol": "AAPL",
                    "underlying_price": 251.0,
                    "atm_strike": 252.5,
                    "atm_iv": 0.245,
                    "atm_delta": 0.53,
                    "atm_gamma": 0.023,
                    "atm_theta": -0.16,
                    "atm_vega": 0.25,
                    "greeks_complete": 4,
                    "contracts_count": 6,
                    "error": None,
                    "iv_source": "ibkr",
                }
            ],
            profile=profile,
        )
        st.save_symbol_snapshots(
            [
                {
                    "symbol": "AAPL",
                    "underlying_price": None,
                    "atm_strike": 252.5,
                    "atm_iv": None,
                    "greeks_complete": 0,
                    "contracts_count": 6,
                    "error": "qualifyContracts opzioni ATM fallito",
                    "iv_source": "yfinance",
                }
            ],
            profile=profile,
        )

        rows = st.list_symbol_snapshots(profile=profile)
        self.assertEqual(len(rows), 1)
        aapl = self._get(rows, "AAPL")
        self.assertEqual(int(aapl["greeks_complete"] or 0), 4)
        self.assertGreater(float(aapl["atm_iv"] or 0.0), 0.0)
        self.assertGreater(float(aapl["underlying"] or 0.0), 0.0)

    def test_missing_symbol_in_followup_batch_is_retained_same_day(self) -> None:
        profile = "paper"
        st.save_symbol_snapshots(
            [
                {
                    "symbol": "AAPL",
                    "underlying_price": 251.0,
                    "atm_strike": 252.5,
                    "atm_iv": 0.245,
                    "greeks_complete": 4,
                    "contracts_count": 6,
                    "error": None,
                    "iv_source": "ibkr",
                },
                {
                    "symbol": "MSFT",
                    "underlying_price": 369.0,
                    "atm_strike": 388.0,
                    "atm_iv": 0.002,
                    "greeks_complete": 4,
                    "contracts_count": 6,
                    "error": None,
                    "iv_source": "yfinance",
                },
            ],
            profile=profile,
        )
        st.save_symbol_snapshots(
            [
                {
                    "symbol": "AAPL",
                    "underlying_price": 252.0,
                    "atm_strike": 252.5,
                    "atm_iv": 0.246,
                    "greeks_complete": 4,
                    "contracts_count": 6,
                    "error": None,
                    "iv_source": "ibkr",
                }
            ],
            profile=profile,
        )

        rows = st.list_symbol_snapshots(profile=profile)
        symbols = {str(r["symbol"]).upper() for r in rows}
        self.assertEqual(symbols, {"AAPL", "MSFT"})

    def test_first_bad_snapshot_is_stored_when_no_last_good_exists(self) -> None:
        profile = "paper"
        st.save_symbol_snapshots(
            [
                {
                    "symbol": "NVDA",
                    "underlying_price": None,
                    "atm_strike": None,
                    "atm_iv": None,
                    "greeks_complete": 0,
                    "contracts_count": 0,
                    "error": "Catena opzioni assente",
                    "iv_source": "yfinance",
                }
            ],
            profile=profile,
        )

        rows = st.list_symbol_snapshots(profile=profile)
        self.assertEqual(len(rows), 1)
        nvda = self._get(rows, "NVDA")
        self.assertEqual(int(nvda["greeks_complete"] or 0), 0)
        self.assertEqual(int(nvda["contracts_count"] or 0), 0)


if __name__ == "__main__":
    unittest.main()
