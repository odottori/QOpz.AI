"""
execution/ibkr_connection.py — ROC4-T1

Layer di connessione IBKR con auto-detect porta e degradazione sicura.

Porte TWS/Gateway tentate in ordine:
  7497 → TWS paper trading
  4002 → IB Gateway paper trading
  7496 → TWS live trading
  4001 → IB Gateway live trading

Comportamento:
  - try_connect(): tenta connessione non-bloccante (timeout 2s default)
  - Se TWS/Gateway non è aperto → is_connected=False, nessuna eccezione
  - get_events_for_symbol(): usa IBKR calendar se connesso, yfinance altrimenti
  - DATA_MODE: se connesso → source_system="ibkr_live", altrimenti "yfinance"

Uso tipico (auto-detect silenzioso all'avvio):
  from execution.ibkr_connection import get_manager
  mgr = get_manager()
  mgr.try_connect()          # silenzioso se TWS non aperto
  if mgr.is_connected:
      ev = mgr.get_events_for_symbol("AAPL")
"""
from __future__ import annotations

import logging
import os
import re
import socket
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Porte candidate (ordine di priorità)
# ─────────────────────────────────────────────────────────────────────────────
IBKR_PORTS: list[int] = [7497, 4002, 7496, 4001]
IBKR_HOST: str = os.environ.get("IBKR_HOST", "127.0.0.1")  # override via env per Docker (es. IBKR_HOST=ibg)
IBKR_CLIENT_ID: int = 10          # client_id dedicato al monitoring (non trading)
CONNECT_TIMEOUT: float = 2.0      # secondi per il probe TCP


# ─────────────────────────────────────────────────────────────────────────────
# Dataclass output
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IBKRStatus:
    connected: bool
    host: str
    port: Optional[int]
    client_id: int
    source_system: str            # "ibkr_live" | "yfinance" | "unavailable"
    connected_at: Optional[str]   # ISO timestamp UTC


# ─────────────────────────────────────────────────────────────────────────────
# Helper: probe TCP porta (non apre IB API, solo verifica ascolto)
# ─────────────────────────────────────────────────────────────────────────────

