"""
tests/test_roc7_ibkr_account_edge.py — ROC7-T2

Edge-case test suite per GET /opz/ibkr/account:
  - tag mancanti in accountSummary (nessun AccountCode, NetLiquidation, …)
  - valori non-float nei tag (es. "-", "N/A", stringa vuota, None)
  - portfolio con contratti non-OPT (STK, FUT, …)
  - portfolio item con attributi mancanti → getattr fallback
  - mix posizioni long/short
  - account_id=None quando AccountCode assente
  - risponse sempre 200 e ok=True indipendentemente dall'eccezione
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from fastapi.testclient import TestClient
from api.opz_api import app

CLIENT = TestClient(app, raise_server_exceptions=False)
ENDPOINT = "/opz/ibkr/account"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _av(tag: str, value: str) -> MagicMock:
    av = MagicMock()
    av.tag = tag
    av.value = value
    return av


def _contract(symbol="SPY", sec_type="OPT", expiry="20260417",
              strike=495.0, right="P") -> MagicMock:
    c = MagicMock()
    c.symbol = symbol
    c.secType = sec_type
    c.lastTradeDateOrContractMonth = expiry
    c.strike = strike
    c.right = right
    return c


def _portfolio_item(contract=None, position=-1.0, avg_cost=100.0,
                    market_price=110.0, market_value=-110.0,
                    unrealized_pnl=-10.0, realized_pnl=0.0) -> MagicMock:
    item = MagicMock()
    item.contract = contract or _contract()
    item.position = position
    item.averageCost = avg_cost
    item.marketPrice = market_price
    item.marketValue = market_value
    item.unrealizedPNL = unrealized_pnl
    item.realizedPNL = realized_pnl
    return item


def _connected_manager(summary: list, portfolio: list) -> MagicMock:
    ib = MagicMock()
    ib.isConnected.return_value = True
    ib.accountSummary.return_value = summary
    ib.portfolio.return_value = portfolio

    mgr = MagicMock()
    mgr.is_connected = True
    mgr._ib = ib
    return mgr


def _get(mgr) -> dict:
    with patch("execution.ibkr_connection.get_manager", return_value=mgr):
        r = CLIENT.get(ENDPOINT)
    assert r.status_code == 200
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tag mancanti in accountSummary
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingTags(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def test_empty_summary_all_null(self):
        mgr = _connected_manager(summary=[], portfolio=[])
        body = _get(mgr)
        self.assertIsNone(body["account_id"])
        self.assertIsNone(body["net_liquidation"])
        self.assertIsNone(body["realized_pnl"])
        self.assertIsNone(body["unrealized_pnl"])
        self.assertIsNone(body["buying_power"])

    def test_no_account_code_tag(self):
        summary = [
            _av("NetLiquidation", "50000"),
            _av("BuyingPower", "25000"),
        ]
        mgr = _connected_manager(summary=summary, portfolio=[])
        body = _get(mgr)
        self.assertIsNone(body["account_id"])
        self.assertAlmostEqual(body["net_liquidation"], 50000.0)

    def test_no_net_liquidation_tag(self):
        summary = [_av("AccountCode", "DU999")]
        mgr = _connected_manager(summary=summary, portfolio=[])
        body = _get(mgr)
        self.assertEqual(body["account_id"], "DU999")
        self.assertIsNone(body["net_liquidation"])

    def test_partial_tags_ok_true(self):
        summary = [_av("RealizedPnL", "500"), _av("UnrealizedPnL", "-200")]
        mgr = _connected_manager(summary=summary, portfolio=[])
        body = _get(mgr)
        self.assertTrue(body["ok"])
        self.assertAlmostEqual(body["realized_pnl"], 500.0)
        self.assertAlmostEqual(body["unrealized_pnl"], -200.0)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Valori non-float nei tag
# ─────────────────────────────────────────────────────────────────────────────

class TestNonFloatTagValues(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def _body_with_net_liq(self, value: str) -> dict:
        summary = [
            _av("AccountCode", "DU123"),
            _av("NetLiquidation", value),
        ]
        mgr = _connected_manager(summary=summary, portfolio=[])
        return _get(mgr)

    def test_dash_returns_null(self):
        """IBKR restituisce '-' quando il valore non è disponibile."""
        body = self._body_with_net_liq("-")
        self.assertIsNone(body["net_liquidation"])

    def test_na_returns_null(self):
        body = self._body_with_net_liq("N/A")
        self.assertIsNone(body["net_liquidation"])

    def test_empty_string_returns_null(self):
        body = self._body_with_net_liq("")
        self.assertIsNone(body["net_liquidation"])

    def test_valid_float_string_parsed(self):
        body = self._body_with_net_liq("75000.50")
        self.assertAlmostEqual(body["net_liquidation"], 75000.50)

    def test_negative_float_string_parsed(self):
        body = self._body_with_net_liq("-1200.00")
        self.assertAlmostEqual(body["net_liquidation"], -1200.00)

    def test_ok_true_on_bad_float(self):
        body = self._body_with_net_liq("NOTANUMBER")
        self.assertTrue(body["ok"])
        self.assertIsNone(body["net_liquidation"])


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tipi contratto diversi da OPT
# ─────────────────────────────────────────────────────────────────────────────

class TestNonOptContracts(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def _body_with_contract(self, sec_type: str) -> dict:
        summary = [_av("AccountCode", "DU123"), _av("NetLiquidation", "10000")]
        item = _portfolio_item(contract=_contract(sec_type=sec_type, strike=None, right=None))
        mgr = _connected_manager(summary=summary, portfolio=[item])
        return _get(mgr)

    def test_stk_contract(self):
        body = self._body_with_contract("STK")
        self.assertEqual(len(body["positions"]), 1)
        self.assertEqual(body["positions"][0]["sec_type"], "STK")

    def test_fut_contract(self):
        body = self._body_with_contract("FUT")
        self.assertEqual(body["positions"][0]["sec_type"], "FUT")

    def test_etf_contract(self):
        body = self._body_with_contract("ETF")
        self.assertEqual(body["positions"][0]["sec_type"], "ETF")

    def test_positions_have_required_keys_for_any_type(self):
        body = self._body_with_contract("STK")
        pos = body["positions"][0]
        for key in ("symbol", "sec_type", "expiry", "strike", "right",
                    "quantity", "avg_cost", "market_price", "market_value",
                    "unrealized_pnl", "realized_pnl"):
            self.assertIn(key, pos)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Mix posizioni long/short
# ─────────────────────────────────────────────────────────────────────────────

class TestLongShortMix(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def test_long_position_positive_quantity(self):
        summary = [_av("AccountCode", "DU1")]
        item = _portfolio_item(position=+2.0)
        mgr = _connected_manager(summary=summary, portfolio=[item])
        body = _get(mgr)
        self.assertGreater(body["positions"][0]["quantity"], 0)

    def test_short_position_negative_quantity(self):
        summary = [_av("AccountCode", "DU1")]
        item = _portfolio_item(position=-3.0)
        mgr = _connected_manager(summary=summary, portfolio=[item])
        body = _get(mgr)
        self.assertLess(body["positions"][0]["quantity"], 0)

    def test_mixed_pnl_signs(self):
        summary = [_av("AccountCode", "DU1")]
        items = [
            _portfolio_item(position=-1.0, unrealized_pnl=+50.0),
            _portfolio_item(position=+2.0, unrealized_pnl=-30.0),
        ]
        mgr = _connected_manager(summary=summary, portfolio=items)
        body = _get(mgr)
        upnls = [p["unrealized_pnl"] for p in body["positions"]]
        self.assertTrue(any(v > 0 for v in upnls))
        self.assertTrue(any(v < 0 for v in upnls))

    def test_two_positions_count(self):
        summary = [_av("AccountCode", "DU1")]
        items = [_portfolio_item(), _portfolio_item()]
        mgr = _connected_manager(summary=summary, portfolio=items)
        body = _get(mgr)
        self.assertEqual(len(body["positions"]), 2)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Messaggi
# ─────────────────────────────────────────────────────────────────────────────

class TestAccountMessages(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def test_message_zero_positions(self):
        summary = [_av("AccountCode", "DU42")]
        mgr = _connected_manager(summary=summary, portfolio=[])
        body = _get(mgr)
        self.assertIn("0", body["message"])

    def test_message_with_positions(self):
        summary = [_av("AccountCode", "DU42")]
        mgr = _connected_manager(
            summary=summary,
            portfolio=[_portfolio_item(), _portfolio_item(), _portfolio_item()],
        )
        body = _get(mgr)
        self.assertIn("3", body["message"])

    def test_disconnected_message_has_endpoint_hint(self):
        """Messaggio disconnesso deve suggerire il path per connettersi."""
        mgr = MagicMock()
        mgr.is_connected = False
        with patch("execution.ibkr_connection.get_manager", return_value=mgr):
            body = CLIENT.get(ENDPOINT).json()
        # Il messaggio deve contenere un riferimento a status o try_connect
        msg = body["message"].lower()
        self.assertTrue("status" in msg or "try_connect" in msg or "connett" in msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
