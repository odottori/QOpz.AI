"""
tests/test_roc6_ibkr_account.py — ROC6-T4

Test suite per GET /opz/ibkr/account:
  - struttura risposta corretta (ok, connected, source_system, account_id,
    net_liquidation, realized_pnl, unrealized_pnl, buying_power, positions, message)
  - quando non connesso → ok=True, connected=False, dati null, positions=[]
  - quando connesso → dati da accountSummary() + portfolio()
  - positions: struttura corretta (symbol, sec_type, expiry, strike, right,
    quantity, avg_cost, market_price, market_value, unrealized_pnl, realized_pnl)
  - quando ib.accountSummary() lancia eccezione → ok=True, connected=True, dati null
  - message sempre stringa non vuota
  - source_system="ibkr_live" quando connesso, "yfinance" quando non connesso
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

os.environ.setdefault("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

from fastapi.testclient import TestClient
from api.opz_api import app

CLIENT = TestClient(app, raise_server_exceptions=False)

ENDPOINT = "/opz/ibkr/account"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_account_value(tag: str, value: str, account: str = "DU123456") -> MagicMock:
    av = MagicMock()
    av.tag = tag
    av.value = value
    av.account = account
    return av


def _make_portfolio_item(
    symbol: str = "SPY",
    sec_type: str = "OPT",
    expiry: str = "20260417",
    strike: float = 495.0,
    right: str = "P",
    position: float = -1.0,
    avg_cost: float = 180.0,
    market_price: float = 200.0,
    market_value: float = -200.0,
    unrealized_pnl: float = -20.0,
    realized_pnl: float = 0.0,
) -> MagicMock:
    contract = MagicMock()
    contract.symbol = symbol
    contract.secType = sec_type
    contract.lastTradeDateOrContractMonth = expiry
    contract.strike = strike
    contract.right = right

    item = MagicMock()
    item.contract = contract
    item.position = position
    item.averageCost = avg_cost
    item.marketPrice = market_price
    item.marketValue = market_value
    item.unrealizedPNL = unrealized_pnl
    item.realizedPNL = realized_pnl
    return item


def _make_connected_manager(
    account_id: str = "DU123456",
    net_liq: float = 50000.0,
    realized: float = 1200.0,
    unrealized: float = -350.0,
    buying_power: float = 25000.0,
    portfolio_items: list | None = None,
) -> MagicMock:
    if portfolio_items is None:
        portfolio_items = [_make_portfolio_item()]

    ib = MagicMock()
    ib.isConnected.return_value = True
    ib.accountSummary.return_value = [
        _make_account_value("AccountCode", account_id),
        _make_account_value("NetLiquidation", str(net_liq)),
        _make_account_value("RealizedPnL", str(realized)),
        _make_account_value("UnrealizedPnL", str(unrealized)),
        _make_account_value("BuyingPower", str(buying_power)),
    ]
    ib.portfolio.return_value = portfolio_items

    mgr = MagicMock()
    mgr.is_connected = True
    mgr._ib = ib
    return mgr


def _make_disconnected_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.is_connected = False
    return mgr


# ─────────────────────────────────────────────────────────────────────────────
# 1. Stato non connesso
# ─────────────────────────────────────────────────────────────────────────────

class TestIbkrAccountDisconnected(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def _get(self):
        mgr = _make_disconnected_manager()
        with patch("execution.ibkr_connection.get_manager", return_value=mgr):
            return CLIENT.get(ENDPOINT)

    def test_status_200(self):
        self.assertEqual(self._get().status_code, 200)

    def test_ok_true(self):
        self.assertTrue(self._get().json()["ok"])

    def test_connected_false(self):
        self.assertFalse(self._get().json()["connected"])

    def test_source_system_yfinance(self):
        self.assertEqual(self._get().json()["source_system"], "yfinance")

    def test_account_id_null(self):
        self.assertIsNone(self._get().json()["account_id"])

    def test_net_liquidation_null(self):
        self.assertIsNone(self._get().json()["net_liquidation"])

    def test_realized_pnl_null(self):
        self.assertIsNone(self._get().json()["realized_pnl"])

    def test_unrealized_pnl_null(self):
        self.assertIsNone(self._get().json()["unrealized_pnl"])

    def test_buying_power_null(self):
        self.assertIsNone(self._get().json()["buying_power"])

    def test_positions_empty_list(self):
        body = self._get().json()
        self.assertIsInstance(body["positions"], list)
        self.assertEqual(len(body["positions"]), 0)

    def test_message_nonempty(self):
        msg = self._get().json()["message"]
        self.assertIsInstance(msg, str)
        self.assertGreater(len(msg), 0)

    def test_message_mentions_not_connected(self):
        msg = self._get().json()["message"].lower()
        # dovrebbe menzionare "non connesso" o simile
        self.assertTrue("non connesso" in msg or "not connected" in msg or "connett" in msg)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Struttura risposta (chiavi obbligatorie)
# ─────────────────────────────────────────────────────────────────────────────

class TestIbkrAccountStructure(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def _get_disconnected(self):
        mgr = _make_disconnected_manager()
        with patch("execution.ibkr_connection.get_manager", return_value=mgr):
            return CLIENT.get(ENDPOINT)

    def _get_connected(self):
        mgr = _make_connected_manager()
        with patch("execution.ibkr_connection.get_manager", return_value=mgr):
            return CLIENT.get(ENDPOINT)

    def test_required_keys_disconnected(self):
        body = self._get_disconnected().json()
        for key in ("ok", "connected", "source_system", "account_id",
                    "net_liquidation", "realized_pnl", "unrealized_pnl",
                    "buying_power", "positions", "message"):
            self.assertIn(key, body, f"Chiave mancante: {key}")

    def test_required_keys_connected(self):
        body = self._get_connected().json()
        for key in ("ok", "connected", "source_system", "account_id",
                    "net_liquidation", "realized_pnl", "unrealized_pnl",
                    "buying_power", "positions", "message"):
            self.assertIn(key, body, f"Chiave mancante: {key}")

    def test_positions_is_list(self):
        body = self._get_connected().json()
        self.assertIsInstance(body["positions"], list)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Stato connesso — valori account
# ─────────────────────────────────────────────────────────────────────────────

class TestIbkrAccountConnected(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def _get(self, **kwargs):
        mgr = _make_connected_manager(**kwargs)
        with patch("execution.ibkr_connection.get_manager", return_value=mgr):
            return CLIENT.get(ENDPOINT)

    def test_connected_true(self):
        self.assertTrue(self._get().json()["connected"])

    def test_source_system_ibkr_live(self):
        self.assertEqual(self._get().json()["source_system"], "ibkr_live")

    def test_account_id_returned(self):
        body = self._get(account_id="DU999888").json()
        self.assertEqual(body["account_id"], "DU999888")

    def test_net_liquidation_returned(self):
        body = self._get(net_liq=75000.0).json()
        self.assertAlmostEqual(body["net_liquidation"], 75000.0)

    def test_realized_pnl_returned(self):
        body = self._get(realized=500.0).json()
        self.assertAlmostEqual(body["realized_pnl"], 500.0)

    def test_unrealized_pnl_returned(self):
        body = self._get(unrealized=-200.0).json()
        self.assertAlmostEqual(body["unrealized_pnl"], -200.0)

    def test_buying_power_returned(self):
        body = self._get(buying_power=30000.0).json()
        self.assertAlmostEqual(body["buying_power"], 30000.0)

    def test_message_mentions_account_id(self):
        body = self._get(account_id="DU123456").json()
        self.assertIn("DU123456", body["message"])

    def test_message_mentions_position_count(self):
        items = [_make_portfolio_item("SPY"), _make_portfolio_item("QQQ")]
        body = self._get(portfolio_items=items).json()
        self.assertIn("2", body["message"])

    def test_ok_true_when_connected(self):
        self.assertTrue(self._get().json()["ok"])


# ─────────────────────────────────────────────────────────────────────────────
# 4. Struttura posizioni
# ─────────────────────────────────────────────────────────────────────────────

class TestIbkrAccountPositions(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def _get_with_position(self, **kwargs):
        item = _make_portfolio_item(**kwargs)
        mgr = _make_connected_manager(portfolio_items=[item])
        with patch("execution.ibkr_connection.get_manager", return_value=mgr):
            return CLIENT.get(ENDPOINT).json()["positions"][0]

    def test_position_symbol(self):
        pos = self._get_with_position(symbol="AAPL")
        self.assertEqual(pos["symbol"], "AAPL")

    def test_position_sec_type(self):
        pos = self._get_with_position(sec_type="OPT")
        self.assertEqual(pos["sec_type"], "OPT")

    def test_position_expiry(self):
        pos = self._get_with_position(expiry="20261219")
        self.assertEqual(pos["expiry"], "20261219")

    def test_position_strike(self):
        pos = self._get_with_position(strike=450.0)
        self.assertAlmostEqual(pos["strike"], 450.0)

    def test_position_right(self):
        pos = self._get_with_position(right="C")
        self.assertEqual(pos["right"], "C")

    def test_position_quantity(self):
        pos = self._get_with_position(position=-2.0)
        self.assertAlmostEqual(pos["quantity"], -2.0)

    def test_position_keys_complete(self):
        pos = self._get_with_position()
        for key in ("symbol", "sec_type", "expiry", "strike", "right",
                    "quantity", "avg_cost", "market_price", "market_value",
                    "unrealized_pnl", "realized_pnl"):
            self.assertIn(key, pos, f"Chiave posizione mancante: {key}")

    def test_no_positions_empty_list(self):
        mgr = _make_connected_manager(portfolio_items=[])
        with patch("execution.ibkr_connection.get_manager", return_value=mgr):
            body = CLIENT.get(ENDPOINT).json()
        self.assertEqual(body["positions"], [])

    def test_multiple_positions(self):
        items = [
            _make_portfolio_item("SPY"),
            _make_portfolio_item("QQQ"),
            _make_portfolio_item("IWM"),
        ]
        mgr = _make_connected_manager(portfolio_items=items)
        with patch("execution.ibkr_connection.get_manager", return_value=mgr):
            body = CLIENT.get(ENDPOINT).json()
        self.assertEqual(len(body["positions"]), 3)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Fallback su eccezione IB
# ─────────────────────────────────────────────────────────────────────────────

class TestIbkrAccountFetchError(unittest.TestCase):

    def setUp(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def tearDown(self):
        from execution.ibkr_connection import reset_manager
        reset_manager()

    def _get_with_error(self):
        ib = MagicMock()
        ib.isConnected.return_value = True
        ib.accountSummary.side_effect = RuntimeError("IB disconnected mid-fetch")

        mgr = MagicMock()
        mgr.is_connected = True
        mgr._ib = ib

        with patch("execution.ibkr_connection.get_manager", return_value=mgr):
            return CLIENT.get(ENDPOINT)

    def test_ok_true_on_error(self):
        self.assertTrue(self._get_with_error().json()["ok"])

    def test_connected_true_on_error(self):
        """connected riflette stato connessione, non fetch success."""
        self.assertTrue(self._get_with_error().json()["connected"])

    def test_source_system_ibkr_live_on_error(self):
        self.assertEqual(self._get_with_error().json()["source_system"], "ibkr_live")

    def test_net_liquidation_null_on_error(self):
        self.assertIsNone(self._get_with_error().json()["net_liquidation"])

    def test_positions_empty_on_error(self):
        body = self._get_with_error().json()
        self.assertIsInstance(body["positions"], list)
        self.assertEqual(len(body["positions"]), 0)

    def test_message_nonempty_on_error(self):
        msg = self._get_with_error().json()["message"]
        self.assertIsInstance(msg, str)
        self.assertGreater(len(msg), 0)

    def test_status_200_on_error(self):
        self.assertEqual(self._get_with_error().status_code, 200)

    def test_ib_none_returns_gracefully(self):
        """Se _ib è None → deve gestirlo senza crash."""
        mgr = MagicMock()
        mgr.is_connected = True
        mgr._ib = None

        with patch("execution.ibkr_connection.get_manager", return_value=mgr):
            r = CLIENT.get(ENDPOINT)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
