"""
tests/test_roc0_iv_history.py — ROC0-T3

Test suite per scripts/fetch_iv_history.py.
Nessuna rete: yfinance viene mockato con dati deterministici inline.

Cosa viene testato:
  - _hv_from_yfinance: mock dei dati di prezzo, calcolo HV
  - _iv_from_option_chain: mock della chain, estrazione ATM IV
  - fetch_iv_history: composizione HV + chain IV
  - save_iv_history / load_iv_history: roundtrip JSON
  - load_iv_history: file assente, file malformato, zero-IV filtrati
  - integrazione con compute_iv_zscore
  - CLI _run: simbolo OK, simbolo senza dati (exit=2), verbose
"""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.fetch_iv_history import (
    DEFAULT_LOOKBACK_DAYS,
    MIN_POINTS_REQUIRED,
    _hv_from_yfinance,
    _history_path,
    _iv_from_option_chain,
    _run,
    fetch_iv_history,
    load_iv_history,
    save_iv_history,
)
from strategy.opportunity_scanner import compute_iv_zscore


# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_iv_points(n: int, mean: float = 0.25) -> list[dict]:
    """Genera n punti IV deterministici (nessuna rete)."""
    today = datetime.now(timezone.utc).date()
    return [
        {"date": (today - timedelta(days=n - 1 - i)).isoformat(),
         "iv": round(mean + 0.01 * (i % 7 - 3), 6)}
        for i in range(n)
    ]


def _make_iv_floats(n: int, mean: float = 0.25) -> list[float]:
    return [p["iv"] for p in _make_iv_points(n, mean)]


def _mock_yf_ticker(closes: list[float], options: list[str] | None = None):
    """Restituisce un mock di yfinance.Ticker con prezzi e options forniti."""
    import pandas as pd
    today = datetime.now(timezone.utc).date()
    dates = [today - timedelta(days=len(closes) - 1 - i) for i in range(len(closes))]
    df = pd.DataFrame({"Close": closes}, index=pd.to_datetime(dates))

    ticker = MagicMock()
    ticker.history.return_value = df
    ticker.options = tuple(options or [])
    ticker.fast_info = MagicMock()
    ticker.fast_info.last_price = 500.0
    return ticker


# ─────────────────────────────────────────────────────────────────────────────
# 1.  _hv_from_yfinance  (mock di yfinance)
# ─────────────────────────────────────────────────────────────────────────────

