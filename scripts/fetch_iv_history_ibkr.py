"""
scripts/fetch_iv_history_ibkr.py — ATM IV + greeks da IBKR via ib_insync

capture_ibkr_universe_snapshot(symbols, profile) → list[dict]
    Apre UNA connessione IBG e cattura snapshot per tutti i simboli.
    Per ogni simbolo: prezzo sottostante, catena opzioni (20-60 DTE), strike ATM,
    IV implicita ATM (call+put), greche ATM (delta, gamma, theta, vega).
    Errori per-simbolo NON bloccanti: ritorna partial con error field.

capture_ibkr_symbol_snapshot(sym, profile) → dict
    Wrapper single-symbol per compatibilità. Usa capture_ibkr_universe_snapshot.

merge_today_iv_point(sym, atm_iv) → None
    Sovrascrive il punto odierno nell'IV history JSON con il valore IBKR,
    mantenendo lo stesso formato usato da fetch_iv_history.py.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Black-Scholes IV fallback (Newton-Raphson)
# Usato quando IBKR non restituisce impliedVolatility (es. manca abbonamento OPRA)
# ─────────────────────────────────────────────────────────────────────────────

def _bs_price(S: float, K: float, T: float, r: float, sigma: float, right: str) -> float:
    """Prezzo Black-Scholes per call (C) o put (P)."""
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if right == "C" else (K - S))
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    if right == "C":
        return S * N(d1) - K * math.exp(-r * T) * N(d2)
    else:
        return K * math.exp(-r * T) * N(-d2) - S * N(-d1)


def _bs_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0:
        return 1e-8
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    N_prime = math.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)
    return S * N_prime * math.sqrt(T)


def _implied_vol_from_price(S: float, K: float, T: float, market_price: float,
                             right: str = "C", r: float = 0.05) -> Optional[float]:
    """
    Calcola IV implicita via Newton-Raphson dato il prezzo di mercato (mid bid/ask).
    Ritorna None se non converge o il prezzo non è valido.
    """
    if market_price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None
    intrinsic = max(0.0, (S - K) if right == "C" else (K - S))
    if market_price <= intrinsic:
        return None
    sigma = 0.3  # punto di partenza ragionevole
    for _ in range(50):
        price = _bs_price(S, K, T, r, sigma, right)
        vega = _bs_vega(S, K, T, r, sigma)
        diff = price - market_price
        if abs(diff) < 1e-6:
            break
        if vega < 1e-8:
            break
        sigma -= diff / vega
        if sigma <= 0:
            sigma = 1e-4
    return round(sigma, 6) if 0.001 < sigma < 20.0 else None

ROOT = Path(__file__).resolve().parents[1]
IV_HISTORY_DIR = ROOT / "data" / "providers"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        return None if f != f else f  # NaN guard
    except Exception:
        return None


def _history_path(symbol: str) -> Path:
    return IV_HISTORY_DIR / f"iv_history_{symbol.upper()}.json"


def _data_mode() -> str:
    return os.environ.get("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")


def _market_phase_ny(now_utc: Optional[datetime] = None) -> str:
    """pre | open | post | closed (timezone America/New_York)."""
    now_ref = now_utc or datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        now_ny = now_ref.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        # Fallback conservativo: senza timezone affidabile non inferiamo pre/post.
        return "closed"

    if now_ny.weekday() >= 5:
        return "closed"

    mins = now_ny.hour * 60 + now_ny.minute
    if mins < 9 * 60 + 30:
        return "pre"
    if mins < 16 * 60:
        return "open"
    return "post"


def _ibkr_connection_params(profile: str = "dev") -> tuple[str, list[int], int]:
    """Ritorna (host, ports, client_id) leggendo env vars + config profilo."""
    host = (os.environ.get("IBKR_HOST") or "127.0.0.1").strip()
    env_ports_raw = os.environ.get("IBKR_PORTS") or os.environ.get("IBKR_PORT") or ""
    env_ports = [int(p.strip()) for p in env_ports_raw.replace(";", ",").split(",")
                 if p.strip().isdigit()]
    ports = env_ports or [4004, 4002, 7497, 7496, 4001]
    default_client_id = "10"
    try:
        from execution.ibkr_connection import IBKR_CLIENT_ID as _DEFAULT_CLIENT_ID
        default_client_id = str(int(_DEFAULT_CLIENT_ID))
    except Exception:
        pass
    env_client_id_raw = os.environ.get("IBKR_CLIENT_ID")
    client_id = int(env_client_id_raw or default_client_id)

    manager_connected = False
    try:
        from execution.ibkr_connection import get_manager

        mgr = get_manager()
        # Controllo sempre stato/connessione prima di snapshot chain.
        mgr.try_connect(timeout=1.5)
        info = mgr.connection_info()
        if bool(info.get("connected")):
            manager_connected = True
            m_host = str(info.get("host") or "").strip()
            m_port = info.get("port")
            m_client_id = info.get("client_id")
            if m_host:
                host = m_host
            if m_port:
                p = int(m_port)
                ports = [p] + [x for x in ports if x != p]
            if m_client_id is not None:
                if env_client_id_raw:
                    client_id = int(env_client_id_raw)
                else:
                    client_id = int(m_client_id) + 1
    except Exception:
        pass

    try:
        from execution.config_loader import load_profile_config
        cfg = load_profile_config(profile)
        b = cfg.get("broker") or {}
        if not env_ports and not manager_connected:
            cfg_port = b.get("port")
            if cfg_port:
                ports = [int(cfg_port)] + [p for p in ports if p != int(cfg_port)]
        if not os.environ.get("IBKR_CLIENT_ID"):
            cfg_client_id = b.get("client_id")
            if cfg_client_id is not None and not manager_connected:
                client_id = int(cfg_client_id)
    except Exception:
        pass
    return host, ports, client_id


def _parse_expiry_yyyymmdd(exp_str: str) -> Optional[date]:
    s = str(exp_str or "").strip()
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except Exception:
        return None


def _select_regular_expiries(
    expirations: Iterable[str],
    *,
    min_dte: int = 7,
    max_dte: int = 240,
    center_day: int = 20,
    day_tolerance: int = 5,
    max_candidates: int = 8,
    today_ref: Optional[date] = None,
) -> list[tuple[str, date, int]]:
    """
    Select candidate expiries with preference for monthly-like regular dates.

    Regular monthly-like is approximated as day-of-month in
    [center_day-day_tolerance, center_day+day_tolerance].
    """
    today = today_ref or date.today()
    parsed: list[tuple[str, date, int]] = []
    for raw in expirations:
        exp_dt = _parse_expiry_yyyymmdd(str(raw))
        if exp_dt is None:
            continue
        dte = (exp_dt - today).days
        if dte < min_dte or dte > max_dte:
            continue
        parsed.append((exp_dt.strftime("%Y%m%d"), exp_dt, dte))
    parsed.sort(key=lambda x: x[1])
    if not parsed:
        return []

    lo = center_day - day_tolerance
    hi = center_day + day_tolerance
    regular = [x for x in parsed if lo <= x[1].day <= hi]
    pool = regular if regular else parsed
    return pool[: max(1, int(max_candidates))]


def _estimate_sigma_bands(
    underlying: float,
    atm_iv: Optional[float],
    dte: Optional[int],
) -> dict[str, Optional[float]]:
    if underlying <= 0.0 or atm_iv is None or atm_iv <= 0.0 or dte is None or dte <= 0:
        return {
            "sigma_1_abs": None,
            "sigma_1_up": None,
            "sigma_1_down": None,
            "sigma_2_abs": None,
            "sigma_2_up": None,
            "sigma_2_down": None,
        }
    t = float(dte) / 365.0
    if t <= 0.0:
        return {
            "sigma_1_abs": None,
            "sigma_1_up": None,
            "sigma_1_down": None,
            "sigma_2_abs": None,
            "sigma_2_up": None,
            "sigma_2_down": None,
        }
    sigma_1 = underlying * atm_iv * math.sqrt(t)
    sigma_2 = sigma_1 * 2.0
    return {
        "sigma_1_abs": round(sigma_1, 4),
        "sigma_1_up": round(underlying + sigma_1, 4),
        "sigma_1_down": round(max(0.0, underlying - sigma_1), 4),
        "sigma_2_abs": round(sigma_2, 4),
        "sigma_2_up": round(underlying + sigma_2, 4),
        "sigma_2_down": round(max(0.0, underlying - sigma_2), 4),
    }


def _ticker_iv(tkr: Any) -> Optional[float]:
    direct = _safe_float(getattr(tkr, "impliedVolatility", None))
    if direct and direct > 0:
        return direct
    for g_name in ("modelGreeks", "lastGreeks"):
        g = getattr(tkr, g_name, None)
        if g is None:
            continue
        val = _safe_float(getattr(g, "impliedVol", None))
        if val and val > 0:
            return val
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Core: snapshot per simbolo / universo
# ─────────────────────────────────────────────────────────────────────────────

def _empty_result(symbol: str, error: str) -> dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        "market_data_type": None,
        "underlying_price": None,
        "contracts_count": 0,
        "greeks_complete": 0,
        "atm_iv": None,
        "atm_strike": None,
        "expiry": None,
        "dte": None,
        "atm_call_iv": None,
        "atm_put_iv": None,
        "atm_delta": None,
        "atm_gamma": None,
        "atm_theta": None,
        "atm_vega": None,
        "error": error,
    }


def _snapshot_on_connection(ib: Any, symbol: str) -> dict[str, Any]:
    """
    Cattura snapshot per un singolo simbolo su una connessione IB già aperta.
    Non apre né chiude la connessione.
    """
    from ib_insync import Stock, Option

    result = _empty_result(symbol, None)

    try:
        # ── 1. Qualifica contratto sottostante ────────────────────────────────
        stock = Stock(symbol.upper(), "SMART", "USD")
        try:
            qualified = ib.qualifyContracts(stock)
            if not qualified:
                raise RuntimeError("qualifyContracts vuoto")
            stock = qualified[0]
        except Exception as exc:
            result["error"] = f"qualify fallito: {exc}"
            return result

        # ── 2. Prezzo sottostante ─────────────────────────────────────────────
        preferred_type = getattr(ib, "_qopz_market_data_type", None)
        tried_types: list[int] = []
        ordered_types = [preferred_type, 1, 3, 4]  # 1=live, 3=delayed, 4=delayed-frozen
        underlying: Optional[float] = None
        for mdt in ordered_types:
            if not isinstance(mdt, int) or mdt in tried_types:
                continue
            tried_types.append(mdt)
            try:
                ib.reqMarketDataType(mdt)
            except Exception:
                pass
            tkr = ib.reqMktData(stock, "", snapshot=True, regulatorySnapshot=False)
            ib.sleep(2.0)
            try:
                ib.cancelMktData(stock)
            except Exception:
                pass

            candidate = (
                _safe_float(tkr.last) or
                _safe_float(tkr.close) or
                _safe_float(tkr.bid) or
                _safe_float(tkr.ask)
            )
            if candidate and candidate > 0:
                underlying = candidate
                result["market_data_type"] = mdt
                try:
                    setattr(ib, "_qopz_market_data_type", mdt)
                except Exception:
                    pass
                break

        if underlying and underlying > 0:
            result["underlying_price"] = round(underlying, 4)
        else:
            tried_repr = ",".join(str(x) for x in tried_types) if tried_types else "-"
            result["error"] = (
                "NO MRKT - Prezzo sottostante non disponibile "
                f"(mercato chiuso o feed non attivo; tipi provati: {tried_repr})"
            )
            return result

        # ── 3. Catena opzioni ─────────────────────────────────────────────────
        chains = ib.reqSecDefOptParams(
            stock.symbol, "", stock.secType, stock.conId
        )
        if not chains:
            result["error"] = "nessuna catena opzioni disponibile"
            return result

        chain = next((c for c in chains if c.exchange == "SMART"), chains[0])

        today = date.today()
        chosen_exp: Optional[str] = None
        chosen_dte: Optional[int] = None
        for exp_str in sorted(chain.expirations):
            try:
                exp_date = date(int(exp_str[:4]), int(exp_str[4:6]), int(exp_str[6:8]))
                dte = (exp_date - today).days
                if 20 <= dte <= 60:
                    chosen_exp = exp_str
                    chosen_dte = dte
                    break
            except Exception:
                continue

        if chosen_exp is None:
            result["error"] = "nessuna scadenza in 20-60 DTE"
            return result

        result["expiry"] = chosen_exp
        result["dte"] = chosen_dte

        # ── 4. Strike ATM ─────────────────────────────────────────────────────
        strikes = sorted(chain.strikes)
        if not strikes:
            result["error"] = "nessuno strike disponibile"
            return result
        atm_strike = min(strikes, key=lambda s: abs(s - underlying))
        result["atm_strike"] = atm_strike
        result["contracts_count"] = len(strikes)

        # ── 5. Market data ATM call + put ─────────────────────────────────────
        # Non specificare multiplier: IBKR lo risolve (evita fallimento su NVDA e simili)
        call_contract = Option(symbol.upper(), chosen_exp, atm_strike, "C", "SMART", currency="USD")
        put_contract  = Option(symbol.upper(), chosen_exp, atm_strike, "P", "SMART", currency="USD")
        try:
            qualified_opts = ib.qualifyContracts(call_contract, put_contract)
        except Exception:
            qualified_opts = []

        if not qualified_opts:
            result["error"] = "qualifyContracts opzioni ATM fallito"
            return result

        tickers = []
        for opt in qualified_opts:
            # Snapshot + genericTicks (100/101/106) su alcune configurazioni IBKR
            # produce Error 321. Usiamo uno stream breve e poi cancelliamo.
            t = ib.reqMktData(opt, "100,101,106", snapshot=False, regulatorySnapshot=False)
            tickers.append((opt, t))

        ib.sleep(2.0)
        for opt, _ in tickers:
            try:
                ib.cancelMktData(opt)
            except Exception:
                pass

        call_t = next((t for o, t in tickers if hasattr(o, "right") and o.right == "C"), None)
        put_t  = next((t for o, t in tickers if hasattr(o, "right") and o.right == "P"), None)

        call_iv = _safe_float(getattr(call_t, "impliedVolatility", None)) if call_t else None
        put_iv  = _safe_float(getattr(put_t,  "impliedVolatility", None)) if put_t else None

        # Fallback Black-Scholes: se IBKR non restituisce IV (abbonamento OPRA mancante),
        # la calcoliamo dal mid bid/ask — stesso risultato, fonte diversa.
        T = chosen_dte / 365.0
        if (not call_iv or call_iv <= 0) and call_t is not None:
            call_bid = _safe_float(getattr(call_t, "bid", None))
            call_ask = _safe_float(getattr(call_t, "ask", None))
            if call_bid and call_ask and call_bid > 0 and call_ask > 0:
                mid = (call_bid + call_ask) / 2
                call_iv = _implied_vol_from_price(underlying, atm_strike, T, mid, "C")

        if (not put_iv or put_iv <= 0) and put_t is not None:
            put_bid = _safe_float(getattr(put_t, "bid", None))
            put_ask = _safe_float(getattr(put_t, "ask", None))
            if put_bid and put_ask and put_bid > 0 and put_ask > 0:
                mid = (put_bid + put_ask) / 2
                put_iv = _implied_vol_from_price(underlying, atm_strike, T, mid, "P")

        if call_iv and call_iv > 0:
            result["atm_call_iv"] = round(call_iv, 6)
        if put_iv and put_iv > 0:
            result["atm_put_iv"] = round(put_iv, 6)

        iv_vals = [v for v in (call_iv, put_iv) if v and v > 0]
        if iv_vals:
            result["atm_iv"] = round(sum(iv_vals) / len(iv_vals), 6)

        greeks_filled = 0
        if call_t is not None:
            mg = getattr(call_t, "modelGreeks", None)
            if mg is not None:
                for field in ("delta", "gamma", "theta", "vega"):
                    val = _safe_float(getattr(mg, field, None))
                    if val is not None:
                        result[f"atm_{field}"] = round(val, 6)
                        greeks_filled += 1

        result["greeks_complete"] = greeks_filled

        if result["atm_iv"] is None:
            phase = _market_phase_ny()
            if phase == "pre":
                result["error"] = "PRE-MKT - IV ATM non disponibile prima apertura USA (09:30 ET)"
            else:
                result["error"] = "NO MRKT - IV ATM non disponibile (mercato opzioni chiuso o feed OPRA assente)"

        return result

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def capture_ibkr_universe_snapshot(symbols: list[str], profile: str = "dev") -> list[dict[str, Any]]:
    """
    Apre UNA sola connessione IBG e cattura snapshot per tutti i simboli.
    Ritorna lista di dict (uno per simbolo), stessa struttura di capture_ibkr_symbol_snapshot.
    Molto più efficiente del loop per-simbolo con connessioni separate.
    """
    if not symbols:
        return []

    try:
        from ib_insync import IB
    except ImportError as exc:
        err = f"ib_insync non installato: {exc}"
        return [_empty_result(s, err) for s in symbols]

    host, ports, client_id = _ibkr_connection_params(profile)
    ib = IB()
    connected_port: Optional[int] = None

    try:
        for port in ports:
            try:
                ok = ib.connect(host, port, clientId=client_id, timeout=8.0, readonly=True)
                if ok and ib.isConnected():
                    connected_port = port
                    break
            except Exception:
                try:
                    ib.disconnect()
                except Exception:
                    pass
                ib = IB()

        if connected_port is None:
            err = f"IBG non raggiungibile su {host} porte {ports}"
            return [_empty_result(s, err) for s in symbols]

        ib.reqMarketDataType(1)  # live data — necessario per IV e greeks opzioni

        results = []
        for symbol in symbols:
            snap = _snapshot_on_connection(ib, symbol)
            results.append(snap)

        return results

    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        return [_empty_result(s, err) for s in symbols]
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass


def _term_structure_point_on_expiry(
    ib: Any,
    *,
    symbol: str,
    exchange: str,
    expiry_yyyymmdd: str,
    expiry_dt: date,
    dte: int,
    underlying: float,
    strikes: list[float],
    max_strikes: int = 18,
) -> dict[str, Any]:
    from ib_insync import Option

    if not strikes:
        return {
            "expiry": expiry_dt.isoformat(),
            "expiry_yyyymmdd": expiry_yyyymmdd,
            "dte": dte,
            "atm_strike": None,
            "atm_call_iv": None,
            "atm_put_iv": None,
            "atm_iv": None,
            "iv_source": "none",
            "liquidity_score": 0.0,
            "contracts_sampled": 0,
            "error": "no strikes",
            **_estimate_sigma_bands(underlying, None, dte),
        }

    strike_vals = sorted({float(s) for s in strikes if s is not None and float(s) > 0.0})
    if underlying > 0.0:
        sampled_strikes = sorted(strike_vals, key=lambda s: abs(s - underlying))[: max(4, max_strikes)]
        sampled_strikes = sorted(sampled_strikes)
    else:
        sampled_strikes = strike_vals[: max(4, max_strikes)]
    if not sampled_strikes:
        return {
            "expiry": expiry_dt.isoformat(),
            "expiry_yyyymmdd": expiry_yyyymmdd,
            "dte": dte,
            "atm_strike": None,
            "atm_call_iv": None,
            "atm_put_iv": None,
            "atm_iv": None,
            "iv_source": "none",
            "liquidity_score": 0.0,
            "contracts_sampled": 0,
            "error": "no sampled strikes",
            **_estimate_sigma_bands(underlying, None, dte),
        }

    opts = []
    for s in sampled_strikes:
        opts.append(Option(symbol.upper(), expiry_yyyymmdd, s, "C", exchange, currency="USD"))
        opts.append(Option(symbol.upper(), expiry_yyyymmdd, s, "P", exchange, currency="USD"))

    try:
        qualified = ib.qualifyContracts(*opts)
    except Exception as exc:
        return {
            "expiry": expiry_dt.isoformat(),
            "expiry_yyyymmdd": expiry_yyyymmdd,
            "dte": dte,
            "atm_strike": None,
            "atm_call_iv": None,
            "atm_put_iv": None,
            "atm_iv": None,
            "iv_source": "none",
            "liquidity_score": 0.0,
            "contracts_sampled": 0,
            "error": f"qualify error: {exc}",
            **_estimate_sigma_bands(underlying, None, dte),
        }
    if not qualified:
        return {
            "expiry": expiry_dt.isoformat(),
            "expiry_yyyymmdd": expiry_yyyymmdd,
            "dte": dte,
            "atm_strike": None,
            "atm_call_iv": None,
            "atm_put_iv": None,
            "atm_iv": None,
            "iv_source": "none",
            "liquidity_score": 0.0,
            "contracts_sampled": 0,
            "error": "no qualified contracts",
            **_estimate_sigma_bands(underlying, None, dte),
        }

    req_pairs: list[tuple[Any, Any]] = []
    for opt in qualified:
        tkr = ib.reqMktData(opt, "100,101,106", snapshot=False, regulatorySnapshot=False)
        req_pairs.append((opt, tkr))
    ib.sleep(2.0)
    for opt, _ in req_pairs:
        try:
            ib.cancelMktData(opt)
        except Exception:
            pass

    liquidity = 0.0
    ticker_by_leg: dict[tuple[float, str], Any] = {}
    for opt, tkr in req_pairs:
        k = round(float(getattr(opt, "strike", 0.0)), 4)
        right = str(getattr(opt, "right", "")).upper()
        ticker_by_leg[(k, right)] = tkr
        oi = _safe_float(getattr(tkr, "openInterest", None)) or 0.0
        vol = _safe_float(getattr(tkr, "volume", None)) or 0.0
        bid = _safe_float(getattr(tkr, "bid", None)) or 0.0
        ask = _safe_float(getattr(tkr, "ask", None)) or 0.0
        mid = (bid + ask) / 2.0 if bid > 0.0 and ask > 0.0 and ask >= bid else 0.0
        spread_penalty = 1.0
        if mid > 0.0:
            spread_ratio = max(0.0, (ask - bid) / mid)
            spread_penalty = max(0.25, min(1.0, 1.0 - spread_ratio))
        liquidity += (oi + vol) * spread_penalty

    if underlying > 0.0:
        atm_strike = min(sampled_strikes, key=lambda s: abs(s - underlying))
    else:
        atm_strike = sampled_strikes[len(sampled_strikes) // 2]

    atm_key = round(float(atm_strike), 4)
    call_t = ticker_by_leg.get((atm_key, "C"))
    put_t = ticker_by_leg.get((atm_key, "P"))

    call_iv = _ticker_iv(call_t) if call_t is not None else None
    put_iv = _ticker_iv(put_t) if put_t is not None else None
    call_from_bs = False
    put_from_bs = False
    t_years = float(dte) / 365.0 if dte > 0 else 0.0

    if (call_iv is None or call_iv <= 0.0) and call_t is not None and t_years > 0.0 and underlying > 0.0:
        bid = _safe_float(getattr(call_t, "bid", None))
        ask = _safe_float(getattr(call_t, "ask", None))
        if bid and ask and bid > 0.0 and ask > 0.0:
            mid = (bid + ask) / 2.0
            call_iv = _implied_vol_from_price(underlying, atm_strike, t_years, mid, "C")
            call_from_bs = bool(call_iv and call_iv > 0.0)
    if (put_iv is None or put_iv <= 0.0) and put_t is not None and t_years > 0.0 and underlying > 0.0:
        bid = _safe_float(getattr(put_t, "bid", None))
        ask = _safe_float(getattr(put_t, "ask", None))
        if bid and ask and bid > 0.0 and ask > 0.0:
            mid = (bid + ask) / 2.0
            put_iv = _implied_vol_from_price(underlying, atm_strike, t_years, mid, "P")
            put_from_bs = bool(put_iv and put_iv > 0.0)

    call_iv_out = round(call_iv, 6) if call_iv and call_iv > 0.0 else None
    put_iv_out = round(put_iv, 6) if put_iv and put_iv > 0.0 else None
    iv_vals = [v for v in (call_iv, put_iv) if v and v > 0.0]
    atm_iv = round(sum(iv_vals) / len(iv_vals), 6) if iv_vals else None
    if atm_iv is None:
        iv_source = "none"
    elif call_from_bs and put_from_bs:
        iv_source = "bs"
    elif call_from_bs or put_from_bs:
        iv_source = "mix"
    else:
        iv_source = "ibkr"

    return {
        "expiry": expiry_dt.isoformat(),
        "expiry_yyyymmdd": expiry_yyyymmdd,
        "dte": dte,
        "atm_strike": round(float(atm_strike), 4),
        "atm_call_iv": call_iv_out,
        "atm_put_iv": put_iv_out,
        "atm_iv": atm_iv,
        "iv_source": iv_source,
        "liquidity_score": round(float(liquidity), 2),
        "contracts_sampled": int(len(sampled_strikes) * 2),
        "error": None if atm_iv is not None else "ATM IV unavailable",
        **_estimate_sigma_bands(underlying, atm_iv, dte),
    }


def _term_structure_on_connection(
    ib: Any,
    symbol: str,
    *,
    top_n: int = 3,
) -> dict[str, Any]:
    from ib_insync import Stock

    out: dict[str, Any] = {
        "symbol": symbol.upper(),
        "market_data_type": None,
        "underlying_price": None,
        "chains": [],
        "error": None,
    }
    try:
        stock = Stock(symbol.upper(), "SMART", "USD")
        qualified = ib.qualifyContracts(stock)
        if not qualified:
            out["error"] = "qualify underlying failed"
            return out
        stock = qualified[0]

        preferred_type = getattr(ib, "_qopz_market_data_type", None)
        tried_types: list[int] = []
        ordered_types = [preferred_type, 1, 3, 4]
        underlying: Optional[float] = None
        for mdt in ordered_types:
            if not isinstance(mdt, int) or mdt in tried_types:
                continue
            tried_types.append(mdt)
            try:
                ib.reqMarketDataType(mdt)
            except Exception:
                pass
            tkr = ib.reqMktData(stock, "", snapshot=True, regulatorySnapshot=False)
            ib.sleep(2.0)
            try:
                ib.cancelMktData(stock)
            except Exception:
                pass
            px = (
                _safe_float(getattr(tkr, "last", None))
                or _safe_float(getattr(tkr, "close", None))
                or _safe_float(getattr(tkr, "bid", None))
                or _safe_float(getattr(tkr, "ask", None))
            )
            if px and px > 0.0:
                underlying = float(px)
                out["market_data_type"] = mdt
                try:
                    setattr(ib, "_qopz_market_data_type", mdt)
                except Exception:
                    pass
                break
        if underlying is None or underlying <= 0.0:
            out["error"] = "underlying unavailable"
            return out
        out["underlying_price"] = round(float(underlying), 4)

        chains = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
        if not chains:
            out["error"] = "no option chain params"
            return out
        chain = next((c for c in chains if getattr(c, "exchange", "") == "SMART"), chains[0])
        expirations = list(getattr(chain, "expirations", []) or [])
        strikes = [float(s) for s in (getattr(chain, "strikes", []) or []) if s is not None]
        exp_candidates = _select_regular_expiries(expirations, max_candidates=10)
        if not exp_candidates:
            out["error"] = "no regular expiries in range"
            return out

        points: list[dict[str, Any]] = []
        chain_exchange = str(getattr(chain, "exchange", "SMART") or "SMART")
        for exp_str, exp_dt, dte in exp_candidates:
            point = _term_structure_point_on_expiry(
                ib,
                symbol=symbol,
                exchange=chain_exchange,
                expiry_yyyymmdd=exp_str,
                expiry_dt=exp_dt,
                dte=dte,
                underlying=float(underlying),
                strikes=strikes,
                max_strikes=18,
            )
            points.append(point)
        if not points:
            out["error"] = "no term points"
            return out

        points.sort(key=lambda p: (-float(p.get("liquidity_score") or 0.0), int(p.get("dte") or 9999)))
        out["chains"] = points[: max(1, int(top_n))]
        if not out["chains"]:
            out["error"] = "no selected chains"
        return out
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out


def capture_ibkr_universe_term_structure(
    symbols: list[str],
    profile: str = "dev",
    *,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """
    Capture term-structure snapshots for each symbol:
    select top-N regular monthly-like expiries by liquidity and compute 1sigma/2sigma bands.
    """
    if not symbols:
        return []
    try:
        from ib_insync import IB
    except ImportError as exc:
        err = f"ib_insync non installato: {exc}"
        return [{"symbol": str(s).upper(), "market_data_type": None, "underlying_price": None, "chains": [], "error": err} for s in symbols]

    host, ports, client_id = _ibkr_connection_params(profile)
    ib = IB()
    connected_port: Optional[int] = None
    try:
        for port in ports:
            try:
                ok = ib.connect(host, port, clientId=client_id, timeout=8.0, readonly=True)
                if ok and ib.isConnected():
                    connected_port = port
                    break
            except Exception:
                try:
                    ib.disconnect()
                except Exception:
                    pass
                ib = IB()
        if connected_port is None:
            err = f"IBG non raggiungibile su {host} porte {ports}"
            return [{"symbol": str(s).upper(), "market_data_type": None, "underlying_price": None, "chains": [], "error": err} for s in symbols]

        try:
            ib.reqMarketDataType(1)
        except Exception:
            pass

        out: list[dict[str, Any]] = []
        for s in symbols:
            out.append(_term_structure_on_connection(ib, str(s), top_n=top_n))
        return out
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        return [{"symbol": str(s).upper(), "market_data_type": None, "underlying_price": None, "chains": [], "error": err} for s in symbols]
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass


def capture_ibkr_symbol_snapshot(symbol: str, profile: str = "dev") -> dict[str, Any]:
    """
    Connette a IBG e cattura snapshot per un singolo simbolo.
    Wrapper di capture_ibkr_universe_snapshot per compatibilità.
    Per batch multi-simbolo usare direttamente capture_ibkr_universe_snapshot.
    """
    results = capture_ibkr_universe_snapshot([symbol], profile=profile)
    return results[0] if results else _empty_result(symbol, "nessun risultato")


# ─────────────────────────────────────────────────────────────────────────────
# Merge IV point nel JSON storico
# ─────────────────────────────────────────────────────────────────────────────

def merge_today_iv_point(symbol: str, atm_iv: float) -> None:
    """
    Sostituisce (o aggiunge) il punto odierno nell'IV history JSON con il
    valore IBKR. Stessa struttura usata da save_iv_history() in fetch_iv_history.py.
    Non fa nulla se atm_iv <= 0 o il path non esiste.
    """
    if not atm_iv or atm_iv <= 0.0:
        return

    path = _history_path(symbol)
    IV_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    today_str = date.today().isoformat()
    history: list[dict] = []

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            history = data.get("iv_history") or []
        except Exception:
            history = []

    # Rimuovi eventuale punto odierno esistente e aggiungi quello IBKR
    history = [p for p in history if p.get("date") != today_str]
    history.append({"date": today_str, "iv": round(atm_iv, 6), "source": "ibkr"})
    history.sort(key=lambda p: p.get("date", ""))

    payload = {
        "symbol": symbol.upper(),
        "data_mode": _data_mode(),
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "points": len(history),
        "iv_source_today": "ibkr",
        "iv_history": history,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
