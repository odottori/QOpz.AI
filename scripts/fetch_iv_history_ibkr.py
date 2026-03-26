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
from typing import Any, Optional

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


def _ibkr_connection_params(profile: str = "dev") -> tuple[str, list[int], int]:
    """Ritorna (host, ports, client_id) leggendo env vars + config profilo."""
    host = (os.environ.get("IBKR_HOST") or "127.0.0.1").strip()
    env_ports_raw = os.environ.get("IBKR_PORTS") or os.environ.get("IBKR_PORT") or ""
    env_ports = [int(p.strip()) for p in env_ports_raw.replace(";", ",").split(",")
                 if p.strip().isdigit()]
    ports = env_ports or [4004, 4002, 7497, 7496, 4001]
    client_id = int(os.environ.get("IBKR_CLIENT_ID") or "8")
    try:
        from execution.config_loader import load_profile_config
        cfg = load_profile_config(profile)
        b = cfg.get("broker") or {}
        if not env_ports:
            cfg_port = b.get("port")
            if cfg_port:
                ports = [int(cfg_port)] + [p for p in ports if p != int(cfg_port)]
    except Exception:
        pass
    return host, ports, client_id


# ─────────────────────────────────────────────────────────────────────────────
# Core: snapshot per simbolo / universo
# ─────────────────────────────────────────────────────────────────────────────

def _empty_result(symbol: str, error: str) -> dict[str, Any]:
    return {
        "symbol": symbol.upper(),
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
        tkr = ib.reqMktData(stock, "", snapshot=True, regulatorySnapshot=False)
        ib.sleep(2.0)
        ib.cancelMktData(stock)

        underlying = (
            _safe_float(tkr.last) or
            _safe_float(tkr.close) or
            _safe_float(tkr.bid) or
            _safe_float(tkr.ask)
        )
        if underlying and underlying > 0:
            result["underlying_price"] = round(underlying, 4)
        else:
            result["error"] = "NO MRKT - Prezzo sottostante non disponibile (mercato chiuso o feed non attivo)"
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
            # snapshot=True: richiesta singola, nessuna sottoscrizione persistente.
            # Evita accumulo di streaming e spam di Error 10091 nel log.
            t = ib.reqMktData(opt, "100,101,106", snapshot=True, regulatorySnapshot=False)
            tickers.append((opt, t))

        ib.sleep(2.0)

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
