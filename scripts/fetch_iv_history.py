"""
scripts/fetch_iv_history.py — ROC0-T3

Fetch historical ATM implied-volatility (IV) for a list of symbols and persist
to data/providers/iv_history_{SYMBOL}.json for use by the IV Z-Score engine in
strategy/opportunity_scanner.py.

Source hierarchy
----------------
1. yfinance options chain (free, no key) — ATM call/put IV from nearest expiry
   that falls in [20, 45] DTE; falls back to HV proxy (option IV unavailable
   during off-market hours for many tickers).
2. HV proxy — std(log_returns, 20) * sqrt(252) computed from daily close prices
   via yfinance history when option-chain IV is unavailable.

Output format (JSON per symbol)
--------------------------------
{
  "symbol": "AAPL",
  "data_mode": "VENDOR_REAL_CHAIN",
  "updated_at": "<UTC ISO>",
  "points": 90,
  "iv_history": [
    {"date": "2025-01-02", "iv": 0.245},
    ...
  ]
}

Usage
-----
    python scripts/fetch_iv_history.py AAPL SPY QQQ
    python scripts/fetch_iv_history.py --symbols AAPL SPY --days 90 -v
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
IV_HISTORY_DIR = ROOT / "data" / "providers"
IV_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_LOOKBACK_DAYS = 90
MIN_POINTS_REQUIRED   = 30

# Module-level import so tests can patch scripts.fetch_iv_history.yf
try:
    import yfinance as yf  # type: ignore
except ImportError:
    yf = None  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _data_mode() -> str:
    import os
    return os.environ.get("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")


def _safe_float(val, default: float = 0.0) -> float:
    try:
        f = float(val)
        return f if math.isfinite(f) and f > 0.0 else default
    except (TypeError, ValueError):
        return default


def _history_path(symbol: str) -> Path:
    return IV_HISTORY_DIR / f"iv_history_{symbol.upper()}.json"


# ─────────────────────────────────────────────────────────────────────────────
# Fetch from yfinance
# ─────────────────────────────────────────────────────────────────────────────

def _hv_from_yfinance(symbol: str, lookback_days: int) -> list[dict]:
    """
    Compute Historical Volatility (HV) proxy from daily close prices via yfinance.

    HV = std(log_returns, window=20) * sqrt(252) — used as IV approximation
    when option-chain IV is unavailable (off-hours, less liquid tickers).

    Returns list[{"date": "YYYY-MM-DD", "iv": float}], most recent last.
    """
    if yf is None:
        return []

    period_days = lookback_days + 60  # buffer for rolling window
    start = (datetime.now(timezone.utc).date() - timedelta(days=period_days)).isoformat()
    ticker = yf.Ticker(symbol)
    hist = ticker.history(start=start, auto_adjust=True)
    if hist.empty or "Close" not in hist.columns:
        return []

    closes = hist["Close"].dropna()
    if len(closes) < 22:
        return []

    import statistics as _stats

    log_returns = [
        math.log(closes.iloc[i] / closes.iloc[i - 1])
        for i in range(1, len(closes))
    ]

    result = []
    window = 20
    for i in range(window, len(log_returns) + 1):
        window_rets = log_returns[i - window: i]
        try:
            hv = _stats.stdev(window_rets) * math.sqrt(252)
        except Exception:
            continue
        idx = closes.index[i]
        try:
            d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
        except Exception:
            continue
        result.append({"date": d.isoformat(), "iv": round(hv, 6)})

    return result[-lookback_days:]


def _iv_from_option_chain(symbol: str) -> Optional[float]:
    """
    Return today's ATM IV from yfinance option chain (nearest expiry in 20–45 DTE).
    Uses average of call and put IV at ATM strike.
    Returns None if chain unavailable or IV not populated.
    """
    if yf is None:
        return None

    today = datetime.now(timezone.utc).date()
    ticker = yf.Ticker(symbol)

    try:
        expirations = ticker.options
    except Exception:
        return None

    if not expirations:
        return None

    chosen_exp: Optional[str] = None
    for exp_str in sorted(expirations):
        try:
            exp_date = date.fromisoformat(exp_str)
            dte = (exp_date - today).days
            if 20 <= dte <= 45:
                chosen_exp = exp_str
                break
        except Exception:
            continue

    if chosen_exp is None:
        return None

    try:
        chain = ticker.option_chain(chosen_exp)
    except Exception:
        return None

    try:
        info = ticker.fast_info
        underlying = float(getattr(info, "last_price", 0.0) or 0.0)
        if underlying <= 0.0:
            calls = chain.calls
            if not calls.empty:
                underlying = float(calls["strike"].median())
    except Exception:
        underlying = 0.0

    if underlying <= 0.0:
        return None

    try:
        calls = chain.calls
        puts = chain.puts
        all_strikes = sorted(set(calls["strike"].tolist()) | set(puts["strike"].tolist()))
        if not all_strikes:
            return None
        atm_strike = min(all_strikes, key=lambda s: abs(s - underlying))

        iv_vals = []
        for df_row in (calls[calls["strike"] == atm_strike],
                       puts[puts["strike"] == atm_strike]):
            if not df_row.empty:
                iv_val = _safe_float(df_row["impliedVolatility"].values[0])
                if iv_val > 0.0:
                    iv_vals.append(iv_val)

        if not iv_vals:
            return None
        return round(sum(iv_vals) / len(iv_vals), 6)
    except Exception:
        return None


def fetch_iv_history(symbol: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> list[dict]:
    """
    Build IV history for a symbol using yfinance.

    1. HV proxy as base time-series (always available when market data exists).
    2. Enrich today's point with actual ATM option-chain IV if available.

    Returns list[{"date": "YYYY-MM-DD", "iv": float}], most recent last.
    Returns [] if yfinance cannot retrieve data (e.g. invalid symbol).
    """
    history = _hv_from_yfinance(symbol, lookback_days)

    today_str = datetime.now(timezone.utc).date().isoformat()
    chain_iv = _iv_from_option_chain(symbol)
    if chain_iv is not None and chain_iv > 0.0:
        history = [p for p in history if p["date"] != today_str]
        history.append({"date": today_str, "iv": chain_iv})
        history.sort(key=lambda p: p["date"])

    return history


# ─────────────────────────────────────────────────────────────────────────────
# Persist + load
# ─────────────────────────────────────────────────────────────────────────────

def save_iv_history(symbol: str, history: list[dict]) -> Path:
    """Persist IV history to data/providers/iv_history_{SYMBOL}.json."""
    path = _history_path(symbol)
    payload = {
        "symbol": symbol.upper(),
        "data_mode": _data_mode(),
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "points": len(history),
        "iv_history": history,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_iv_history(symbol: str) -> list[float]:
    """
    Load persisted IV history for a symbol.

    Returns list[float] (decimal IV, most recent last) for use by
    strategy/opportunity_scanner.compute_iv_zscore().

    Returns [] if no file found or file is malformed.
    """
    path = _history_path(symbol)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("iv_history", [])
        sorted_pts = sorted(raw, key=lambda p: p.get("date", ""))
        return [float(p["iv"]) for p in sorted_pts if _safe_float(p.get("iv")) > 0.0]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def _run(symbols: list[str], days: int, verbose: bool) -> int:
    exit_code = 0
    for sym in symbols:
        sym = sym.upper()
        history = fetch_iv_history(sym, lookback_days=days)

        if not history:
            print(f"[WARN] {sym}: no IV history fetched from yfinance", file=sys.stderr)
            exit_code = 2
            continue

        n = len(history)
        path = save_iv_history(sym, history)

        if n < MIN_POINTS_REQUIRED:
            print(
                f"[WARN] {sym}: only {n} points (need >=={MIN_POINTS_REQUIRED}) "
                f"-- Z-Score may be unreliable",
                file=sys.stderr,
            )
            exit_code = max(exit_code, 2)

        if verbose:
            first   = history[0]["date"] if history else "?"
            last    = history[-1]["date"] if history else "?"
            iv_last = history[-1]["iv"]  if history else 0.0
            print(
                f"[OK]   {sym:6s}  {n:3d} pts  {first} to {last}  "
                f"iv_last={iv_last:.4f}  src=yfinance  file={path.name}"
            )
        else:
            print(f"[OK]   {sym}: {n} points saved to {path.name}")

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch IV history (yfinance) for IV Z-Score computation."
    )
    parser.add_argument("symbols", nargs="*", help="Ticker symbols (e.g. AAPL SPY)")
    parser.add_argument("--symbols", dest="symbols_flag", nargs="+",
                        help="Alternative way to pass symbols")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help=f"Lookback days (default {DEFAULT_LOOKBACK_DAYS})")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print date range and last IV value")
    args = parser.parse_args()

    symbols = list(args.symbols or []) + list(args.symbols_flag or [])
    if not symbols:
        parser.print_help()
        sys.exit(0)

    sys.exit(_run(symbols, days=args.days, verbose=args.verbose))


if __name__ == "__main__":
    main()
