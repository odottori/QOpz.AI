"""
strategy/opportunity_scanner.py — ROC0-T1 + ROC0-T2

Option Chain Fetcher (IBKR TWS paper/live + CSV fallback for dev),
JSON snapshot cache (TTL 18h), hard-filter pipeline, IV Z-Score
(30d / 60d windows), and Expected Move from ATM straddle.

Public API
----------
fetch_and_filter_chain(symbol, profile, ...)  -> ChainFilterResult
compute_chain_analytics(result, iv_history)   -> ChainAnalytics
apply_hard_filters(contracts, params)         -> tuple[kept, stats]
compute_iv_zscore(iv_current, history, win)   -> float | None
compute_expected_move(contracts, underlying)  -> EM tuple

Profiles
--------
dev   : CSV fallback from data/providers/chain_{symbol}.csv (synthetic)
paper : IBKR TWS paper account (port 7496), falls back to CSV on error
live  : IBKR TWS live account (port 7497), falls back to CSV on error
"""
from __future__ import annotations

import csv
import json
import math
import os
import socket
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "cache"
CHAIN_CSV_DIR = ROOT / "data" / "providers"

# ── Hard-filter defaults ───────────────────────────────────────────────────
HARD_MIN_DTE: int          = 14      # absolute floor (CLAUDE.md)
HARD_MAX_DTE: int          = 60      # absolute ceiling
DEFAULT_MIN_DTE: int       = 20      # preferred window
DEFAULT_MAX_DTE: int       = 45
DEFAULT_MIN_OI: int        = 100     # canonical hard minimum
PAPER_LIVE_MIN_OI: int     = 500     # stricter for paper/live (Opportunity Scanner doc)
DEFAULT_MAX_SPREAD_PCT     = 10.0    # % of mid
DEFAULT_MIN_VOLUME: int    = 10
DEFAULT_MIN_IVR            = 20.0    # IVR < 20 → edge null (scoring.py hard filter)
DELTA_LONG_MIN             = 0.15
DELTA_LONG_MAX             = 0.50

# ── Cache ──────────────────────────────────────────────────────────────────
CACHE_TTL_HOURS            = 18
CHAIN_SNAPSHOT_CLIENT_ID   = 8       # separate from order client_id (7)

# ── IV Z-Score interpretation ──────────────────────────────────────────────
Z_CHEAP_THRESHOLD          = -1.5    # IV cheap  → long vega preferred
Z_EXPENSIVE_THRESHOLD      = +1.5    # IV expensive → short vega preferred


# ─────────────────────────────────────────────────────────────────────────────
# 1.  Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OptionContract:
    symbol: str
    expiry: str           # ISO "YYYY-MM-DD"
    dte: int
    strike: float
    right: str            # "C" or "P"
    bid: float
    ask: float
    delta: float          # signed (negative for puts)
    gamma: float
    theta: float
    vega: float
    iv: float             # decimal: 0.25 = 25%
    open_interest: int
    volume: int
    underlying_price: float

    @property
    def mid(self) -> float:
        return round((self.bid + self.ask) / 2.0, 4)

    @property
    def spread_pct(self) -> float:
        if self.mid <= 0.0:
            return 9999.0
        return round((self.ask - self.bid) / self.mid * 100.0, 3)

    @property
    def delta_abs(self) -> float:
        return abs(self.delta)


@dataclass
class FilterParams:
    """Hard-filter thresholds. Defaults match PROJECT_OPZ_COMPLETE_V2 §12."""
    min_dte: int          = DEFAULT_MIN_DTE
    max_dte: int          = DEFAULT_MAX_DTE
    min_oi: int           = DEFAULT_MIN_OI
    max_spread_pct: float = DEFAULT_MAX_SPREAD_PCT
    min_volume: int       = DEFAULT_MIN_VOLUME
    min_ivr: float        = DEFAULT_MIN_IVR
    delta_min: float      = DELTA_LONG_MIN
    delta_max: float      = DELTA_LONG_MAX


@dataclass
class FilterRejectStats:
    total_raw: int  = 0
    spread_pct: int = 0
    oi_low: int     = 0
    dte_out: int    = 0
    volume_low: int = 0
    delta_out: int  = 0
    iv_missing: int = 0

    @property
    def total_rejected(self) -> int:
        return (
            self.spread_pct + self.oi_low + self.dte_out
            + self.volume_low + self.delta_out + self.iv_missing
        )


@dataclass
class ChainFilterResult:
    symbol: str
    profile: str
    data_mode: str
    fetched_at: str                        # UTC ISO timestamp
    expiry: str                            # primary expiry used
    dte: int
    underlying_price: float
    contracts_raw: int
    contracts_kept: list[OptionContract]   = field(default_factory=list)
    reject_stats: FilterRejectStats        = field(default_factory=FilterRejectStats)
    data_quality: str                      = "unknown"   # real_time|cache|stale|synthetic
    source: str                            = "unknown"   # ibkr_paper|ibkr_live|csv_delayed
    cache_age_hours: Optional[float]       = None
    error: Optional[str]                   = None


@dataclass
class ChainAnalytics:
    symbol: str
    expiry: str
    underlying_price: float
    # Expected Move (from ATM straddle)
    expected_move: Optional[float]       = None   # decimal: 0.035 = 3.5%
    expected_move_abs: Optional[float]   = None   # $ terms
    atm_strike: Optional[float]          = None
    atm_call_mid: Optional[float]        = None
    atm_put_mid: Optional[float]         = None
    # IV Z-Scores
    iv_current: Optional[float]          = None   # ATM IV decimal
    iv_zscore_30: Optional[float]        = None
    iv_zscore_60: Optional[float]        = None
    iv_interp_30: str                    = "unknown"  # cheap|fair|expensive|unknown
    iv_interp_60: str                    = "unknown"
    history_len_30: Optional[int]        = None
    history_len_60: Optional[int]        = None


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Cache helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(symbol: str) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"option_chain_{symbol.upper()}_{today}.json"