def _probe_port(host: str, port: int, timeout: float = CONNECT_TIMEOUT) -> bool:
    """Verifica se una porta TCP è in ascolto. Non apre la IB API."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as _:
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# IBKRConnectionManager
# ─────────────────────────────────────────────────────────────────────────────

class IBKRConnectionManager:
    """
    Gestisce la connessione a TWS/IB Gateway via ib_insync.

    Thread-safe via lock interno. Degradazione sicura: qualsiasi errore
    lascia is_connected=False senza eccezioni propagate all'esterno.
    """

    def __init__(
        self,
        host: str = IBKR_HOST,
        ports: list[int] | None = None,
        client_id: int = IBKR_CLIENT_ID,
        connect_timeout: float = CONNECT_TIMEOUT,
    ) -> None:
        self._host = host
        self._ports = ports if ports is not None else list(IBKR_PORTS)
        self._client_id = client_id
        self._connect_timeout = connect_timeout

        self._ib = None               # ib_insync.IB instance (lazy)
        self._connected = False
        self._active_port: Optional[int] = None
        self._connected_at: Optional[str] = None
        self._lock = threading.Lock()

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        with self._lock:
            if not self._connected:
                return False
            # Verifica live: ib_insync potrebbe aver perso la connessione
            try:
                return bool(self._ib and self._ib.isConnected())
            except Exception:
                self._connected = False
                return False

    @property
    def source_system(self) -> str:
        return "ibkr_live" if self.is_connected else "yfinance"

    # ── Connect / Disconnect ─────────────────────────────────────────────────

    def try_connect(self, timeout: float | None = None) -> bool:
        """
        Tenta connessione a TWS/Gateway. Ritorna True se connesso.

        Non propaga eccezioni: se fallisce → ritorna False silenziosamente.
        """
        if timeout is None:
            timeout = self._connect_timeout

        with self._lock:
            # Se già connesso, verifica che sia ancora viva
            if self._connected and self._ib and self._ib.isConnected():
                return True

            # Reset stato
            self._connected = False
            self._active_port = None

            # Prova ogni porta nell'ordine di priorità
            for port in self._ports:
                if not _probe_port(self._host, port, timeout=timeout):
                    continue
                # Porta aperta → tenta connessione IB API
                try:
                    ib = self._get_or_create_ib()
                    self._ib = ib          # store reference prima di connect
                    ib.connect(
                        self._host,
                        port,
                        clientId=self._client_id,
                        timeout=timeout,
                        readonly=True,      # solo lettura: dati, nessun ordine
                    )
                    if ib.isConnected():
                        self._connected = True
                        self._active_port = port
                        self._connected_at = datetime.now(timezone.utc).isoformat()
                        logger.info(
                            "IBKR connected host=%s port=%d clientId=%d",
                            self._host, port, self._client_id,
                        )
                        return True
                except Exception as exc:
                    logger.debug("IBKR connect port=%d failed: %s", port, exc)
                    try:
                        if self._ib:
                            self._ib.disconnect()
                    except Exception:
                        pass

            logger.debug("IBKR not available (TWS/Gateway not open)")
            return False

    def disconnect(self) -> None:
        """Disconnette da TWS/Gateway. Sicuro se già disconnesso."""
        with self._lock:
            self._connected = False
            self._active_port = None
            try:
                if self._ib and self._ib.isConnected():
                    self._ib.disconnect()
            except Exception as exc:
                logger.debug("IBKR disconnect error: %s", exc)
            self._ib = None

    # ── Context manager ──────────────────────────────────────────────────────

    def __enter__(self) -> "IBKRConnectionManager":
        self.try_connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    # ── Info ─────────────────────────────────────────────────────────────────

    def connection_info(self) -> dict:
        """Ritorna dict con stato corrente della connessione."""
        return {
            "connected":    self.is_connected,
            "host":         self._host,
            "port":         self._active_port,
            "client_id":    self._client_id,
            "source_system": self.source_system,
            "connected_at": self._connected_at,
        }

    def status(self) -> IBKRStatus:
        return IBKRStatus(
            connected=self.is_connected,
            host=self._host,
            port=self._active_port,
            client_id=self._client_id,
            source_system=self.source_system,
            connected_at=self._connected_at,
        )

    # ── Events via IBKR ──────────────────────────────────────────────────────

    def get_events_for_symbol(self, symbol: str):
        """
        Ritorna EventCheckResult per il simbolo.

        Se connesso a IBKR → tenta fetch dal calendario IB.
        Se non connesso o fetch fallisce → fallback a yfinance (check_events).
        Mai propaga eccezioni.
        """
        if not self.is_connected:
            return self._yfinance_fallback(symbol)

        try:
            return self._fetch_events_ibkr(symbol)
        except Exception as exc:
            logger.debug("IBKR events fetch failed for %s: %s — using yfinance", symbol, exc)
            return self._yfinance_fallback(symbol)

    def _fetch_events_ibkr(self, symbol: str):
        """
        Fetch eventi da IBKR (earnings + dividendi) via ib_insync fundamentals.

        IBKR fornisce CompanyFinancials XML; lo mappiamo a EventCheckResult.
        Se non disponibile → solleva eccezione (catturata da get_events_for_symbol).
        """
        from scripts.events_calendar import (
            EventCheckResult,
            EARNINGS_BLOCK_DAYS,
            EARNINGS_FLAG_DAYS,
            DIVIDEND_FLAG_DAYS,
        )

        today = date.today()

        # ib_insync: reqFundamentalData con ReportType="CalendarReport"
        # Disponibile solo con account paper/live con permesso Market Data
        # Se non disponibile → eccezione → fallback yfinance
        contract = self._make_stock_contract(symbol)
        xml_data: str = self._ib.reqFundamentalData(contract, "CalendarReport")

        # Parse XML minimale per estrarre earnings date e ex-div date
        earnings_dt = self._parse_earnings_from_xml(xml_data, today)
        dividend_dt = self._parse_dividend_from_xml(xml_data, today)

        # Applica regole flag/blocco (stesse di events_calendar.py)
        days_to_earn: Optional[int] = None
        earnings_flag: Optional[str] = None
        block_trade: bool = False
        restrict_lg: bool = False

        if earnings_dt is not None:
            days_to_earn = (earnings_dt - today).days
            if 0 <= days_to_earn <= EARNINGS_BLOCK_DAYS:
                earnings_flag = "EARNINGS_2D"
                block_trade = True
            elif EARNINGS_BLOCK_DAYS < days_to_earn <= EARNINGS_FLAG_DAYS:
                earnings_flag = "EARNINGS_7D"
                restrict_lg = True

        days_to_div: Optional[int] = None
        dividend_flag: Optional[str] = None
        if dividend_dt is not None:
            days_to_div = (dividend_dt - today).days
            if 0 <= days_to_div <= DIVIDEND_FLAG_DAYS:
                dividend_flag = "DIVIDEND_5D"

        return EventCheckResult(
            symbol=symbol,
            as_of_date=today,
            earnings_date=earnings_dt,
            dividend_date=dividend_dt,
            days_to_earnings=days_to_earn,
            days_to_dividend=days_to_div,
            earnings_flag=earnings_flag,
            dividend_flag=dividend_flag,
            block_trade=block_trade,
            restrict_long_gamma=restrict_lg,
        )

    def _parse_date_from_xml(self, xml: str, pattern: str, today: date) -> Optional[date]:
        """Helper condiviso: estrae la prossima data (YYYYMMDD) che corrisponde al pattern."""
        upcoming: list[date] = []
        for m in re.finditer(pattern, xml, re.DOTALL | re.IGNORECASE):
            try:
                d = datetime.strptime(m.group(1), "%Y%m%d").date()
                if d >= today:
                    upcoming.append(d)
            except ValueError:
                continue
        return min(upcoming) if upcoming else None

    def _parse_earnings_from_xml(self, xml: str, today: date) -> Optional[date]:
        """Estrae prossima earnings date dall'XML CalendarReport IBKR."""
        # IBKR CalendarReport: <Event type="Earnings" ...><ActualDate>YYYYMMDD</ActualDate>
        pattern = r'<Event\s[^>]*type="Earnings"[^>]*>.*?<(?:Actual|Estimated)Date>(\d{8})</(?:Actual|Estimated)Date>'
        return self._parse_date_from_xml(xml, pattern, today)

    def _parse_dividend_from_xml(self, xml: str, today: date) -> Optional[date]:
        """Estrae prossima ex-dividend date dall'XML CalendarReport IBKR."""
        pattern = r'<Event\s[^>]*type="Dividend"[^>]*>.*?<ExDate>(\d{8})</ExDate>'
        return self._parse_date_from_xml(xml, pattern, today)

    def _make_stock_contract(self, symbol: str):
        """Crea contratto Stock ib_insync per il simbolo."""
        from ib_insync import Stock
        return Stock(symbol, "SMART", "USD")

    def _yfinance_fallback(self, symbol: str):
        """Fallback a yfinance. Ritorna EventCheckResult vuoto se yfinance fallisce."""
        try:
            from scripts.events_calendar import check_events as _check_events
            return _check_events(symbol)
        except Exception:
            from scripts.events_calendar import EventCheckResult
            return EventCheckResult(
                symbol=symbol,
                as_of_date=date.today(),
                earnings_date=None,
                dividend_date=None,
                days_to_earnings=None,
                days_to_dividend=None,
                earnings_flag=None,
                dividend_flag=None,
                block_trade=False,
                restrict_long_gamma=False,
            )

    # ── Internals ────────────────────────────────────────────────────────────

    def _get_or_create_ib(self):
        """Crea o ricicla istanza ib_insync.IB."""
        if self._ib is None:
            from ib_insync import IB
            self._ib = IB()
        return self._ib


# ─────────────────────────────────────────────────────────────────────────────
# Singleton module-level
# ─────────────────────────────────────────────────────────────────────────────

_manager: Optional[IBKRConnectionManager] = None
_manager_lock = threading.Lock()


def get_manager(
    host: str = IBKR_HOST,
    ports: list[int] | None = None,
    client_id: int = IBKR_CLIENT_ID,
) -> IBKRConnectionManager:
    """
    Ritorna il singleton IBKRConnectionManager.

    Thread-safe. Crea il manager al primo accesso (non tenta connessione
    automaticamente: chiamare .try_connect() esplicitamente).
    """
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = IBKRConnectionManager(
                host=host,
                ports=ports,
                client_id=client_id,
            )
    return _manager


def reset_manager() -> None:
    """Reset del singleton (per test). Disconnette e azzera."""
    global _manager
    with _manager_lock:
        if _manager is not None:
            try:
                _manager.disconnect()
            except Exception:
                pass
            _manager = None
