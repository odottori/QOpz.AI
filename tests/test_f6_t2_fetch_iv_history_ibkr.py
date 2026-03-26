import sys
import types
import unittest
from unittest.mock import patch

from scripts.fetch_iv_history_ibkr import _snapshot_on_connection


class _FakeStock:
    def __init__(self, symbol: str, exchange: str, currency: str):
        self.symbol = symbol
        self.exchange = exchange
        self.currency = currency
        self.secType = "STK"
        self.conId = 101


class _FakeOption:
    def __init__(self, *args, **kwargs):
        self.right = kwargs.get("right")


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


if __name__ == "__main__":
    unittest.main()