def _load_cache(symbol: str) -> tuple[list[OptionContract], float] | tuple[None, None]:
    """Return (contracts, age_hours) if cache exists and is within TTL, else (None, None)."""
    path = _cache_path(symbol)
    if not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        captured_str = data.get("captured_at")
        if not captured_str:
            return None, None
        captured = datetime.fromisoformat(captured_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_hours = (now - captured).total_seconds() / 3600.0
        if age_hours > CACHE_TTL_HOURS:
            return None, None  # stale — caller should mark data_quality = "stale"

        raw_contracts = data.get("contracts", [])
        contracts: list[OptionContract] = []
        for c in raw_contracts:
            try:
                contracts.append(OptionContract(**c))
            except Exception:
                continue
        return contracts, round(age_hours, 2)
    except Exception:
        return None, None


def _save_cache(symbol: str, contracts: list[OptionContract]) -> None:
    """Persist chain snapshot to JSON cache."""
    path = _cache_path(symbol)
    now = datetime.now(timezone.utc)
    payload = {
        "symbol": symbol.upper(),
        "captured_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(hours=CACHE_TTL_HOURS)).isoformat().replace("+00:00", "Z"),
        "contracts": [asdict(c) for c in contracts],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Hard Filters
# ─────────────────────────────────────────────────────────────────────────────

def apply_hard_filters(
    contracts: list[OptionContract],
    params: FilterParams | None = None,
) -> tuple[list[OptionContract], FilterRejectStats]:
    """
    Apply hard filters per PROJECT_OPZ_COMPLETE_V2 §12 and CLAUDE.md invariants.

    Returns (kept, reject_stats). Order of filters: IV → DTE → spread → OI → volume → delta.
    A contract failing any filter is excluded; stats track first-hit reason.
    """
    if params is None:
        params = FilterParams()

    stats = FilterRejectStats(total_raw=len(contracts))
    kept: list[OptionContract] = []

    for c in contracts:
        # IV missing / non-positive
        if c.iv <= 0.0 or math.isnan(c.iv):
            stats.iv_missing += 1
            continue
        # DTE out of range (HARD bounds take priority over preferred params)
        effective_min = max(params.min_dte, HARD_MIN_DTE)
        effective_max = min(params.max_dte, HARD_MAX_DTE)
        if c.dte < effective_min or c.dte > effective_max:
            stats.dte_out += 1
            continue
        # Spread too wide
        if c.spread_pct > params.max_spread_pct:
            stats.spread_pct += 1
            continue
        # Open interest too low
        if c.open_interest < params.min_oi:
            stats.oi_low += 1
            continue
        # Volume too low
        if c.volume < params.min_volume:
            stats.volume_low += 1
            continue
        # Delta out of target range (uses absolute value)
        d_abs = c.delta_abs
        if d_abs < params.delta_min or d_abs > params.delta_max:
            stats.delta_out += 1
            continue
        kept.append(c)

    return kept, stats


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Analytics — IV Z-Score and Expected Move
# ─────────────────────────────────────────────────────────────────────────────

def compute_iv_zscore(
    iv_current: float,
    iv_history: list[float],
    window: int,
) -> float | None:
    """
    Return IV Z-Score: (IV_today − mean(history[-window:])) / std(history[-window:]).

    Returns None if history is too short (< window) or std = 0.
    iv_current and iv_history values are in the same units (decimal or %).
    """
    if not iv_history or len(iv_history) < window:
        return None
    window_vals = iv_history[-window:]
    if len(window_vals) < 2:
        return None
    try:
        mu = statistics.mean(window_vals)
        sigma = statistics.stdev(window_vals)
        if sigma <= 0.0:
            return None
        return round((iv_current - mu) / sigma, 4)
    except Exception:
        return None


def _interpret_zscore(z: float | None) -> str:
    if z is None:
        return "unknown"
    if z < Z_CHEAP_THRESHOLD:
        return "cheap"
    if z > Z_EXPENSIVE_THRESHOLD:
        return "expensive"
    return "fair"


def compute_expected_move(
    contracts: list[OptionContract],
    underlying_price: float,
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """
    Compute Expected Move from ATM straddle: (call_mid + put_mid) / underlying.

    Uses the strike closest to underlying_price from the filtered contract list.
    Returns (em_decimal, em_abs, atm_strike, call_mid, put_mid).
    """
    if not contracts or underlying_price <= 0.0:
        return None, None, None, None, None

    strikes = sorted({c.strike for c in contracts})
    if not strikes:
        return None, None, None, None, None

    # Find ATM strike: closest to underlying
    atm_strike = min(strikes, key=lambda s: abs(s - underlying_price))

    # Collect ATM call and put
    atm_contracts = [c for c in contracts if c.strike == atm_strike]
    atm_call = next((c for c in atm_contracts if c.right == "C"), None)
    atm_put = next((c for c in atm_contracts if c.right == "P"), None)

    if atm_call is None or atm_put is None:
        return None, None, atm_strike, None, None

    call_mid = atm_call.mid
    put_mid = atm_put.mid

    if call_mid <= 0.0 or put_mid <= 0.0:
        return None, None, atm_strike, call_mid, put_mid

    em_abs = round(call_mid + put_mid, 4)
    em_decimal = round(em_abs / underlying_price, 6)
    return em_decimal, em_abs, atm_strike, call_mid, put_mid


def compute_chain_analytics(
    result: ChainFilterResult,
    iv_history: list[float] | None = None,
) -> ChainAnalytics:
    """
    Compute IV Z-Score (30d, 60d) and Expected Move from a ChainFilterResult.

    iv_history : list of historical ATM IV values (decimal), most recent last.
                 Provided by scripts/fetch_iv_history.py (ROC0-T3).
                 If None or too short, Z-Scores return None (graceful degradation).
    """
    analytics = ChainAnalytics(
        symbol=result.symbol,
        expiry=result.expiry,
        underlying_price=result.underlying_price,
    )

    if not result.contracts_kept:
        return analytics

    # ── Expected Move ──────────────────────────────────────────────────────
    em_dec, em_abs, atm_str, c_mid, p_mid = compute_expected_move(
        result.contracts_kept, result.underlying_price
    )
    analytics.expected_move = em_dec
    analytics.expected_move_abs = em_abs
    analytics.atm_strike = atm_str
    analytics.atm_call_mid = c_mid
    analytics.atm_put_mid = p_mid

    # ── ATM IV (used as iv_current for Z-Score) ────────────────────────────
    if atm_str is not None:
        atm_c = next((c for c in result.contracts_kept if c.strike == atm_str and c.right == "C"), None)
        atm_p = next((c for c in result.contracts_kept if c.strike == atm_str and c.right == "P"), None)
        # Prefer call IV for ATM; average if both available
        iv_vals = [x.iv for x in (atm_c, atm_p) if x is not None and x.iv > 0]
        if iv_vals:
            analytics.iv_current = round(sum(iv_vals) / len(iv_vals), 6)

    # ── IV Z-Scores ────────────────────────────────────────────────────────
    if iv_history and analytics.iv_current is not None:
        z30 = compute_iv_zscore(analytics.iv_current, iv_history, 30)
        z60 = compute_iv_zscore(analytics.iv_current, iv_history, 60)
        analytics.iv_zscore_30 = z30
        analytics.iv_zscore_60 = z60
        analytics.iv_interp_30 = _interpret_zscore(z30)
        analytics.iv_interp_60 = _interpret_zscore(z60)
        analytics.history_len_30 = min(len(iv_history), 30)
        analytics.history_len_60 = min(len(iv_history), 60)

    return analytics


# ─────────────────────────────────────────────────────────────────────────────
# 5.  CSV Fetch  (dev / fallback)
# ─────────────────────────────────────────────────────────────────────────────

_CHAIN_CSV_REQUIRED = [
    "symbol", "expiry", "strike", "right",
    "bid", "ask", "delta", "gamma", "theta", "vega", "iv",
    "open_interest", "volume", "underlying_price",
]


def _dte(expiry_iso: str, asof: date | None = None) -> int:
    d = date.fromisoformat(expiry_iso)
    ref = asof or datetime.now(timezone.utc).date()
    return max(0, (d - ref).days)


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        f = float(val)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _fetch_chain_csv(
    symbol: str,
    min_dte: int = HARD_MIN_DTE,
    max_dte: int = HARD_MAX_DTE,
) -> tuple[list[OptionContract], float]:
    """
    Load chain from data/providers/chain_{SYMBOL}.csv.

    CSV schema (required columns):
        symbol, expiry, strike, right, bid, ask, delta, gamma, theta, vega,
        iv, open_interest, volume, underlying_price
    Optional: observed_at_utc

    Returns (contracts, underlying_price). underlying_price = median of rows.
    """
    path = CHAIN_CSV_DIR / f"chain_{symbol.upper()}.csv"
    if not path.exists():
        return [], 0.0

    contracts: list[OptionContract] = []
    today = datetime.now(timezone.utc).date()

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = [k for k in _CHAIN_CSV_REQUIRED if k not in (reader.fieldnames or [])]
        if missing:
            return [], 0.0

        for row in reader:
            sym = str(row.get("symbol") or "").strip().upper()
            if sym and sym != symbol.upper():
                continue
            try:
                expiry_str = str(row["expiry"]).strip()
                dte_val = _dte(expiry_str, today)
                if dte_val < min_dte or dte_val > max_dte:
                    continue
                contracts.append(OptionContract(
                    symbol=symbol.upper(),
                    expiry=expiry_str,
                    dte=dte_val,
                    strike=_safe_float(row["strike"]),
                    right=str(row["right"]).strip().upper(),
                    bid=_safe_float(row["bid"]),
                    ask=_safe_float(row["ask"]),
                    delta=_safe_float(row["delta"]),
                    gamma=_safe_float(row["gamma"]),
                    theta=_safe_float(row["theta"]),
                    vega=_safe_float(row["vega"]),
                    iv=_safe_float(row["iv"]),
                    open_interest=_safe_int(row["open_interest"]),
                    volume=_safe_int(row["volume"]),
                    underlying_price=_safe_float(row["underlying_price"]),
                ))
            except Exception:
                continue

    underlying_price = 0.0
    if contracts:
        prices = [c.underlying_price for c in contracts if c.underlying_price > 0]
        if prices:
            underlying_price = statistics.median(prices)

    return contracts, underlying_price


# ─────────────────────────────────────────────────────────────────────────────
# 6.  IBKR Fetch  (paper / live)
# ─────────────────────────────────────────────────────────────────────────────

def _tcp_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _fetch_chain_ibkr(
    symbol: str,
    profile: str,
    config: dict[str, Any],
    min_dte: int = DEFAULT_MIN_DTE,
    max_dte: int = DEFAULT_MAX_DTE,
) -> tuple[list[OptionContract], float]:
    """
    Fetch option chain from IBKR TWS (paper or live).

    Uses reqSecDefOptParams to enumerate strikes/expiries, then
    reqMktData(snapshot=True) in batch for the filtered strike set.

    Returns (contracts, underlying_price).
    Raises RuntimeError on connectivity / dependency failure (caller falls back).
    """
    broker = config.get("broker", {})
    host = str(broker.get("host", "127.0.0.1"))
    port = int(broker.get("port", 7496))
    timeout_sec = float(config.get("phase0", {}).get("ibkr_timeout_sec", 10))

    if not _tcp_reachable(host, port, timeout=min(3.0, timeout_sec)):
        raise RuntimeError(f"TWS unreachable at {host}:{port}")

    try:
        from ib_insync import IB, Option, Stock  # type: ignore
    except Exception as e:
        raise RuntimeError(f"ib_insync not available: {e}") from e

    ib = IB()
    try:
        ib.connect(
            host, port,
            clientId=CHAIN_SNAPSHOT_CLIENT_ID,
            timeout=timeout_sec,
            readonly=True,
        )

        # ── Underlying price ──────────────────────────────────────────────
        stock = Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(stock)
        stk_ticker = ib.reqMktData(stock, "", snapshot=True, regulatorySnapshot=False)
        ib.sleep(2)
        underlying_price = float(
            stk_ticker.last or stk_ticker.close or stk_ticker.bid or 0.0
        )

        # ── Option chain params ───────────────────────────────────────────
        params = ib.reqSecDefOptParams(
            stock.symbol, "", stock.secType, stock.conId
        )
        if not params:
            raise RuntimeError(f"No option params for {symbol}")

        # Pick best params set (most complete strikes)
        best = max(
            params,
            key=lambda p: len(list(getattr(p, "strikes", []) or [])),
        )

        # ── Pick expiry in [min_dte, max_dte] ─────────────────────────────
        today = datetime.now(timezone.utc).date()
        expiries_raw = sorted(getattr(best, "expirations", []) or [])
        chosen_exp_yyyymmdd: str | None = None
        chosen_dte: int = 0
        for e in expiries_raw:
            try:
                d = datetime.strptime(e, "%Y%m%d").date()
                dte_val = (d - today).days
                if min_dte <= dte_val <= max_dte:
                    chosen_exp_yyyymmdd = e
                    chosen_dte = dte_val
                    break
            except Exception:
                continue
        if chosen_exp_yyyymmdd is None:
            raise RuntimeError(f"No expiry in [{min_dte}, {max_dte}] DTE for {symbol}")

        chosen_exp_iso = datetime.strptime(chosen_exp_yyyymmdd, "%Y%m%d").date().isoformat()

        # ── Filter strikes: ATM ±25% of underlying ────────────────────────
        all_strikes = sorted(
            float(s) for s in (getattr(best, "strikes", []) or [])
            if str(s).strip() != ""
        )
        if underlying_price > 0.0:
            lo = underlying_price * 0.75
            hi = underlying_price * 1.25
            target_strikes = [s for s in all_strikes if lo <= s <= hi]
        else:
            target_strikes = all_strikes[:40]  # fallback: first 40

        if not target_strikes:
            raise RuntimeError(f"No strikes in ATM ±25% range for {symbol}")

        # ── Batch reqMktData ──────────────────────────────────────────────
        opt_contracts = []
        for strike in target_strikes:
            for right in ("C", "P"):
                opt_contracts.append(
                    Option(symbol, chosen_exp_yyyymmdd, strike, right, "SMART", currency="USD")
                )
        ib.qualifyContracts(*opt_contracts)

        tickers = [
            ib.reqMktData(opt, "", snapshot=True, regulatorySnapshot=False)
            for opt in opt_contracts
        ]
        ib.sleep(3)  # wait for snapshot data to populate

        # ── Parse tickers → OptionContract ───────────────────────────────
        contracts: list[OptionContract] = []
        for opt, ticker in zip(opt_contracts, tickers):
            bid = float(ticker.bid) if ticker.bid is not None and math.isfinite(float(ticker.bid or -1)) and float(ticker.bid or -1) >= 0 else 0.0
            ask = float(ticker.ask) if ticker.ask is not None and math.isfinite(float(ticker.ask or -1)) and float(ticker.ask or -1) >= 0 else 0.0
            if ask <= 0.0:
                continue
            greeks = ticker.modelGreeks or ticker.lastGreeks or None
            delta = float(getattr(greeks, "delta", 0.0) or 0.0) if greeks else 0.0
            gamma = float(getattr(greeks, "gamma", 0.0) or 0.0) if greeks else 0.0
            theta = float(getattr(greeks, "theta", 0.0) or 0.0) if greeks else 0.0
            vega  = float(getattr(greeks, "vega", 0.0) or 0.0) if greeks else 0.0
            iv    = float(getattr(greeks, "impliedVol", 0.0) or 0.0) if greeks else 0.0
            oi    = _safe_int(getattr(ticker, "openInterest", 0) or 0)
            vol   = _safe_int(getattr(ticker, "volume", 0) or 0)
            contracts.append(OptionContract(
                symbol=symbol.upper(),
                expiry=chosen_exp_iso,
                dte=chosen_dte,
                strike=float(opt.strike),
                right=str(opt.right).upper(),
                bid=bid,
                ask=ask,
                delta=delta,
                gamma=gamma,
                theta=theta,
                vega=vega,
                iv=iv,
                open_interest=oi,
                volume=vol,
                underlying_price=underlying_price,
            ))

        return contracts, underlying_price

    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 7.  Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def fetch_and_filter_chain(
    symbol: str,
    profile: str = "dev",
    *,
    params: FilterParams | None = None,
    use_cache: bool = True,
    config: dict[str, Any] | None = None,
    min_dte: int = DEFAULT_MIN_DTE,
    max_dte: int = DEFAULT_MAX_DTE,
) -> ChainFilterResult:
    """
    Fetch option chain for a single symbol and apply hard filters.

    Pipeline:
      1. Cache lookup  (if use_cache=True and cache is fresh)
      2. IBKR fetch    (paper/live only; skipped in dev or if TWS unreachable)
      3. CSV fallback  (dev always; paper/live on IBKR failure)
      4. Apply hard filters (FilterParams)
      5. Save cache    (if new IBKR data and profile != dev)

    Returns ChainFilterResult with contracts_kept ready for analytics.
    """
    sym = symbol.upper()
    data_mode = os.environ.get("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Resolve FilterParams: upgrade min_oi for paper/live
    if params is None:
        params = FilterParams(min_dte=min_dte, max_dte=max_dte)
        if profile in ("paper", "live"):
            params = FilterParams(
                min_dte=min_dte,
                max_dte=max_dte,
                min_oi=PAPER_LIVE_MIN_OI,
                max_spread_pct=DEFAULT_MAX_SPREAD_PCT,
                min_volume=DEFAULT_MIN_VOLUME,
                min_ivr=DEFAULT_MIN_IVR,
                delta_min=DELTA_LONG_MIN,
                delta_max=DELTA_LONG_MAX,
            )

    raw_contracts: list[OptionContract] = []
    underlying_price: float = 0.0
    data_quality: str = "synthetic"
    source: str = "csv_delayed"
    cache_age_hours: float | None = None
    fetch_error: str | None = None

    # ── Step 1: Cache lookup ─────────────────────────────────────────────────
    if use_cache and profile in ("paper", "live"):
        cached, age = _load_cache(sym)
        if cached is not None and age is not None:
            raw_contracts = cached
            cache_age_hours = age
            data_quality = "cache"
            source = f"ibkr_{profile}"
            up_prices = [c.underlying_price for c in raw_contracts if c.underlying_price > 0]
            underlying_price = statistics.median(up_prices) if up_prices else 0.0

    # ── Step 2: IBKR fetch (paper/live only, cache miss) ────────────────────
    if not raw_contracts and profile in ("paper", "live"):
        try:
            cfg = config or {}
            raw_contracts, underlying_price = _fetch_chain_ibkr(
                sym, profile, cfg, min_dte=min_dte, max_dte=max_dte
            )
            data_quality = "real_time"
            source = f"ibkr_{profile}"
            # Auto-save cache for next call
            if raw_contracts:
                try:
                    _save_cache(sym, raw_contracts)
                except Exception:
                    pass  # cache write failure is non-fatal
        except Exception as e:
            fetch_error = f"IBKR fetch failed: {e} — falling back to CSV"
            raw_contracts = []

    # ── Step 3: CSV fallback ─────────────────────────────────────────────────
    if not raw_contracts:
        raw_contracts, underlying_price = _fetch_chain_csv(
            sym, min_dte=min_dte, max_dte=max_dte
        )
        data_quality = "synthetic"
        source = "csv_delayed"

    # ── Determine primary expiry from fetched contracts ──────────────────────
    primary_expiry = ""
    primary_dte = 0
    if raw_contracts:
        # Pick the expiry with the most contracts (best coverage)
        from collections import Counter
        exp_counts = Counter(c.expiry for c in raw_contracts)
        if exp_counts:
            primary_expiry = exp_counts.most_common(1)[0][0]
            primary_dte_vals = [c.dte for c in raw_contracts if c.expiry == primary_expiry]
            primary_dte = primary_dte_vals[0] if primary_dte_vals else 0

    # ── Step 4: Apply hard filters ───────────────────────────────────────────
    kept, stats = apply_hard_filters(raw_contracts, params)

    return ChainFilterResult(
        symbol=sym,
        profile=profile,
        data_mode=data_mode,
        fetched_at=now_iso,
        expiry=primary_expiry,
        dte=primary_dte,
        underlying_price=round(underlying_price, 4),
        contracts_raw=len(raw_contracts),
        contracts_kept=kept,
        reject_stats=stats,
        data_quality=data_quality,
        source=source,
        cache_age_hours=cache_age_hours,
        error=fetch_error,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8.  ScanResult + OpportunityCandidate dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OpportunityCandidate:
    """Single ranked opportunity output from scan_opportunities()."""
    symbol: str
    strategy: str                          # BULL_PUT | BULL_CALL | IRON_CONDOR | STRADDLE
    score: float                           # 0–100
    score_breakdown: dict                  # {vol_edge, liquidity, risk_reward, regime_align}
    expiry: str                            # ISO date
    dte: int
    strikes: list                          # strike(s) involved (short, long or [atm])
    delta: float                           # primary leg delta (abs)
    iv: float                              # ATM IV decimal
    iv_zscore_30: Optional[float]
    iv_zscore_60: Optional[float]
    iv_interp: str                         # cheap | fair | expensive | unknown
    expected_move: Optional[float]         # decimal (0.035 = 3.5%)
    signal_vs_em_ratio: Optional[float]    # technical_signal_pct / EM; None if no signal
    spread_pct: float                      # primary leg bid-ask spread %
    open_interest: int                     # primary leg OI
    volume: int                            # primary leg volume
    max_loss: float                        # absolute $ (positive)
    max_loss_pct: float                    # % of account capital
    breakeven: float                       # $ breakeven price
    breakeven_pct: float                   # % from current spot
    credit_or_debit: float                 # positive=credit received, negative=debit paid
    sizing_suggested: float                # % of account (Adaptive Fixed Fractional)
    kelly_fraction: Optional[float]        # None until Kelly gate unlocked
    events_flag: Optional[str]             # EARNINGS_2D | EARNINGS_7D | DIVIDEND_5D | None
    human_review_required: bool            # True if signal > 2× EM
    stress_base: float                     # P&L estimate at VIX+30%
    stress_shock: float                    # P&L estimate at VIX+100%
    data_quality: str                      # real_time | cache | stale | synthetic
    source: str                            # ibkr_paper | ibkr_live | csv_delayed
    underlying_price: float


@dataclass
class ScanResult:
    """Output of scan_opportunities(): ranked list + audit metadata."""
    profile: str
    regime: str
    data_mode: str                         # DATA_MODE watermark
    scan_ts: str                           # UTC ISO timestamp
    symbols_scanned: int
    symbols_with_chain: int
    filtered_count: int                    # total contracts rejected by hard filters
    cache_used: bool
    cache_age_hours: Optional[float]
    candidates: list                       # list[OpportunityCandidate]
    ranking_suspended: bool
    suspension_reason: Optional[str]
    events_source: str = "yfinance"        # "ibkr_live" | "yfinance" | "events_map" | "none"


# ─────────────────────────────────────────────────────────────────────────────
# 9.  Strategy selector
# ─────────────────────────────────────────────────────────────────────────────

_STRATEGY_BULL_PUT   = "BULL_PUT"
_STRATEGY_BULL_CALL  = "BULL_CALL"
_STRATEGY_IRON_CONDOR = "IRON_CONDOR"
_STRATEGY_STRADDLE   = "STRADDLE"

_BASE_SIZING_PCT = 2.0   # % of account (Adaptive Fixed Fractional base)

def _select_strategy(
    regime: str,
    iv_zscore: Optional[float],
    signal: Optional[str],   # "bullish" | "bearish" | "neutral" | None
    ivr: Optional[float],    # 0–100
) -> str:
    """
    Select options strategy per PROJECT_OPZ_COMPLETE_V2 §2.1 Step 5.

    Precedence: regime → signal direction → IV Z-Score → IVR.
    CAUTION allows only narrow spreads → returns BULL_PUT (credit, defined-risk).
    """
    if regime == "SHOCK":
        return ""   # no strategy in SHOCK

    is_bullish  = signal in ("bullish", None)   # default bullish if no signal
    is_neutral  = signal == "neutral"

    z = iv_zscore if iv_zscore is not None else 0.0

    if regime == "CAUTION":
        # Only narrow credit spreads (defined-risk, vega-negative)
        return _STRATEGY_BULL_PUT

    # NORMAL regime
    if is_neutral and ivr is not None and ivr >= 45.0:
        return _STRATEGY_IRON_CONDOR

    if is_neutral:
        return _STRATEGY_STRADDLE

    if is_bullish:
        if z > Z_EXPENSIVE_THRESHOLD:
            return _STRATEGY_BULL_PUT   # IV high → sell premium
        if z < Z_CHEAP_THRESHOLD:
            return _STRATEGY_BULL_CALL  # IV low → buy debit spread
        return _STRATEGY_BULL_PUT       # default credit (IV fair, bullish)

    # bearish: mirror of bullish (beyond current scope — default to credit put)
    return _STRATEGY_BULL_PUT


# ─────────────────────────────────────────────────────────────────────────────
# 10.  Contract picker — choose primary leg(s) per strategy
# ─────────────────────────────────────────────────────────────────────────────

def _closest_delta(
    contracts: list[OptionContract],
    right: str,
    target_delta_abs: float,
) -> Optional[OptionContract]:
    """Return contract with |delta| closest to target_delta_abs."""
    candidates = [c for c in contracts if c.right == right]
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(c.delta_abs - target_delta_abs))


def _pick_spread_legs(
    contracts: list[OptionContract],
    strategy: str,
) -> tuple[Optional[OptionContract], Optional[OptionContract]]:
    """
    Pick (short_leg, long_leg) for spread strategies.

    Returns (None, None) if insufficient contracts.
    """
    if strategy == _STRATEGY_BULL_PUT:
        short = _closest_delta(contracts, "P", 0.30)
        # Long leg: lower delta (further OTM) than short
        if short is None:
            return None, None
        long_cands = [
            c for c in contracts
            if c.right == "P" and c.delta_abs < short.delta_abs and c.strike < short.strike
        ]
        if not long_cands:
            return short, None
        long = min(long_cands, key=lambda c: abs(c.delta_abs - 0.20))
        return short, long

    if strategy == _STRATEGY_BULL_CALL:
        short = _closest_delta(contracts, "C", 0.20)   # sell higher call
        long = _closest_delta(contracts, "C", 0.35)    # buy lower call (primary leg)
        return long, short   # long = primary (lower strike), short = hedge

    if strategy == _STRATEGY_STRADDLE:
        call = _closest_delta(contracts, "C", 0.50)
        put  = _closest_delta(contracts, "P", 0.50)
        return call, put

    if strategy == _STRATEGY_IRON_CONDOR:
        short_call = _closest_delta(contracts, "C", 0.30)
        short_put  = _closest_delta(contracts, "P", 0.30)
        return short_call, short_put   # simplified: just the two short legs

    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# 11.  Payoff + sizing approximations
# ─────────────────────────────────────────────────────────────────────────────

def _approx_payoff(
    strategy: str,
    short_leg: Optional[OptionContract],
    long_leg: Optional[OptionContract],
    underlying: float,
) -> tuple[float, float, float, float]:
    """
    Return (credit_or_debit, max_loss, breakeven, rr_ratio).
    All approximations for ranking purposes (not order-ready).
    Spread width default = 5 points when long_leg missing.
    """
    if short_leg is None:
        return 0.0, 9999.0, underlying, 0.0

    if strategy == _STRATEGY_BULL_PUT:
        credit = short_leg.mid - (long_leg.mid if long_leg else 0.0)
        width  = (short_leg.strike - long_leg.strike) if long_leg else 5.0
        max_loss = max(width - credit, 0.01) * 100   # per contract, 100x
        credit_per_contract = credit * 100
        breakeven = short_leg.strike - credit
        rr = credit / (width - credit) if (width - credit) > 0 else 0.0
        return credit_per_contract, max_loss, breakeven, rr

    if strategy == _STRATEGY_BULL_CALL:
        debit  = short_leg.mid - (long_leg.mid if long_leg else 0.0)
        # short_leg here is the higher-strike call hedge
        width  = (long_leg.strike - short_leg.strike) if long_leg else 5.0
        # For bull call: short=long-strike (higher), long=primary (lower)
        # Recompute: long_leg is the bought call, short_leg is the sold call
        if long_leg is not None:
            debit_paid = long_leg.mid - short_leg.mid
        else:
            debit_paid = short_leg.mid
        max_gain = max(width - debit_paid, 0.0) * 100
        max_loss = debit_paid * 100
        breakeven = (short_leg.strike + debit_paid) if long_leg is None else (long_leg.strike + debit_paid)
        rr = max_gain / max_loss if max_loss > 0 else 0.0
        return -debit_paid * 100, max_loss, breakeven, rr

    if strategy == _STRATEGY_STRADDLE:
        cost = ((short_leg.mid if short_leg else 0.0) +
                (long_leg.mid if long_leg else 0.0)) * 100
        breakeven_up   = (short_leg.strike if short_leg else underlying) + cost / 100
        breakeven_down = (short_leg.strike if short_leg else underlying) - cost / 100
        return -cost, cost, breakeven_up, 1.0   # report upper breakeven

    if strategy == _STRATEGY_IRON_CONDOR:
        credit_call = short_leg.mid if short_leg else 0.0
        credit_put  = long_leg.mid  if long_leg  else 0.0
        total_credit = (credit_call + credit_put) * 100
        width = 5.0  # assume 5-point wing width
        max_loss = (width - total_credit / 100) * 100
        breakeven = underlying   # simplified center
        rr = (total_credit / 100) / (width - total_credit / 100) if width > total_credit / 100 else 0.0
        return total_credit, max(max_loss, 0.01), breakeven, rr

    return 0.0, 9999.0, underlying, 0.0


def _stress_estimate(strategy: str, credit_or_debit: float, max_loss: float) -> tuple[float, float]:
    """
    Simplified stress scenario estimates.
    VIX+30%: assume 60% of max adverse move.
    VIX+100%: assume 95% of max loss for credit strategies; full debit for debit.
    """
    is_credit = credit_or_debit > 0
    if is_credit:
        stress_base  = -max_loss * 0.60
        stress_shock = -max_loss * 0.95
    else:
        loss = abs(credit_or_debit)
        stress_base  = -loss * 0.40
        stress_shock = -loss * 0.90
    return round(stress_base, 2), round(stress_shock, 2)


def _sizing_adaptive_fixed(regime: str) -> float:
    """Adaptive Fixed Fractional: base_pct × regime_multiplier."""
    multiplier = {"NORMAL": 1.0, "CAUTION": 0.5, "SHOCK": 0.0}.get(regime, 0.0)
    return round(_BASE_SIZING_PCT * multiplier, 2)


# ─────────────────────────────────────────────────────────────────────────────
# 12.  IVR proxy from IV history
# ─────────────────────────────────────────────────────────────────────────────

def _ivr_from_history(iv_current: float, iv_history: list[float], lookback: int = 252) -> Optional[float]:
    """
    IV Rank (0–100) from history: (iv_current - min_iv) / (max_iv - min_iv) * 100.
    Returns None if history too short (< 30 points).
    """
    if not iv_history or len(iv_history) < 30:
        return None
    window = iv_history[-lookback:] if len(iv_history) > lookback else iv_history
    mn, mx = min(window), max(window)
    if mx == mn:
        return 50.0
    rank = (iv_current - mn) / (mx - mn) * 100.0
    return round(max(0.0, min(100.0, rank)), 2)


# ─────────────────────────────────────────────────────────────────────────────
# 13.  Build OpportunityCandidate
# ─────────────────────────────────────────────────────────────────────────────

def _build_candidate(
    chain_result: ChainFilterResult,
    analytics: ChainAnalytics,
    strategy: str,
    regime: str,
    iv_history: list[float],
    account_size: float = 10_000.0,
    signal_pct: Optional[float] = None,   # technical signal expected move % (decimal)
    events_flag: Optional[str] = None,    # ROC2: "EARNINGS_2D"|"EARNINGS_7D"|"DIVIDEND_5D"|None
) -> Optional[OpportunityCandidate]:
    """
    Build an OpportunityCandidate from ChainFilterResult + ChainAnalytics.
    Returns None if insufficient data for scoring.
    """
    if not chain_result.contracts_kept:
        return None

    short_leg, long_leg = _pick_spread_legs(chain_result.contracts_kept, strategy)
    if short_leg is None:
        return None

    underlying = chain_result.underlying_price or analytics.underlying_price
    credit_or_debit, max_loss, breakeven, rr = _approx_payoff(
        strategy, short_leg, long_leg, underlying
    )

    # ── Score via existing 4-pillar scorer ───────────────────────────────
    iv_current = analytics.iv_current or short_leg.iv
    ivr = _ivr_from_history(iv_current, iv_history) if iv_history else None
    ivr_for_score = ivr if ivr is not None else 30.0   # safe default

    from strategy.scoring import compute_trade_score, Regime as SRegime
    try:
        score_result = compute_trade_score(
            ivr=ivr_for_score,
            bid_ask_spread_pct=short_leg.spread_pct,
            open_interest=short_leg.open_interest,
            rr=rr,
            regime=regime,
        )
    except Exception:
        return None

    if not score_result.accepted:
        return None

    score = round(score_result.score, 2)

    # Approximate score breakdown (regime component + inferred split)
    vol_edge_score   = round(min(100.0, ivr_for_score * 1.25), 2)
    liq_score        = round(max(0.0, 100.0 - short_leg.spread_pct * 5.0), 2)
    rr_score         = round(min(100.0, rr * 33.0), 2)
    regime_align     = 100.0 if regime == "NORMAL" else (50.0 if regime == "CAUTION" else 0.0)
    score_breakdown  = {
        "vol_edge": vol_edge_score,
        "liquidity": liq_score,
        "risk_reward": rr_score,
        "regime_align": regime_align,
    }

    # ── Signal vs EM ratio ────────────────────────────────────────────────
    em = analytics.expected_move
    signal_vs_em: Optional[float] = None
    if signal_pct is not None and em is not None and em > 0.0:
        signal_vs_em = round(signal_pct / em, 3)
    human_review = (signal_vs_em is not None and signal_vs_em > 2.0) or (events_flag == "EARNINGS_7D")

    # ── Stress + sizing ───────────────────────────────────────────────────
    stress_base, stress_shock = _stress_estimate(strategy, credit_or_debit, max_loss)
    sizing = _sizing_adaptive_fixed(regime)
    max_loss_pct = round(max_loss / account_size * 100.0, 3) if account_size > 0 else 0.0
    breakeven_pct = round((breakeven - underlying) / underlying * 100.0, 4) if underlying > 0 else 0.0

    # ── Strikes list ─────────────────────────────────────────────────────
    strikes = [short_leg.strike]
    if long_leg is not None:
        strikes.append(long_leg.strike)

    z30 = analytics.iv_zscore_30
    iv_interp = analytics.iv_interp_30 if z30 is not None else analytics.iv_interp_60

    return OpportunityCandidate(
        symbol=chain_result.symbol,
        strategy=strategy,
        score=score,
        score_breakdown=score_breakdown,
        expiry=chain_result.expiry,
        dte=chain_result.dte,
        strikes=sorted(strikes),
        delta=short_leg.delta_abs,
        iv=iv_current,
        iv_zscore_30=z30,
        iv_zscore_60=analytics.iv_zscore_60,
        iv_interp=iv_interp,
        expected_move=em,
        signal_vs_em_ratio=signal_vs_em,
        spread_pct=short_leg.spread_pct,
        open_interest=short_leg.open_interest,
        volume=short_leg.volume,
        max_loss=round(max_loss, 2),
        max_loss_pct=max_loss_pct,
        breakeven=round(breakeven, 4),
        breakeven_pct=breakeven_pct,
        credit_or_debit=round(credit_or_debit, 2),
        sizing_suggested=sizing,
        kelly_fraction=None,   # Kelly gate not unlocked in dev/paper
        events_flag=events_flag,
        human_review_required=human_review,
        stress_base=stress_base,
        stress_shock=stress_shock,
        data_quality=chain_result.data_quality,
        source=chain_result.source,
        underlying_price=underlying,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 14.  scan_opportunities — main entry point
# ─────────────────────────────────────────────────────────────────────────────

def scan_opportunities(
    profile: str = "dev",
    regime: str = "NORMAL",
    symbols: list[str] | None = None,
    *,
    top_n: int = 5,
    signal_map: dict[str, str] | None = None,     # symbol → "bullish"|"bearish"|"neutral"
    signal_pct_map: dict[str, float] | None = None, # symbol → expected_move_pct (decimal)
    params: FilterParams | None = None,
    use_cache: bool = True,
    config: dict[str, Any] | None = None,
    account_size: float = 10_000.0,
    iv_history_map: dict[str, list[float]] | None = None,  # pre-loaded; if None → load from files
    events_map: dict[str, Any] | None = None,  # ROC2: symbol → EventCheckResult; None → auto-fetch
    min_dte: int = DEFAULT_MIN_DTE,
    max_dte: int = DEFAULT_MAX_DTE,
    min_score: float = 60.0,
) -> ScanResult:
    """
    Full opportunity scan pipeline per PROJECT_OPZ_COMPLETE_V2 §2.1.

    For each symbol:
      1. Load IV history (file or synthetic fallback)
      2. fetch_and_filter_chain() → ChainFilterResult
      3. compute_chain_analytics() → ChainAnalytics
      4. Select strategy (regime + IV Z-Score + signal)
      5. Build OpportunityCandidate (score via 4 pillars)

    Returns ScanResult with candidates ranked by score desc (top_n max).
    SHOCK → ranking_suspended=True, empty candidates.
    """
    from scripts.fetch_iv_history import load_iv_history  # lazy to avoid circular import

    scan_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    data_mode = os.environ.get("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

    # SHOCK circuit breaker
    if regime == "SHOCK":
        return ScanResult(
            profile=profile,
            regime=regime,
            data_mode=data_mode,
            scan_ts=scan_ts,
            symbols_scanned=0,
            symbols_with_chain=0,
            filtered_count=0,
            cache_used=False,
            cache_age_hours=None,
            candidates=[],
            ranking_suspended=True,
            suspension_reason="SHOCK regime — no new positions allowed",
            events_source="none",
        )

    if symbols is None or len(symbols) == 0:
        return ScanResult(
            profile=profile,
            regime=regime,
            data_mode=data_mode,
            scan_ts=scan_ts,
            symbols_scanned=0,
            symbols_with_chain=0,
            filtered_count=0,
            cache_used=use_cache,
            cache_age_hours=None,
            candidates=[],
            ranking_suspended=False,
            suspension_reason=None,
            events_source="none",
        )

    # ── Determina events_source prima del loop ────────────────────────────
    if events_map is not None:
        _events_source = "events_map"
    else:
        try:
            from execution.ibkr_connection import get_manager as _get_ibkr_mgr
            _events_source = "ibkr_live" if _get_ibkr_mgr().is_connected else "yfinance"
        except Exception:
            _events_source = "yfinance"

    candidates: list[OpportunityCandidate] = []
    total_filtered = 0
    symbols_with_chain = 0
    cache_ages: list[float] = []

    for sym in symbols:
        sym = sym.upper()

        # ── IV history ───────────────────────────────────────────────────
        if iv_history_map and sym in iv_history_map:
            iv_hist = iv_history_map[sym]
        else:
            iv_hist = load_iv_history(sym)

        # ── Chain fetch + filter ─────────────────────────────────────────
        chain_result = fetch_and_filter_chain(
            sym, profile,
            params=params,
            use_cache=use_cache,
            config=config,
            min_dte=min_dte,
            max_dte=max_dte,
        )

        total_filtered += chain_result.reject_stats.total_rejected
        if chain_result.cache_age_hours is not None:
            cache_ages.append(chain_result.cache_age_hours)

        if not chain_result.contracts_kept:
            continue

        symbols_with_chain += 1

        # ── Analytics ────────────────────────────────────────────────────
        analytics = compute_chain_analytics(chain_result, iv_history=iv_hist or None)

        # ── Strategy selection ───────────────────────────────────────────
        signal = (signal_map or {}).get(sym)
        iv_current = analytics.iv_current
        ivr = _ivr_from_history(iv_current, iv_hist) if (iv_current and iv_hist) else None
        strategy = _select_strategy(
            regime=regime,
            iv_zscore=analytics.iv_zscore_30,
            signal=signal,
            ivr=ivr,
        )
        if not strategy:
            continue

        # ── Events check (ROC2 + ROC4) ───────────────────────────────────
        ev_flag: Optional[str] = None
        if events_map is not None and sym in events_map:
            ev = events_map[sym]
        else:
            try:
                # ROC4: usa IBKR se connesso, yfinance altrimenti
                from execution.ibkr_connection import get_manager as _get_ibkr_manager
                _ibkr = _get_ibkr_manager()
                if _ibkr.is_connected:
                    ev = _ibkr.get_events_for_symbol(sym)
                else:
                    from scripts.events_calendar import check_events as _check_events
                    ev = _check_events(sym)
            except Exception:
                ev = None

        if ev is not None:
            if ev.block_trade:
                # EARNINGS_2D → blocco totale, nessun candidato per questo simbolo
                continue
            # EARNINGS_7D → nessuna strategia long-gamma
            if ev.restrict_long_gamma:
                from scripts.events_calendar import LONG_GAMMA_STRATEGIES
                if strategy in LONG_GAMMA_STRATEGIES:
                    strategy = _STRATEGY_BULL_PUT
            # Flag per il candidato (earnings ha priorità su dividendo)
            from scripts.events_calendar import combined_events_flag
            ev_flag = combined_events_flag(ev)

        # ── Build candidate ──────────────────────────────────────────────
        spct = (signal_pct_map or {}).get(sym)
        candidate = _build_candidate(
            chain_result=chain_result,
            analytics=analytics,
            strategy=strategy,
            regime=regime,
            iv_history=iv_hist or [],
            account_size=account_size,
            signal_pct=spct,
            events_flag=ev_flag,
        )
        if candidate is not None:
            candidates.append(candidate)

    # ── Sort by score, take top_n ────────────────────────────────────────
    candidates.sort(key=lambda c: c.score, reverse=True)
    top_candidates = [c for c in candidates if c.score >= min_score][:top_n]

    cache_used = bool(cache_ages)
    avg_cache_age: Optional[float] = (
        round(sum(cache_ages) / len(cache_ages), 2) if cache_ages else None
    )

    return ScanResult(
        profile=profile,
        regime=regime,
        data_mode=data_mode,
        scan_ts=scan_ts,
        symbols_scanned=len(symbols),
        symbols_with_chain=symbols_with_chain,
        filtered_count=total_filtered,
        cache_used=cache_used,
        cache_age_hours=avg_cache_age,
        candidates=top_candidates,
        ranking_suspended=False,
        suspension_reason=None,
        events_source=_events_source,
    )
