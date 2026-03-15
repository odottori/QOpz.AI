"""
scripts/events_calendar.py — ROC2-T1

Fetch upcoming corporate events (earnings, dividends) per simbolo
e applica le regole di blocco/flag definite in PROJECT_OPZ_COMPLETE_V2.

Regole:
  - earnings entro 0–2 giorni  → EARNINGS_2D  → block_trade = True
  - earnings entro 3–7 giorni  → EARNINGS_7D  → restrict_long_gamma = True
  - ex-dividend entro 0–5 giorni → DIVIDEND_5D → dividend_flag set

Sorgente: yfinance Ticker.calendar (proxy gratuito, no API key).
Degradazione: se yfinance non disponibile o fetch fallisce → risultato vuoto
              (block=False, flag=None) — non blocca la pipeline.

CLI:
    python scripts/events_calendar.py AAPL SPY TSLA
    python scripts/events_calendar.py AAPL --as-of 2026-04-10
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Optional

# Module-level import for patchability in tests (stessa convenzione di fetch_iv_history.py)
try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None  # type: ignore[assignment]

# ─────────────────────────────────────────────────────────────────────────────
# Costanti
# ─────────────────────────────────────────────────────────────────────────────
EARNINGS_BLOCK_DAYS   = 2   # blocco totale se earnings entro N giorni
EARNINGS_FLAG_DAYS    = 7   # flag + restrict long-gamma se entro N giorni
DIVIDEND_FLAG_DAYS    = 5   # flag dividendo se ex-date entro N giorni

LONG_GAMMA_STRATEGIES = frozenset({"BULL_CALL", "STRADDLE"})


# ─────────────────────────────────────────────────────────────────────────────
# Dataclass output
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class EventCheckResult:
    """Risultato check eventi per un simbolo."""
    symbol:               str
    as_of_date:           date
    earnings_date:        Optional[date]   # prossima earnings (o None)
    dividend_date:        Optional[date]   # prossima ex-div (o None)
    days_to_earnings:     Optional[int]    # None se nessuna earnings nota
    days_to_dividend:     Optional[int]    # None se nessuna dividend nota
    earnings_flag:        Optional[str]    # None | "EARNINGS_2D" | "EARNINGS_7D"
    dividend_flag:        Optional[str]    # None | "DIVIDEND_5D"
    block_trade:          bool             # True → BLOCCO TOTALE
    restrict_long_gamma:  bool             # True → no BULL_CALL / STRADDLE


# ─────────────────────────────────────────────────────────────────────────────
# Fetch dal calendario yfinance
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_calendar(symbol: str) -> dict:
    """Fetch raw calendar dict da yfinance. Ritorna {} in caso di errore."""
    if yf is None:
        return {}
    try:
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is None:
            return {}
        # yfinance può ritornare DataFrame o dict a seconda della versione
        if hasattr(cal, "to_dict"):
            cal = cal.to_dict()
        return cal if isinstance(cal, dict) else {}
    except Exception:
        return {}


def _parse_date_value(val) -> Optional[date]:
    """Converte qualsiasi valore restituito da yfinance in date, o None."""
    if val is None:
        return None
    # Pandas Timestamp, datetime, o oggetto con .date()
    if hasattr(val, "date") and callable(val.date):
        try:
            return val.date()
        except Exception:
            pass
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, (int, float)):
        # UNIX timestamp (ms o s)
        try:
            ts = val / 1000 if val > 1e10 else val
            return datetime.utcfromtimestamp(ts).date()
        except Exception:
            return None
    if isinstance(val, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                pass
    return None


def fetch_earnings_date(symbol: str) -> Optional[date]:
    """Ritorna la prossima data di earnings da yfinance, o None."""
    cal = _fetch_calendar(symbol)
    today = date.today()

    for key in ("Earnings Date", "earningsDate", "Earnings Dates"):
        val = cal.get(key)
        if val is None:
            continue
        # val può essere singolo valore o lista
        items = val if isinstance(val, (list, tuple)) else [val]
        upcoming: list[date] = []
        for item in items:
            d = _parse_date_value(item)
            if d is not None and d >= today:
                upcoming.append(d)
        if upcoming:
            return min(upcoming)

    return None


def fetch_dividend_date(symbol: str) -> Optional[date]:
    """Ritorna la prossima ex-dividend date da yfinance, o None."""
    cal = _fetch_calendar(symbol)
    today = date.today()

    for key in ("Ex-Dividend Date", "exDividendDate", "Dividend Date"):
        val = cal.get(key)
        if val is None:
            continue
        d = _parse_date_value(val)
        if d is not None and d >= today:
            return d

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Check principale
# ─────────────────────────────────────────────────────────────────────────────

def check_events(
    symbol: str,
    as_of_date: Optional[date] = None,
) -> EventCheckResult:
    """
    Controlla eventi imminenti per un simbolo e applica le regole flag/blocco.

    Degradazione sicura: se yfinance non risponde, ritorna risultato vuoto
    (block=False, tutti i flag=None) senza eccezioni.
    """
    if as_of_date is None:
        as_of_date = date.today()

    # ── Earnings ─────────────────────────────────────────────────────────
    earnings_dt    = fetch_earnings_date(symbol)
    days_to_earn:    Optional[int]  = None
    earnings_flag:   Optional[str]  = None
    block_trade:     bool           = False
    restrict_lg:     bool           = False

    if earnings_dt is not None:
        days_to_earn = (earnings_dt - as_of_date).days
        if 0 <= days_to_earn <= EARNINGS_BLOCK_DAYS:
            earnings_flag = "EARNINGS_2D"
            block_trade   = True
        elif EARNINGS_BLOCK_DAYS < days_to_earn <= EARNINGS_FLAG_DAYS:
            earnings_flag = "EARNINGS_7D"
            restrict_lg   = True

    # ── Dividendi ────────────────────────────────────────────────────────
    dividend_dt    = fetch_dividend_date(symbol)
    days_to_div:     Optional[int]  = None
    dividend_flag:   Optional[str]  = None

    if dividend_dt is not None:
        days_to_div   = (dividend_dt - as_of_date).days
        if 0 <= days_to_div <= DIVIDEND_FLAG_DAYS:
            dividend_flag = "DIVIDEND_5D"

    return EventCheckResult(
        symbol               = symbol,
        as_of_date           = as_of_date,
        earnings_date        = earnings_dt,
        dividend_date        = dividend_dt,
        days_to_earnings     = days_to_earn,
        days_to_dividend     = days_to_div,
        earnings_flag        = earnings_flag,
        dividend_flag        = dividend_flag,
        block_trade          = block_trade,
        restrict_long_gamma  = restrict_lg,
    )


def combined_events_flag(ev: EventCheckResult) -> Optional[str]:
    """
    Ritorna il flag più grave (earnings > dividend) per OpportunityCandidate.events_flag.
    """
    if ev.earnings_flag:
        return ev.earnings_flag
    if ev.dividend_flag:
        return ev.dividend_flag
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _run(symbols: list[str], as_of: Optional[date], verbose: bool) -> int:
    results = []
    for sym in symbols:
        ev = check_events(sym.upper(), as_of_date=as_of)
        results.append({
            "symbol":              ev.symbol,
            "as_of":               ev.as_of_date.isoformat(),
            "earnings_date":       ev.earnings_date.isoformat() if ev.earnings_date else None,
            "days_to_earnings":    ev.days_to_earnings,
            "earnings_flag":       ev.earnings_flag,
            "dividend_date":       ev.dividend_date.isoformat() if ev.dividend_date else None,
            "days_to_dividend":    ev.days_to_dividend,
            "dividend_flag":       ev.dividend_flag,
            "block_trade":         ev.block_trade,
            "restrict_long_gamma": ev.restrict_long_gamma,
        })
        if verbose:
            status = "BLOCK" if ev.block_trade else (ev.earnings_flag or ev.dividend_flag or "CLEAR")
            print(f"  {ev.symbol:6s}  {status}", file=sys.stderr)

    print(json.dumps({"ok": True, "results": results}, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Events calendar check per simboli")
    parser.add_argument("symbols", nargs="+", help="Simboli da controllare (es. AAPL SPY)")
    parser.add_argument("--as-of", default=None, help="Data di riferimento YYYY-MM-DD (default: oggi)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    as_of: Optional[date] = None
    if args.as_of:
        try:
            as_of = date.fromisoformat(args.as_of)
        except ValueError:
            print(f"ERROR: --as-of deve essere YYYY-MM-DD, ricevuto: {args.as_of}", file=sys.stderr)
            sys.exit(1)

    sys.exit(_run(args.symbols, as_of, args.verbose))


if __name__ == "__main__":
    main()
