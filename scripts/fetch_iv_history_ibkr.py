"""
scripts/fetch_iv_history_ibkr.py — ATM IV + greeks da IBKR via ib_insync

capture_ibkr_symbol_snapshot(sym, profile) → dict
    Connette a IBG, per ogni simbolo:
    - Quota del sottostante (bid/ask/last/close)
    - Chain opzioni: expiry più vicina in 20-60 DTE, strike ATM
    - Market data ATM call + put → IV implicita + greche (delta, gamma, theta, vega)
    Ritorna un dict con tutti i valori; errori NON bloccanti (ritorna partial).

merge_today_iv_point(sym, atm_iv) → None
    Sovrascrive il punto odierno nell'IV history JSON con il valore IBKR,
    mantenendo lo stesso formato usato da fetch_iv_history.py.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

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
# Core: snapshot per simbolo
# ─────────────────────────────────────────────────────────────────────────────

def capture_ibkr_symbol_snapshot(symbol: str, profile: str = "dev") -> dict[str, Any]:
    """
    Connette a IBG e cattura: prezzo sottostante, catena opzioni, IV ATM, greche ATM.

    Ritorna dict con:
        symbol, underlying_price, contracts_count, greeks_complete,
        atm_iv, atm_strike, expiry, dte,
        atm_call_iv, atm_put_iv, atm_delta, atm_gamma, atm_theta, atm_vega,
        error (None se ok)
    """
    result: dict[str, Any] = {
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
        "error": None,
    }

    try:
        from ib_insync import IB, Stock, Option
    except ImportError as exc:
        result["error"] = f"ib_insync non installato: {exc}"
        return result

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
            result["error"] = f"IBG non raggiungibile su {host} porte {ports}"
            return result

        # Delayed data per paper/demo (tipo 3 = frozen/delayed)
        ib.reqMarketDataType(3)

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
            result["error"] = "prezzo sottostante non disponibile"
            return result

        # ── 3. Parametri catena opzioni ───────────────────────────────────────
        chains = ib.reqSecDefOptParams(
            stock.symbol, "", stock.secType, stock.conId
        )
        if not chains:
            result["error"] = "nessuna catena opzioni disponibile"
            return result

        # Preferisci SMART, poi primo disponibile
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
        call_contract = Option(symbol.upper(), chosen_exp, atm_strike, "C", "SMART", "100", "USD")
        put_contract  = Option(symbol.upper(), chosen_exp, atm_strike, "P", "SMART", "100", "USD")
        try:
            qualified_opts = ib.qualifyContracts(call_contract, put_contract)
        except Exception:
            qualified_opts = []

        if not qualified_opts:
            result["error"] = "qualifyContracts opzioni ATM fallito"
            return result

        # Generic tick 106 = IV, 100 = opt vol, 101 = opt OI
        tickers = []
        for opt in qualified_opts:
            t = ib.reqMktData(opt, "100,101,106", snapshot=False, regulatorySnapshot=False)
            tickers.append((opt, t))

        ib.sleep(3.0)  # attendi dati dal feed

        call_t = next((t for o, t in tickers if hasattr(o, "right") and o.right == "C"), None)
        put_t  = next((t for o, t in tickers if hasattr(o, "right") and o.right == "P"), None)

        for opt, _ in tickers:
            try:
                ib.cancelMktData(opt)
            except Exception:
                pass

        # IV implicita
        call_iv = _safe_float(getattr(call_t, "impliedVolatility", None)) if call_t else None
        put_iv  = _safe_float(getattr(put_t,  "impliedVolatility", None)) if put_t else None

        if call_iv and call_iv > 0:
            result["atm_call_iv"] = round(call_iv, 6)
        if put_iv and put_iv > 0:
            result["atm_put_iv"] = round(put_iv, 6)

        iv_vals = [v for v in (call_iv, put_iv) if v and v > 0]
        if iv_vals:
            result["atm_iv"] = round(sum(iv_vals) / len(iv_vals), 6)

        # Greche dal modelGreeks del call ATM (più stabile)
        greeks_filled = 0
        for t, prefix in ((call_t, "atm_"), ):
            if t is None:
                continue
            mg = getattr(t, "modelGreeks", None)
            if mg is None:
                continue
            delta = _safe_float(getattr(mg, "delta", None))
            gamma = _safe_float(getattr(mg, "gamma", None))
            theta = _safe_float(getattr(mg, "theta", None))
            vega  = _safe_float(getattr(mg, "vega",  None))
            if delta is not None:
                result[f"{prefix}delta"] = round(delta, 6)
                greeks_filled += 1
            if gamma is not None:
                result[f"{prefix}gamma"] = round(gamma, 6)
                greeks_filled += 1
            if theta is not None:
                result[f"{prefix}theta"] = round(theta, 6)
                greeks_filled += 1
            if vega is not None:
                result[f"{prefix}vega"] = round(vega, 6)
                greeks_filled += 1

        result["greeks_complete"] = greeks_filled

        if result["atm_iv"] is None:
            result["error"] = "IV ATM non disponibile (mercato chiuso o feed delayed)"

        return result

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass


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