class TestHvFromYfinance(unittest.TestCase):

    def _mock_ticker(self, n: int = 80):
        closes = [100.0 * (1 + 0.005 * math.sin(i * 0.3)) for i in range(n)]
        return _mock_yf_ticker(closes)

    def test_returns_list_with_sufficient_prices(self):
        ticker = self._mock_ticker(80)
        with patch("scripts.fetch_iv_history.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            result = _hv_from_yfinance("AAPL", 60)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_each_point_has_date_and_iv(self):
        ticker = self._mock_ticker(80)
        with patch("scripts.fetch_iv_history.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            result = _hv_from_yfinance("AAPL", 60)
        for p in result:
            self.assertIn("date", p)
            self.assertIn("iv", p)
            self.assertGreater(p["iv"], 0.0)

    def test_dates_sorted_ascending(self):
        ticker = self._mock_ticker(80)
        with patch("scripts.fetch_iv_history.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            result = _hv_from_yfinance("AAPL", 60)
        dates = [p["date"] for p in result]
        self.assertEqual(dates, sorted(dates))

    def test_returns_empty_for_short_price_history(self):
        closes = [100.0 + i for i in range(10)]  # solo 10 prezzi
        ticker = _mock_yf_ticker(closes)
        with patch("scripts.fetch_iv_history.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            result = _hv_from_yfinance("AAPL", 60)
        self.assertEqual(result, [])

    def test_max_length_is_lookback_days(self):
        ticker = self._mock_ticker(200)
        with patch("scripts.fetch_iv_history.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            result = _hv_from_yfinance("AAPL", 30)
        self.assertLessEqual(len(result), 30)


# ─────────────────────────────────────────────────────────────────────────────
# 2.  _iv_from_option_chain  (mock di yfinance)
# ─────────────────────────────────────────────────────────────────────────────

class TestIvFromOptionChain(unittest.TestCase):

    def _expiry_in_range(self, days: int = 30) -> str:
        return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()

    def _mock_chain(self, atm_iv: float = 0.28, underlying: float = 500.0):
        """Mock di ticker.option_chain() con ATM call+put a IV nota."""
        import pandas as pd
        calls = pd.DataFrame({
            "strike": [490.0, 500.0, 510.0],
            "impliedVolatility": [0.30, atm_iv, 0.26],
        })
        puts = pd.DataFrame({
            "strike": [490.0, 500.0, 510.0],
            "impliedVolatility": [0.31, atm_iv + 0.005, 0.27],
        })
        chain_mock = MagicMock()
        chain_mock.calls = calls
        chain_mock.puts = puts

        ticker = MagicMock()
        ticker.options = (self._expiry_in_range(30),)
        ticker.option_chain.return_value = chain_mock
        ticker.fast_info = MagicMock()
        ticker.fast_info.last_price = underlying
        return ticker

    def test_returns_float_for_valid_chain(self):
        ticker = self._mock_chain(atm_iv=0.28)
        with patch("scripts.fetch_iv_history.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            iv = _iv_from_option_chain("SPY")
        self.assertIsNotNone(iv)
        self.assertIsInstance(iv, float)
        self.assertGreater(iv, 0.0)

    def test_returns_expected_atm_iv(self):
        ticker = self._mock_chain(atm_iv=0.28)
        with patch("scripts.fetch_iv_history.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            iv = _iv_from_option_chain("SPY")
        # avg(0.28, 0.285) = 0.2825
        self.assertAlmostEqual(iv, 0.2825, places=3)

    def test_returns_none_when_no_expirations(self):
        ticker = MagicMock()
        ticker.options = ()
        with patch("scripts.fetch_iv_history.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            iv = _iv_from_option_chain("SPY")
        self.assertIsNone(iv)

    def test_returns_none_when_no_expiry_in_range(self):
        ticker = MagicMock()
        ticker.options = ("2000-01-01",)  # nel passato → DTE negativo
        with patch("scripts.fetch_iv_history.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            iv = _iv_from_option_chain("SPY")
        self.assertIsNone(iv)


# ─────────────────────────────────────────────────────────────────────────────
# 3.  fetch_iv_history  (mock combinato)
# ─────────────────────────────────────────────────────────────────────────────

class TestFetchIvHistory(unittest.TestCase):

    def test_enriches_with_chain_iv(self):
        hv_history = _make_iv_points(60)
        with patch("scripts.fetch_iv_history._hv_from_yfinance", return_value=hv_history):
            with patch("scripts.fetch_iv_history._iv_from_option_chain", return_value=0.32):
                result = fetch_iv_history("AAPL")
        today = datetime.now(timezone.utc).date().isoformat()
        last = result[-1]
        self.assertEqual(last["date"], today)
        self.assertAlmostEqual(last["iv"], 0.32)

    def test_returns_hv_only_when_chain_unavailable(self):
        hv_history = _make_iv_points(60)
        with patch("scripts.fetch_iv_history._hv_from_yfinance", return_value=hv_history):
            with patch("scripts.fetch_iv_history._iv_from_option_chain", return_value=None):
                result = fetch_iv_history("AAPL")
        self.assertEqual(len(result), 60)

    def test_returns_empty_when_yfinance_unavailable(self):
        with patch("scripts.fetch_iv_history._hv_from_yfinance", return_value=[]):
            with patch("scripts.fetch_iv_history._iv_from_option_chain", return_value=None):
                result = fetch_iv_history("FAKESYMBOL")
        self.assertEqual(result, [])

    def test_result_sorted_by_date(self):
        hv = _make_iv_points(60)
        with patch("scripts.fetch_iv_history._hv_from_yfinance", return_value=hv):
            with patch("scripts.fetch_iv_history._iv_from_option_chain", return_value=0.28):
                result = fetch_iv_history("SPY")
        dates = [p["date"] for p in result]
        self.assertEqual(dates, sorted(dates))


# ─────────────────────────────────────────────────────────────────────────────
# 4.  save_iv_history / load_iv_history  roundtrip
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveLoadRoundtrip(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _patch_dir(self):
        import scripts.fetch_iv_history as mod
        return patch.object(mod, "IV_HISTORY_DIR", Path(self._tmpdir.name))

    def test_save_creates_json_file(self):
        hist = _make_iv_points(10)
        with self._patch_dir():
            path = save_iv_history("SAVE_TEST", hist)
        self.assertTrue(path.exists())

    def test_saved_json_structure(self):
        hist = _make_iv_points(5)
        with self._patch_dir():
            path = save_iv_history("STRUCT", hist)
            data = json.loads(path.read_text())
        for key in ("symbol", "data_mode", "updated_at", "points", "iv_history"):
            self.assertIn(key, data)
        self.assertEqual(data["symbol"], "STRUCT")
        self.assertEqual(data["points"], 5)

    def test_load_returns_float_list(self):
        hist = _make_iv_points(40)
        with self._patch_dir():
            save_iv_history("LOAD_FLOAT", hist)
            values = load_iv_history("LOAD_FLOAT")
        self.assertEqual(len(values), 40)
        for v in values:
            self.assertIsInstance(v, float)
            self.assertGreater(v, 0.0)

    def test_load_order_matches_save_order(self):
        hist = _make_iv_points(20)
        with self._patch_dir():
            save_iv_history("ORDER", hist)
            values = load_iv_history("ORDER")
        expected = [p["iv"] for p in sorted(hist, key=lambda p: p["date"])]
        self.assertEqual(values, expected)

    def test_load_missing_file_returns_empty(self):
        with self._patch_dir():
            values = load_iv_history("GHOST_SYMBOL")
        self.assertEqual(values, [])

    def test_load_malformed_json_returns_empty(self):
        import scripts.fetch_iv_history as mod
        bad_path = Path(self._tmpdir.name) / "iv_history_BAD.json"
        bad_path.write_text("NOT JSON {{{", encoding="utf-8")
        with patch.object(mod, "IV_HISTORY_DIR", Path(self._tmpdir.name)):
            values = load_iv_history("BAD")
        self.assertEqual(values, [])

    def test_load_filters_zero_iv(self):
        import scripts.fetch_iv_history as mod
        hist = [{"date": "2026-01-01", "iv": 0.0},
                {"date": "2026-01-02", "iv": 0.25}]
        path = Path(self._tmpdir.name) / "iv_history_ZEROIV.json"
        path.write_text(json.dumps({"iv_history": hist}), encoding="utf-8")
        with patch.object(mod, "IV_HISTORY_DIR", Path(self._tmpdir.name)):
            values = load_iv_history("ZEROIV")
        self.assertEqual(len(values), 1)
        self.assertAlmostEqual(values[0], 0.25)

    def test_symbol_stored_uppercase(self):
        hist = _make_iv_points(5)
        with self._patch_dir():
            path = save_iv_history("lower", hist)
            data = json.loads(path.read_text())
        self.assertEqual(data["symbol"], "LOWER")


# ─────────────────────────────────────────────────────────────────────────────
# 5.  Integrazione con compute_iv_zscore
# ─────────────────────────────────────────────────────────────────────────────

class TestIvHistoryZscoreIntegration(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _patch_dir(self):
        import scripts.fetch_iv_history as mod
        return patch.object(mod, "IV_HISTORY_DIR", Path(self._tmpdir.name))

    def test_zscore_computable_after_save(self):
        hist = _make_iv_points(90)
        with self._patch_dir():
            save_iv_history("AAPL", hist)
            values = load_iv_history("AAPL")
        self.assertGreaterEqual(len(values), 60)
        z30 = compute_iv_zscore(values[-1], values, 30)
        z60 = compute_iv_zscore(values[-1], values, 60)
        self.assertIsNotNone(z30)
        self.assertIsNotNone(z60)
        self.assertIsInstance(z30, float)

    def test_zscore_none_with_too_few_points(self):
        hist = _make_iv_points(15)
        with self._patch_dir():
            save_iv_history("FEW", hist)
            values = load_iv_history("FEW")
        self.assertIsNone(compute_iv_zscore(values[-1], values, 30))

    def test_zscore_30d_ok_but_60d_none(self):
        hist = _make_iv_points(35)
        with self._patch_dir():
            save_iv_history("MED", hist)
            values = load_iv_history("MED")
        self.assertIsNotNone(compute_iv_zscore(values[-1], values, 30))
        self.assertIsNone(compute_iv_zscore(values[-1], values, 60))


# ─────────────────────────────────────────────────────────────────────────────
# 6.  CLI _run
# ─────────────────────────────────────────────────────────────────────────────

class TestCliRun(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _patch_dir(self):
        import scripts.fetch_iv_history as mod
        return patch.object(mod, "IV_HISTORY_DIR", Path(self._tmpdir.name))

    def _mock_fetch(self, history: list[dict]):
        return patch("scripts.fetch_iv_history.fetch_iv_history", return_value=history)

    def test_exit_zero_with_valid_data(self):
        hist = _make_iv_points(60)
        with self._patch_dir(), self._mock_fetch(hist):
            code = _run(["SPY"], days=60, verbose=False)
        self.assertEqual(code, 0)

    def test_exit_two_when_no_data(self):
        with self._patch_dir(), self._mock_fetch([]):
            code = _run(["MISSING"], days=60, verbose=False)
        self.assertEqual(code, 2)

    def test_exit_two_when_few_points(self):
        hist = _make_iv_points(5)
        with self._patch_dir(), self._mock_fetch(hist):
            code = _run(["TINY"], days=60, verbose=False)
        self.assertEqual(code, 2)

    def test_creates_json_file(self):
        hist = _make_iv_points(60)
        with self._patch_dir(), self._mock_fetch(hist):
            _run(["TSLA"], days=60, verbose=False)
        files = list(Path(self._tmpdir.name).glob("iv_history_*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "iv_history_TSLA.json")

    def test_symbol_uppercased(self):
        hist = _make_iv_points(60)
        with self._patch_dir(), self._mock_fetch(hist):
            _run(["aapl"], days=60, verbose=False)
        files = list(Path(self._tmpdir.name).glob("*.json"))
        self.assertEqual(files[0].name, "iv_history_AAPL.json")

    def test_multiple_symbols(self):
        hist = _make_iv_points(60)
        with self._patch_dir(), self._mock_fetch(hist):
            code = _run(["AA", "BB", "CC"], days=60, verbose=False)
        self.assertEqual(code, 0)
        files = {f.name for f in Path(self._tmpdir.name).glob("*.json")}
        for sym in ("AA", "BB", "CC"):
            self.assertIn(f"iv_history_{sym}.json", files)

    def test_verbose_no_crash(self):
        import io
        from contextlib import redirect_stdout
        hist = _make_iv_points(60)
        buf = io.StringIO()
        with self._patch_dir(), self._mock_fetch(hist):
            with redirect_stdout(buf):
                code = _run(["SPY"], days=60, verbose=True)
        self.assertEqual(code, 0)
        self.assertIn("SPY", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
