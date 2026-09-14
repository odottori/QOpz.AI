import sys
import types
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from scripts.fetch_iv_history_ibkr import (
    _ibkr_connection_params,
    _estimate_sigma_bands,
    _select_regular_expiries,
    _snapshot_on_connection,
)


class _FakeStock:
    def __init__(self, symbol: str, exchange: str, currency: str):
        self.symbol = symbol
        self.exchange = exchange
        self.currency = currency
        self.secType = "STK"
        self.conId = 101


class _FakeOption:
    def __init__(self, *args, **kwargs):
        self.symbol = args[0] if len(args) > 0 else kwargs.get("symbol")
        self.lastTradeDateOrContractMonth = args[1] if len(args) > 1 else kwargs.get("lastTradeDateOrContractMonth")
        self.strike = args[2] if len(args) > 2 else kwargs.get("strike")
        self.right = args[3] if len(args) > 3 else kwargs.get("right")
        self.exchange = args[4] if len(args) > 4 else kwargs.get("exchange")
        self.currency = kwargs.get("currency", "USD")


class _FakeTicker:
    def __init__(self, last=None, close=None, bid=None, ask=None):
        self.last = last
        self.close = close
        self.bid = bid
        self.ask = ask


class _FakeIb:
    def __init__(self):
        self._mdt = None
        self.requested_types = []

    def qualifyContracts(self, *contracts):
        return list(contracts)

    def reqMarketDataType(self, mdt: int):
        self._mdt = mdt
        self.requested_types.append(mdt)

    def reqMktData(self, contract, genericTickList, snapshot, regulatorySnapshot):
        if self._mdt == 3:
            return _FakeTicker(close=432.1)
        return _FakeTicker()

    def sleep(self, _seconds: float):
        return None

    def cancelMktData(self, _contract):
        return None

    def reqSecDefOptParams(self, *_args, **_kwargs):
        return []


class _FakeChain:
    def __init__(self):
        self.exchange = "SMART"
        self.expirations = {(date.today() + timedelta(days=30)).strftime("%Y%m%d")}
        self.strikes = [432.0]


class _FakeIbWithChain(_FakeIb):
    def reqMktData(self, contract, genericTickList, snapshot, regulatorySnapshot):
        if getattr(contract, "secType", "") == "STK":
            if self._mdt == 3:
                return _FakeTicker(close=432.1)
            return _FakeTicker()
        return _FakeTicker()

    def reqSecDefOptParams(self, *_args, **_kwargs):
        return [_FakeChain()]


class TestF6T2FetchIvHistoryIbkr(unittest.TestCase):
    def test_underlying_fallback_uses_delayed_when_live_unavailable(self):
        fake_module = types.SimpleNamespace(Stock=_FakeStock, Option=_FakeOption)
        fake_ib = _FakeIb()
        with patch.dict(sys.modules, {"ib_insync": fake_module}):
            out = _snapshot_on_connection(fake_ib, "SPY")

        self.assertEqual(out.get("market_data_type"), 3)
        self.assertEqual(out.get("underlying_price"), 432.1)
        self.assertIn("nessuna catena opzioni", str(out.get("error")))
        self.assertEqual(fake_ib.requested_types, [1, 3])
        self.assertEqual(getattr(fake_ib, "_qopz_market_data_type", None), 3)

    def test_underlying_uses_cached_market_data_type_first(self):
        fake_module = types.SimpleNamespace(Stock=_FakeStock, Option=_FakeOption)
        fake_ib = _FakeIb()
        fake_ib._qopz_market_data_type = 3
        with patch.dict(sys.modules, {"ib_insync": fake_module}):
            out = _snapshot_on_connection(fake_ib, "QQQ")

        self.assertEqual(out.get("market_data_type"), 3)
        self.assertEqual(fake_ib.requested_types, [3])

    def test_pre_market_error_label_when_iv_missing_before_open(self):
        fake_module = types.SimpleNamespace(Stock=_FakeStock, Option=_FakeOption)
        fake_ib = _FakeIbWithChain()
        with patch.dict(sys.modules, {"ib_insync": fake_module}):
            with patch("scripts.fetch_iv_history_ibkr._market_phase_ny", return_value="pre"):
                out = _snapshot_on_connection(fake_ib, "AAPL")

        self.assertEqual(out.get("market_data_type"), 3)
        self.assertIn("PRE-MKT", str(out.get("error")))

    def test_select_regular_expiries_prefers_near_20th(self):
        today = date(2026, 3, 1)
        expiries = ["20260306", "20260320", "20260417", "20260522", "20260619"]
        out = _select_regular_expiries(expiries, max_candidates=5, today_ref=today)
        chosen = [x[0] for x in out]
        self.assertIn("20260320", chosen)
        self.assertIn("20260417", chosen)
        self.assertIn("20260522", chosen)
        self.assertIn("20260619", chosen)
        self.assertNotIn("20260306", chosen)

    def test_select_regular_expiries_fallback_when_no_regular(self):
        today = date(2026, 3, 1)
        expiries = ["20260310", "20260313"]
        out = _select_regular_expiries(expiries, max_candidates=5, today_ref=today)
        chosen = [x[0] for x in out]
        self.assertEqual(chosen, ["20260310", "20260313"])

    def test_estimate_sigma_bands_returns_1_and_2_sigma(self):
        bands = _estimate_sigma_bands(100.0, 0.20, 30)
        self.assertAlmostEqual(float(bands["sigma_1_abs"]), 5.735, places=2)
        self.assertAlmostEqual(float(bands["sigma_2_abs"]), 11.47, places=2)
        self.assertAlmostEqual(float(bands["sigma_1_up"]), 105.735, places=2)
        self.assertAlmostEqual(float(bands["sigma_1_down"]), 94.265, places=2)

    def test_ibkr_connection_params_prefers_manager_connection(self):
        class _Mgr:
            def try_connect(self, timeout=1.5):
                return True

            def connection_info(self):
                return {
                    "connected": True,
                    "host": "127.0.0.1",
                    "port": 7496,
                    "client_id": 10,
                }

        with patch.dict(sys.modules, {"execution.ibkr_connection": types.SimpleNamespace(get_manager=lambda: _Mgr(), IBKR_CLIENT_ID=10)}):
            with patch.dict("os.environ", {}, clear=False):
                host, ports, client_id = _ibkr_connection_params(profile="paper")

        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(ports[0], 7496)
        self.assertEqual(client_id, 11)

    def test_ibkr_connection_params_uses_profile_client_id_when_manager_off(self):
        class _Mgr:
            def try_connect(self, timeout=1.5):
                return False

            def connection_info(self):
                return {
                    "connected": False,
                    "host": "127.0.0.1",
                    "port": None,
                    "client_id": 10,
                }

        fake_cfg = {"broker": {"port": 7497, "client_id": 7}}
        with patch.dict(sys.modules, {"execution.ibkr_connection": types.SimpleNamespace(get_manager=lambda: _Mgr(), IBKR_CLIENT_ID=10)}):
            with patch("execution.config_loader.load_profile_config", return_value=fake_cfg):
                with patch.dict("os.environ", {}, clear=False):
                    host, ports, client_id = _ibkr_connection_params(profile="paper")

        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(ports[0], 7497)
        self.assertEqual(client_id, 7)


if __name__ == "__main__":
    unittest.main()
