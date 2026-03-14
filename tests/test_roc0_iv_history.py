"""
tests/test_roc0_iv_history.py — ROC0-T3

Test suite per scripts/fetch_iv_history.py:
  - _synthetic_iv_history: deterministico, lunghezza corretta, valori plausibili
  - save_iv_history / load_iv_history: roundtrip JSON
  - load_iv_history: file assente, file malformato, ordine corretto
  - integrazione con compute_iv_zscore: Z-Score calcolabile dopo fetch sintetico
  - CLI _run: mode sintetico, simbolo sconosciuto non blocca altri

Tutti i test usano --synthetic o dati in-memory (nessuna rete, nessun IBKR).
"""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.fetch_iv_history import (
    DEFAULT_LOOKBACK_DAYS,
    MIN_POINTS_REQUIRED,
    _history_path,
    _run,
    _synthetic_iv_history,
    load_iv_history,
    save_iv_history,
)
from strategy.opportunity_scanner import compute_iv_zscore


# ─────────────────────────────────────────────────────────────────────────────
# 1.  _synthetic_iv_history
# ─────────────────────────────────────────────────────────────────────────────

class TestSyntheticIvHistory(unittest.TestCase):

    def test_returns_correct_length(self):
        hist = _synthetic_iv_history("TEST", n=90)
        self.assertEqual(len(hist), 90)

    def test_default_length(self):
        hist = _synthetic_iv_history("TEST")
        self.assertEqual(len(hist), DEFAULT_LOOKBACK_DAYS)

    def test_dates_are_iso_sorted(self):
        hist = _synthetic_iv_history("TEST", n=30)
        dates = [p["date"] for p in hist]
        self.assertEqual(dates, sorted(dates))

    def test_last_date_is_today(self):
        hist = _synthetic_iv_history("TEST", n=10)
        today = datetime.now(timezone.utc).date().isoformat()
        self.assertEqual(hist[-1]["date"], today)

    def test_iv_values_in_plausible_range(self):
        hist = _synthetic_iv_history("TEST", n=90)
        for p in hist:
            self.assertGreater(p["iv"], 0.0)
            self.assertLess(p["iv"], 1.0)   # IV% below 100%

    def test_deterministic_same_symbol(self):
        h1 = _synthetic_iv_history("SPY", n=30)
        h2 = _synthetic_iv_history("SPY", n=30)
        self.assertEqual(h1, h2)

    def test_different_symbols_produce_different_histories(self):
        spy = _synthetic_iv_history("SPY", n=30)
        aapl = _synthetic_iv_history("AAPL", n=30)
        # At least one point should differ
        diffs = [a["iv"] != b["iv"] for a, b in zip(spy, aapl)]
        self.assertTrue(any(diffs))

    def test_all_points_have_date_and_iv_keys(self):
        hist = _synthetic_iv_history("TEST", n=10)
        for p in hist:
            self.assertIn("date", p)
            self.assertIn("iv", p)


# ─────────────────────────────────────────────────────────────────────────────
# 2.  save_iv_history / load_iv_history  roundtrip
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
        hist = _synthetic_iv_history("SAVE_TEST", n=10)
        with self._patch_dir():
            path = save_iv_history("SAVE_TEST", hist)
        self.assertTrue(path.exists())
        self.assertTrue(path.name.startswith("iv_history_SAVE_TEST"))
        self.assertTrue(path.suffix == ".json")

    def test_saved_json_structure(self):
        hist = _synthetic_iv_history("STRUCT", n=5)
        with self._patch_dir():
            path = save_iv_history("STRUCT", hist)
            data = json.loads(path.read_text())
        self.assertIn("symbol", data)
        self.assertIn("data_mode", data)
        self.assertIn("updated_at", data)
        self.assertIn("points", data)
        self.assertIn("iv_history", data)
        self.assertEqual(data["symbol"], "STRUCT")
        self.assertEqual(data["points"], 5)

    def test_load_returns_float_list(self):
        hist = _synthetic_iv_history("LOAD_FLOAT", n=40)
        with self._patch_dir():
            save_iv_history("LOAD_FLOAT", hist)
            values = load_iv_history("LOAD_FLOAT")
        self.assertEqual(len(values), 40)
        for v in values:
            self.assertIsInstance(v, float)
            self.assertGreater(v, 0.0)

    def test_load_order_matches_save_order(self):
        hist = _synthetic_iv_history("ORDER", n=20)
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

    def test_load_empty_history_array(self):
        import scripts.fetch_iv_history as mod
        path = Path(self._tmpdir.name) / "iv_history_EMPTY.json"
        path.write_text(json.dumps({"iv_history": []}), encoding="utf-8")
        with patch.object(mod, "IV_HISTORY_DIR", Path(self._tmpdir.name)):
            values = load_iv_history("EMPTY")
        self.assertEqual(values, [])

    def test_load_filters_zero_iv(self):
        import scripts.fetch_iv_history as mod
        hist = [{"date": "2026-01-01", "iv": 0.0},
                {"date": "2026-01-02", "iv": 0.25}]
        path = Path(self._tmpdir.name) / "iv_history_ZEROIV.json"
        path.write_text(json.dumps({"iv_history": hist}), encoding="utf-8")
        with patch.object(mod, "IV_HISTORY_DIR", Path(self._tmpdir.name)):
            values = load_iv_history("ZEROIV")
        # Zero IV entry should be excluded
        self.assertEqual(len(values), 1)
        self.assertAlmostEqual(values[0], 0.25)

    def test_symbol_uppercase_in_file(self):
        hist = _synthetic_iv_history("lower", n=5)
        with self._patch_dir():
            path = save_iv_history("lower", hist)
            data = json.loads(path.read_text())
        self.assertEqual(data["symbol"], "LOWER")


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Integrazione con compute_iv_zscore
# ─────────────────────────────────────────────────────────────────────────────

