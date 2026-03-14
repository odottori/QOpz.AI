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
2. VIX proxy — if both yfinance IV and HV proxy fail, uses SPY HV as sentinel.

Output format (JSON per symbol)
--------------------------------
{
  "symbol": "AAPL",
  "data_mode": "SYNTHETIC_SURFACE_CALIBRATED",
  "updated_at": "<UTC ISO>",
  "iv_history": [
    {"date": "2025-01-02", "iv": 0.245},
    ...
  ]
}

Usage
-----
    python scripts/fetch_iv_history.py AAPL SPY QQQ
    python scripts/fetch_iv_history.py --symbols AAPL SPY --days 90
    python scripts/fetch_iv_history.py --symbols TEST --synthetic   # dev/test
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

# Number of trading-day points to persist (covers 60d window + buffer)
DEFAULT_LOOKBACK_DAYS = 90
MIN_POINTS_REQUIRED   = 30   # below this → warn, still save


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
    Compute a Historical Volatility (HV) proxy from daily close prices.

    HV = std(log returns, window=20) × sqrt(252) — used as IV approximation
    when option chain IV is unavailable.

    Returns list[{"date": "YYYY-MM-DD", "iv": float}], most recent last.
    """
    try:
        import yfinance as yf
    except ImportError:
        return []

    period_days = lookback_days + 60  # extra buffer for rolling window
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
        idx = closes.index[i]  # date index aligned with last window element
        try:
            d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
        except Exception:
            continue
        result.append({"date": d.isoformat(), "iv": round(hv, 6)})

    # Keep only the last lookback_days worth
    return result[-lookback_days:]


def _iv_from_option_chain(symbol: str) -> Optional[float]:
    """
    Return today's ATM IV from yfinance option chain (nearest valid expiry).
    Uses average of call and put IV at the ATM strike.
    Returns None if chain unavailable or IV not populated.
    """
    try:
        import yfinance as yf
    except ImportError:
        return None

    today = datetime.now(timezone.utc).date()
    ticker = yf.Ticker(symbol)

    try:
        expirations = ticker.options  # tuple of "YYYY-MM-DD" strings
    except Exception:
        return None

    if not expirations:
        return None

    # Pick nearest expiry in [20, 45] DTE
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
        # Get underlying price from info
        info = ticker.fast_info
        underlying = float(getattr(info, "last_price", 0.0) or 0.0)
        if underlying <= 0.0:
            # Fallback: use midpoint of nearest call strike
            calls = chain.calls
            if not calls.empty:
                underlying = float(calls["strike"].median())
    except Exception:
        underlying = 0.0

    if underlying <= 0.0:
        return None

    # Find ATM strike (closest to underlying)
    try:
        calls = chain.calls
        puts = chain.puts
        all_strikes = sorted(set(calls["strike"].tolist()) | set(puts["strike"].tolist()))
        if not all_strikes:
            return None
        atm_strike = min(all_strikes, key=lambda s: abs(s - underlying))

        iv_vals = []
        call_row = calls[calls["strike"] == atm_strike]
        put_row  = puts[puts["strike"] == atm_strike]
        for df_row in (call_row, put_row):
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
    Build an IV history list for a symbol.

    Strategy:
    1. Fetch HV proxy as the base time-series (always available).
    2. Try to get today's option-chain IV; if available, override/append today's point.

    Returns list[{"date": "YYYY-MM-DD", "iv": float}], most recent last.
    """
    history = _hv_from_yfinance(symbol, lookback_days)

    # Attempt to enrich today's point with actual option-chain IV
    today_str = datetime.now(timezone.utc).date().isoformat()
    chain_iv = _iv_from_option_chain(symbol)
    if chain_iv is not None and chain_iv > 0.0:
        # Replace or append today's point
        history = [p for p in history if p["date"] != today_str]
        history.append({"date": today_str, "iv": chain_iv})
        history.sort(key=lambda p: p["date"])

    return history


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic history (dev / test)
# ─────────────────────────────────────────────────────────────────────────────

def _synthetic_iv_history(symbol: str, n: int = DEFAULT_LOOKBACK_DAYS) -> list[dict]:
    """
    Generate deterministic synthetic IV history for dev/test (no network).
    Uses a simple sine wave around 0.25 ± 0.08 with per-symbol seed.
    """
    import hashlib
    seed = int(hashlib.md5(symbol.upper().encode()).hexdigest()[:8], 16)
    result = []
    today = datetime.now(timezone.utc).date()
    for i in range(n - 1, -1, -1):
        d = today - timedelta(days=i)
        phase = (seed + i) % 60
        iv = 0.25 + 0.08 * math.sin(2 * math.pi * phase / 60)
        result.append({"date": d.isoformat(), "iv": round(iv, 6)})
    return result


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

def _run(symbols: list[str], days: int, synthetic: bool, verbose: bool) -> int:
    exit_code = 0
    for sym in symbols:
        sym = sym.upper()
        if synthetic:
            history = _synthetic_iv_history(sym, n=days)
            source = "synthetic"
        else:
            history = fetch_iv_history(sym, lookback_days=days)
            source = "yfinance"

        if not history:
            print(f"[WARN] {sym}: no IV history fetched from {source}", file=sys.stderr)
            exit_code = 2
            continue

        n = len(history)
        path = save_iv_history(sym, history)

        if n < MIN_POINTS_REQUIRED:
            print(
                f"[WARN] {sym}: only {n} points (need ≥{MIN_POINTS_REQUIRED}) "
                f"— Z-Score may be unreliable",
                file=sys.stderr,
            )
            exit_code = max(exit_code, 2)

        if verbose:
            first = history[0]["date"] if history else "?"
            last  = history[-1]["date"] if history else "?"
            iv_last = history[-1]["iv"] if history else 0.0
            print(
                f"[OK]   {sym:6s}  {n:3d} pts  {first} to {last}  "
                f"iv_last={iv_last:.4f}  src={source}  file={path.name}"
            )
        else:
            print(f"[OK]   {sym}: {n} points saved to {path.name}")

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch/generate IV history for IV Z-Score computation."
    )
    parser.add_argument("symbols", nargs="*", help="Ticker symbols (e.g. AAPL SPY)")
    parser.add_argument("--symbols", dest="symbols_flag", nargs="+",
                        help="Alternative way to pass symbols")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help=f"Lookback days (default {DEFAULT_LOOKBACK_DAYS})")
    parser.add_argument("--synthetic", action="store_true",
                        help="Use deterministic synthetic data (dev/test, no network)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print date range and last IV value")
    args = parser.parse_args()

    symbols = list(args.symbols or []) + list(args.symbols_flag or [])
    if not symbols:
        parser.print_help()
        sys.exit(0)

    sys.exit(_run(symbols, days=args.days, synthetic=args.synthetic, verbose=args.verbose))


if __name__ == "__main__":
    main()
