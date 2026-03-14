from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def to_int(value: Any) -> int:
    x = to_float(value)
    if x is None:
        return 0
    return max(0, int(x))


def normalize_symbols(symbols: list[str] | None) -> list[str]:
    if not symbols:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        s = str(raw or "").strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def extract_numeric(record: dict[str, Any], keys: list[str]) -> float | None:
    for k in keys:
        if k in record:
            v = to_float(record.get(k))
            if v is not None:
                return v
    return None


def compute_liquidity(volume: int, open_interest: int, spread_pct: float) -> float:
    v = math.log10(max(1, volume))
    oi = math.log10(max(1, open_interest))
    lv = clamp01((v - 2.0) / 4.0)
    loi = clamp01((oi - 2.0) / 4.0)
    spread_quality = clamp01(1.0 - (spread_pct / 0.020))
    return clamp01(0.45 * lv + 0.35 * loi + 0.20 * spread_quality)


def regime_fit(regime: str, iv_rank: float, spread_pct: float) -> float:
    base = 0.65
    r = regime.upper()
    if r == "CAUTION":
        base = 0.48
    elif r == "SHOCK":
        base = 0.12
    return clamp01(base + 0.15 * iv_rank - 0.20 * clamp01(spread_pct / 0.03))


def pick_strategy(iv_rank: float, regime: str) -> str:
    r = regime.upper()
    if r == "SHOCK":
        return "NO_TRADE"
    if iv_rank >= 0.65:
        return "IRON_CONDOR"
    if iv_rank >= 0.45:
        return "BULL_PUT"
    if r == "CAUTION":
        return "WHEEL"
    return "CALENDAR"


def to_universe_row(symbol: str, regime: str, rec: dict[str, Any]) -> dict[str, Any] | None:
    bid = extract_numeric(rec, ["bid", "best_bid", "b"])
    ask = extract_numeric(rec, ["ask", "best_ask", "a"])
    last = extract_numeric(rec, ["last", "price", "mid", "mark", "close"])
    underlying = extract_numeric(rec, ["underlying_price", "underlying", "spot", "underlyingLast"])
    iv = extract_numeric(rec, ["iv", "implied_volatility", "impl_vol", "opt_imp_vol", "option_iv"])
    volume = to_int(extract_numeric(rec, ["volume", "avg_volume", "avgVolume", "opt_volume", "option_volume"]))
    open_interest = to_int(extract_numeric(rec, ["open_interest", "oi", "option_oi", "optoi"]))

    if bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid:
        mid = (bid + ask) / 2.0
        spread_pct = (ask - bid) / mid if mid > 0 else 1.0
    else:
        spread_pct = 1.0

    px = underlying if underlying is not None else last
    if px is None:
        return None

    iv_rank = clamp01((iv or 0.0) / 1.0)
    liquidity = compute_liquidity(volume, open_interest, spread_pct)
    fit = regime_fit(regime, iv_rank, spread_pct)
    score = clamp01(0.36 * iv_rank + 0.34 * liquidity + 0.30 * fit)

    return {
        "symbol": symbol,
        "asset_type": str(rec.get("asset_type") or "equity").strip().lower(),
        "last": px,
        "bid": bid,
        "ask": ask,
        "iv": iv,
        "volume": volume,
        "open_interest": open_interest,
        "delta": extract_numeric(rec, ["delta"]),
        "gamma": extract_numeric(rec, ["gamma"]),
        "theta": extract_numeric(rec, ["theta"]),
        "vega": extract_numeric(rec, ["vega"]),
        "rho": extract_numeric(rec, ["rho"]),
        "underlying_price": underlying,
        "iv_rank": iv_rank,
        "spread_pct": spread_pct,
        "regime_fit": fit,
        "liquidity_score": liquidity,
        "score": score,
        "strategy": pick_strategy(iv_rank, regime),
        "observed_at_utc": str(rec.get("observed_at_utc") or rec.get("captured_ts_utc") or utcnow_iso()),
    }