class TestIvHistoryZscoreIntegration(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _patch_dir(self):
        import scripts.fetch_iv_history as mod
        return patch.object(mod, "IV_HISTORY_DIR", Path(self._tmpdir.name))

    def test_zscore_computable_after_synthetic_fetch(self):
        hist = _synthetic_iv_history("AAPL", n=90)
        with self._patch_dir():
            save_iv_history("AAPL", hist)
            values = load_iv_history("AAPL")
        # Deve avere abbastanza punti per entrambe le finestre
        self.assertGreaterEqual(len(values), 60)
        z30 = compute_iv_zscore(values[-1], values, 30)
        z60 = compute_iv_zscore(values[-1], values, 60)
        self.assertIsNotNone(z30)
        self.assertIsNotNone(z60)
        self.assertIsInstance(z30, float)
        self.assertIsInstance(z60, float)

    def test_zscore_none_with_too_few_points(self):
        hist = _synthetic_iv_history("FEW", n=15)
        with self._patch_dir():
            save_iv_history("FEW", hist)
            values = load_iv_history("FEW")
        z30 = compute_iv_zscore(values[-1], values, 30)
        self.assertIsNone(z30)  # 15 < 30 → None

    def test_zscore_30d_ok_but_60d_none_with_35_points(self):
        hist = _synthetic_iv_history("MED", n=35)
        with self._patch_dir():
            save_iv_history("MED", hist)
            values = load_iv_history("MED")
        z30 = compute_iv_zscore(values[-1], values, 30)
        z60 = compute_iv_zscore(values[-1], values, 60)
        self.assertIsNotNone(z30)
        self.assertIsNone(z60)

    def test_iv_last_point_is_finite(self):
        hist = _synthetic_iv_history("FINITE", n=60)
        for p in hist:
            self.assertTrue(math.isfinite(p["iv"]))
            self.assertGreater(p["iv"], 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4.  CLI _run
# ─────────────────────────────────────────────────────────────────────────────

class TestCliRun(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _patch_dir(self):
        import scripts.fetch_iv_history as mod
        return patch.object(mod, "IV_HISTORY_DIR", Path(self._tmpdir.name))

    def test_synthetic_run_exit_zero(self):
        with self._patch_dir():
            code = _run(["TEST", "SPY"], days=60, synthetic=True, verbose=False)
        self.assertEqual(code, 0)

    def test_synthetic_creates_files(self):
        with self._patch_dir():
            _run(["TSLA", "AMZN"], days=60, synthetic=True, verbose=False)
            files = list(Path(self._tmpdir.name).glob("iv_history_*.json"))
        names = [f.name for f in files]
        self.assertIn("iv_history_TSLA.json", names)
        self.assertIn("iv_history_AMZN.json", names)

    def test_synthetic_run_verbose_no_crash(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with self._patch_dir():
            with redirect_stdout(buf):
                code = _run(["SPY"], days=60, synthetic=True, verbose=True)
        self.assertEqual(code, 0)
        output = buf.getvalue()
        self.assertIn("SPY", output)
        self.assertIn("[OK]", output)

    def test_symbols_forced_uppercase(self):
        with self._patch_dir():
            _run(["aapl"], days=60, synthetic=True, verbose=False)
            files = list(Path(self._tmpdir.name).glob("iv_history_*.json"))
        self.assertEqual(files[0].name, "iv_history_AAPL.json")

    def test_few_points_returns_exit_2(self):
        # Patch _synthetic_iv_history to return < MIN_POINTS_REQUIRED points
        import scripts.fetch_iv_history as mod
        with self._patch_dir():
            with patch.object(mod, "_synthetic_iv_history", return_value=[
                {"date": "2026-01-01", "iv": 0.25}
            ]):
                code = _run(["TINY"], days=5, synthetic=True, verbose=False)
        self.assertEqual(code, 2)

    def test_empty_symbol_list_returns_zero(self):
        with self._patch_dir():
            code = _run([], days=60, synthetic=True, verbose=False)
        self.assertEqual(code, 0)

    def test_multiple_symbols_all_saved(self):
        syms = ["AA", "BB", "CC"]
        with self._patch_dir():
            code = _run(syms, days=60, synthetic=True, verbose=False)
            files = {f.name for f in Path(self._tmpdir.name).glob("iv_history_*.json")}
        self.assertEqual(code, 0)
        for s in syms:
            self.assertIn(f"iv_history_{s}.json", files)


if __name__ == "__main__":
    unittest.main()
