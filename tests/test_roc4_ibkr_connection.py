"""
tests/test_roc4_ibkr_connection.py — ROC4-T2

Test suite per execution/ibkr_connection.py:
  - IBKRConnectionManager: try_connect, is_connected, disconnect, context manager
  - get_events_for_symbol: fallback yfinance quando non connesso
  - get_events_for_symbol: path IBKR quando connesso (mock)
  - get_manager: singleton thread-safe
  - Integration: scan_opportunities usa IBKR se connesso

Nessuna connessione reale: tutto via mock.
"""
from __future__ import annotations

import threading
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from execution.ibkr_connection import (
    IBKRConnectionManager,
    IBKRStatus,
    _probe_port,
    get_manager,
    reset_manager,
    IBKR_PORTS,
    IBKR_HOST,
    IBKR_CLIENT_ID,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_event_result(symbol="TEST", block=False, earnings_flag=None, dividend_flag=None):
    """Crea EventCheckResult minimale per test."""
    from scripts.events_calendar import EventCheckResult
    return EventCheckResult(
        symbol=symbol,
        as_of_date=date.today(),
        earnings_date=None,
        dividend_date=None,
        days_to_earnings=None,
        days_to_dividend=None,
        earnings_flag=earnings_flag,
        dividend_flag=dividend_flag,
        block_trade=block,
        restrict_long_gamma=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Probe porta TCP
# ─────────────────────────────────────────────────────────────────────────────

class TestProbePort(unittest.TestCase):

    def test_probe_closed_port_returns_false(self):
        # Porta 1 è sempre chiusa su qualsiasi OS moderno senza root
        result = _probe_port("127.0.0.1", 1, timeout=0.3)
        self.assertFalse(result)

    def test_probe_unreachable_host_returns_false(self):
        # 192.0.2.x è TEST-NET, non raggiungibile
        result = _probe_port("192.0.2.99", 7497, timeout=0.3)
        self.assertFalse(result)


# ─────────────────────────────────────────────────────────────────────────────
# 2. IBKRConnectionManager — try_connect
# ─────────────────────────────────────────────────────────────────────────────

class TestIBKRConnectionManagerConnect(unittest.TestCase):

    def setUp(self):
        reset_manager()

    def tearDown(self):
        reset_manager()

    def test_is_connected_false_by_default(self):
        mgr = IBKRConnectionManager()
        self.assertFalse(mgr.is_connected)

    def test_try_connect_no_tws_returns_false(self):
        """Quando nessuna porta risponde → False, nessuna eccezione."""
        mgr = IBKRConnectionManager(ports=[1, 2, 3])  # porte chiuse
        result = mgr.try_connect(timeout=0.2)
        self.assertFalse(result)
        self.assertFalse(mgr.is_connected)

    def test_try_connect_port_order_4004_first(self):
        """Il primo elemento di IBKR_PORTS è 4004 (socat -> IBG Docker)."""
        self.assertEqual(IBKR_PORTS[0], 4004)

    def test_try_connect_timeout_graceful(self):
        """Timeout breve → ritorna False senza eccezione."""
        mgr = IBKRConnectionManager(ports=[9997, 9998, 9999])
        try:
            result = mgr.try_connect(timeout=0.1)
        except Exception as exc:
            self.fail(f"try_connect raised unexpectedly: {exc}")
        self.assertFalse(result)

    def test_try_connect_mocked_success(self):
        """Con IB mock connesso → try_connect ritorna True."""
        mgr = IBKRConnectionManager(ports=[7497])

        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True

        with patch("execution.ibkr_connection._probe_port", return_value=True), \
             patch.object(mgr, "_get_or_create_ib", return_value=mock_ib):
            result = mgr.try_connect()

        self.assertTrue(result)
        self.assertTrue(mgr.is_connected)
        self.assertEqual(mgr._active_port, 7497)

    def test_try_connect_ib_raises_still_false(self):
        """Se IB().connect() solleva eccezione → is_connected=False, no propagazione."""
        mgr = IBKRConnectionManager(ports=[7497])

        mock_ib = MagicMock()
        mock_ib.connect.side_effect = ConnectionRefusedError("refused")
        mock_ib.isConnected.return_value = False

        with patch("execution.ibkr_connection._probe_port", return_value=True), \
             patch.object(mgr, "_get_or_create_ib", return_value=mock_ib):
            result = mgr.try_connect()

        self.assertFalse(result)
        self.assertFalse(mgr.is_connected)

    def test_try_connect_second_port_used_when_first_fails(self):
        """Se prima porta non risponde al probe → prova seconda."""
        mgr = IBKRConnectionManager(ports=[7497, 4002])

        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True

        # Prima porta: probe fallisce; seconda: probe OK
        def probe_side(host, port, timeout=2.0):
            return port == 4002

        with patch("execution.ibkr_connection._probe_port", side_effect=probe_side), \
             patch.object(mgr, "_get_or_create_ib", return_value=mock_ib):
            result = mgr.try_connect()

        self.assertTrue(result)
        self.assertEqual(mgr._active_port, 4002)


# ─────────────────────────────────────────────────────────────────────────────
# 3. IBKRConnectionManager — disconnect + context manager
# ─────────────────────────────────────────────────────────────────────────────

class TestIBKRConnectionManagerDisconnect(unittest.TestCase):

    def setUp(self):
        reset_manager()

    def tearDown(self):
        reset_manager()

    def test_disconnect_when_not_connected_safe(self):
        """disconnect() su manager non connesso non solleva eccezioni."""
        mgr = IBKRConnectionManager()
        try:
            mgr.disconnect()
        except Exception as exc:
            self.fail(f"disconnect raised: {exc}")
        self.assertFalse(mgr.is_connected)

    def test_disconnect_resets_state(self):
        """Dopo disconnect, is_connected=False e active_port=None."""
        mgr = IBKRConnectionManager(ports=[7497])
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True

        with patch("execution.ibkr_connection._probe_port", return_value=True), \
             patch.object(mgr, "_get_or_create_ib", return_value=mock_ib):
            mgr.try_connect()

        # Ora simula disconnect
        mock_ib.isConnected.return_value = False
        mgr.disconnect()

        self.assertFalse(mgr.is_connected)
        self.assertIsNone(mgr._active_port)

    def test_context_manager_disconnects_on_exit(self):
        """With statement → disconnect chiamato all'uscita."""
        mgr = IBKRConnectionManager(ports=[9997])  # porta chiusa → non connette

        with mgr as m:
            self.assertIs(m, mgr)

        # Deve essere sicuro dopo l'uscita
        self.assertFalse(mgr.is_connected)

    def test_context_manager_connects_on_enter(self):
        """With statement → try_connect() chiamato all'entrata."""
        mgr = IBKRConnectionManager(ports=[7497])
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True

        with patch("execution.ibkr_connection._probe_port", return_value=True), \
             patch.object(mgr, "_get_or_create_ib", return_value=mock_ib):
            with mgr as m:
                self.assertTrue(m.is_connected)


# ─────────────────────────────────────────────────────────────────────────────
# 4. IBKRConnectionManager — connection_info + status
# ─────────────────────────────────────────────────────────────────────────────

class TestIBKRConnectionManagerInfo(unittest.TestCase):

    def test_connection_info_returns_dict(self):
        mgr = IBKRConnectionManager()
        info = mgr.connection_info()
        self.assertIsInstance(info, dict)
        for key in ("connected", "host", "port", "client_id", "source_system", "connected_at"):
            self.assertIn(key, info)

    def test_connection_info_disconnected_state(self):
        mgr = IBKRConnectionManager()
        info = mgr.connection_info()
        self.assertFalse(info["connected"])
        self.assertEqual(info["source_system"], "yfinance")
        self.assertIsNone(info["port"])

    def test_source_system_yfinance_when_not_connected(self):
        mgr = IBKRConnectionManager()
        self.assertEqual(mgr.source_system, "yfinance")

    def test_source_system_ibkr_live_when_connected(self):
        mgr = IBKRConnectionManager(ports=[7497])
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True

        with patch("execution.ibkr_connection._probe_port", return_value=True), \
             patch.object(mgr, "_get_or_create_ib", return_value=mock_ib):
            mgr.try_connect()

        self.assertEqual(mgr.source_system, "ibkr_live")

    def test_status_returns_ibkr_status(self):
        mgr = IBKRConnectionManager()
        s = mgr.status()
        self.assertIsInstance(s, IBKRStatus)
        self.assertFalse(s.connected)
        self.assertEqual(s.source_system, "yfinance")

    def test_connected_at_set_on_connect(self):
        mgr = IBKRConnectionManager(ports=[7497])
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True

        with patch("execution.ibkr_connection._probe_port", return_value=True), \
             patch.object(mgr, "_get_or_create_ib", return_value=mock_ib):
            mgr.try_connect()

        self.assertIsNotNone(mgr._connected_at)
        # Deve essere un ISO timestamp
        from datetime import datetime
        datetime.fromisoformat(mgr._connected_at)  # non solleva se formato corretto


# ─────────────────────────────────────────────────────────────────────────────
# 5. get_events_for_symbol — fallback yfinance
# ─────────────────────────────────────────────────────────────────────────────

class TestIBKRGetEventsYFinanceFallback(unittest.TestCase):

    def setUp(self):
        reset_manager()

    def tearDown(self):
        reset_manager()

    def test_get_events_falls_back_yfinance_when_disconnected(self):
        """Se non connesso → usa yfinance (check_events mock)."""
        mgr = IBKRConnectionManager(ports=[9997])
        ev_expected = _make_event_result("AAPL")

        with patch("scripts.events_calendar.check_events", return_value=ev_expected) as mock_yf:
            ev = mgr.get_events_for_symbol("AAPL")

        self.assertEqual(ev.symbol, "AAPL")
        mock_yf.assert_called_once_with("AAPL")

    def test_get_events_yfinance_error_returns_empty_result(self):
        """Se yfinance fallisce → EventCheckResult vuoto con block=False."""
        mgr = IBKRConnectionManager(ports=[9997])

        with patch("scripts.events_calendar.check_events", side_effect=RuntimeError("yf fail")):
            ev = mgr.get_events_for_symbol("MSFT")

        self.assertEqual(ev.symbol, "MSFT")
        self.assertFalse(ev.block_trade)
        self.assertIsNone(ev.earnings_flag)
        self.assertIsNone(ev.dividend_flag)

    def test_get_events_returns_event_check_result(self):
        """Il ritorno è sempre un EventCheckResult."""
        from scripts.events_calendar import EventCheckResult
        mgr = IBKRConnectionManager(ports=[9997])

        with patch("scripts.events_calendar.check_events", return_value=_make_event_result("SPY")):
            ev = mgr.get_events_for_symbol("SPY")

        self.assertIsInstance(ev, EventCheckResult)


# ─────────────────────────────────────────────────────────────────────────────
# 6. get_events_for_symbol — path IBKR (mock connessione)
# ─────────────────────────────────────────────────────────────────────────────

class TestIBKRGetEventsConnected(unittest.TestCase):

    def setUp(self):
        reset_manager()

    def tearDown(self):
        reset_manager()

    def _make_connected_manager(self) -> IBKRConnectionManager:
        mgr = IBKRConnectionManager(ports=[7497])
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True

        with patch("execution.ibkr_connection._probe_port", return_value=True), \
             patch.object(mgr, "_get_or_create_ib", return_value=mock_ib):
            mgr.try_connect()

        mgr._ib = mock_ib
        return mgr

    def test_get_events_uses_ibkr_when_connected(self):
        """Se connesso → tenta _fetch_events_ibkr, non chiama yfinance direttamente."""
        mgr = self._make_connected_manager()
        ev_ibkr = _make_event_result("AAPL", earnings_flag="EARNINGS_7D")

        with patch.object(mgr, "_fetch_events_ibkr", return_value=ev_ibkr) as mock_ibkr, \
             patch("scripts.events_calendar.check_events") as mock_yf:
            ev = mgr.get_events_for_symbol("AAPL")

        mock_ibkr.assert_called_once_with("AAPL")
        mock_yf.assert_not_called()
        self.assertEqual(ev.earnings_flag, "EARNINGS_7D")

    def test_get_events_ibkr_falls_back_yfinance_on_error(self):
        """Se _fetch_events_ibkr solleva → fallback yfinance."""
        mgr = self._make_connected_manager()
        ev_yf = _make_event_result("TSLA")

        with patch.object(mgr, "_fetch_events_ibkr", side_effect=RuntimeError("IB XML error")), \
             patch("scripts.events_calendar.check_events", return_value=ev_yf):
            ev = mgr.get_events_for_symbol("TSLA")

        self.assertEqual(ev.symbol, "TSLA")


# ─────────────────────────────────────────────────────────────────────────────
# 7. XML parsing (unit test interni)
# ─────────────────────────────────────────────────────────────────────────────

class TestIBKRXMLParsing(unittest.TestCase):

    def setUp(self):
        reset_manager()

    def tearDown(self):
        reset_manager()

    def _mgr(self):
        return IBKRConnectionManager()

    def test_parse_earnings_from_xml_future_date(self):
        from datetime import date, timedelta
        today = date.today()
        future = (today + timedelta(days=5)).strftime("%Y%m%d")
        xml = f'<Event type="Earnings" ><EstimatedDate>{future}</EstimatedDate></Event>'
        mgr = self._mgr()
        result = mgr._parse_earnings_from_xml(xml, today)
        self.assertIsNotNone(result)
        self.assertEqual(result, today + timedelta(days=5))

    def test_parse_earnings_from_xml_past_date_ignored(self):
        from datetime import date, timedelta
        today = date.today()
        past = (today - timedelta(days=1)).strftime("%Y%m%d")
        xml = f'<Event type="Earnings"><ActualDate>{past}</ActualDate></Event>'
        mgr = self._mgr()
        result = mgr._parse_earnings_from_xml(xml, today)
        self.assertIsNone(result)

    def test_parse_earnings_from_xml_empty_returns_none(self):
        mgr = self._mgr()
        result = mgr._parse_earnings_from_xml("", date.today())
        self.assertIsNone(result)

    def test_parse_dividend_from_xml_future_date(self):
        from datetime import date, timedelta
        today = date.today()
        future = (today + timedelta(days=3)).strftime("%Y%m%d")
        xml = f'<Event type="Dividend"><ExDate>{future}</ExDate></Event>'
        mgr = self._mgr()
        result = mgr._parse_dividend_from_xml(xml, today)
        self.assertIsNotNone(result)
        self.assertEqual(result, today + timedelta(days=3))

    def test_parse_dividend_from_xml_empty_returns_none(self):
        mgr = self._mgr()
        result = mgr._parse_dividend_from_xml("", date.today())
        self.assertIsNone(result)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Singleton get_manager
# ─────────────────────────────────────────────────────────────────────────────

class TestGetManagerSingleton(unittest.TestCase):

    def setUp(self):
        reset_manager()

    def tearDown(self):
        reset_manager()

    def test_get_manager_returns_manager(self):
        mgr = get_manager()
        self.assertIsInstance(mgr, IBKRConnectionManager)

    def test_get_manager_same_instance(self):
        mgr1 = get_manager()
        mgr2 = get_manager()
        self.assertIs(mgr1, mgr2)

    def test_reset_manager_creates_new_instance(self):
        mgr1 = get_manager()
        reset_manager()
        mgr2 = get_manager()
        self.assertIsNot(mgr1, mgr2)

    def test_get_manager_thread_safe(self):
        """Più thread che chiamano get_manager() → stesso singleton."""
        results = []

        def _worker():
            results.append(get_manager())

        threads = [threading.Thread(target=_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Tutti devono aver ottenuto la stessa istanza
        self.assertTrue(all(r is results[0] for r in results))

    def test_default_host_and_client_id(self):
        mgr = get_manager()
        self.assertEqual(mgr._host, IBKR_HOST)
        self.assertEqual(mgr._client_id, IBKR_CLIENT_ID)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Integration: scan_opportunities usa IBKR se connesso
# ─────────────────────────────────────────────────────────────────────────────

class TestIBKRScanIntegration(unittest.TestCase):
    """
    Verifica che scan_opportunities usi IBKRConnectionManager per i eventi
    quando il manager è connesso, e yfinance quando non lo è.
    """

    def setUp(self):
        reset_manager()

    def tearDown(self):
        reset_manager()

    def _fake_chain_result(self, symbol="SPY"):
        """Ritorna un ChainFilterResult minimale per evitare chiamate reali."""
        from datetime import datetime, timezone
        from strategy.opportunity_scanner import (
            ChainFilterResult, FilterRejectStats, OptionContract
        )
        contract = OptionContract(
            symbol=symbol, expiry="2026-04-17", dte=33,
            strike=495.0, right="P",
            bid=1.60, ask=2.10, delta=-0.30,
            gamma=0.01, theta=-0.05, vega=0.20,
            iv=0.28, open_interest=600, volume=150,
            underlying_price=500.0,
        )
        stats = FilterRejectStats()
        return ChainFilterResult(
            symbol=symbol,
            profile="dev",
            data_mode="SYNTHETIC_SURFACE_CALIBRATED",
            fetched_at=datetime.now(timezone.utc).isoformat(),
            expiry="2026-04-17",
            dte=33,
            underlying_price=500.0,
            contracts_raw=1,
            contracts_kept=[contract],
            reject_stats=stats,
            cache_age_hours=None,
            source="csv_delayed",
            data_quality="cache",
        )

    def test_scan_uses_ibkr_events_when_connected(self):
        """Con manager connesso → get_events_for_symbol usato, non check_events."""
        from strategy.opportunity_scanner import scan_opportunities

        mock_mgr = MagicMock()
        mock_mgr.is_connected = True
        ev_ibkr = _make_event_result("SPY")
        mock_mgr.get_events_for_symbol.return_value = ev_ibkr

        with patch("execution.ibkr_connection.get_manager", return_value=mock_mgr), \
             patch("strategy.opportunity_scanner.fetch_and_filter_chain",
                   return_value=self._fake_chain_result("SPY")), \
             patch("scripts.fetch_iv_history.load_iv_history", return_value=[0.25]*60), \
             patch("scripts.events_calendar.check_events") as mock_yf_check:
            result = scan_opportunities(
                profile="dev",
                regime="NORMAL",
                symbols=["SPY"],
                top_n=1,
            )

        # check_events (yfinance) NON deve essere chiamato
        mock_yf_check.assert_not_called()
        # get_events_for_symbol (IBKR) DEVE essere chiamato
        mock_mgr.get_events_for_symbol.assert_called_once_with("SPY")

    def test_scan_uses_yfinance_when_ibkr_disconnected(self):
        """Con manager non connesso → fallback a check_events."""
        from strategy.opportunity_scanner import scan_opportunities

        mock_mgr = MagicMock()
        mock_mgr.is_connected = False
        ev_yf = _make_event_result("SPY")

        with patch("execution.ibkr_connection.get_manager", return_value=mock_mgr), \
             patch("strategy.opportunity_scanner.fetch_and_filter_chain",
                   return_value=self._fake_chain_result("SPY")), \
             patch("scripts.fetch_iv_history.load_iv_history", return_value=[0.25]*60), \
             patch("scripts.events_calendar.check_events", return_value=ev_yf) as mock_yf_check:
            result = scan_opportunities(
                profile="dev",
                regime="NORMAL",
                symbols=["SPY"],
                top_n=1,
            )

        # check_events (yfinance) DEVE essere chiamato
        mock_yf_check.assert_called()
        # get_events_for_symbol (IBKR) NON deve essere chiamato quando disconnesso
        mock_mgr.get_events_for_symbol.assert_not_called()

    def test_scan_block_still_works_via_ibkr(self):
        """EARNINGS_2D via IBKR → candidato bloccato."""
        from strategy.opportunity_scanner import scan_opportunities

        mock_mgr = MagicMock()
        mock_mgr.is_connected = True
        ev_block = _make_event_result("SPY", block=True, earnings_flag="EARNINGS_2D")
        mock_mgr.get_events_for_symbol.return_value = ev_block

        with patch("execution.ibkr_connection.get_manager", return_value=mock_mgr), \
             patch("strategy.opportunity_scanner.fetch_and_filter_chain",
                   return_value=self._fake_chain_result("SPY")), \
             patch("scripts.fetch_iv_history.load_iv_history", return_value=[0.25]*60):
            result = scan_opportunities(
                profile="dev",
                regime="NORMAL",
                symbols=["SPY"],
                top_n=5,
            )

        # Candidato bloccato → nessun candidato nell'output
        self.assertEqual(len(result.candidates), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
