from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from api.models import DemoPipelineAutoRequest, ScanFullRequest


router = APIRouter()
logger = logging.getLogger(__name__)


def _unique_errs(items: list[str], limit: int = 3) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        txt = str(raw or "").strip()
        if not txt or txt in seen:
            continue
        seen.add(txt)
        out.append(txt)
        if len(out) >= limit:
            break
    return out


def _yfinance_underlying_fallback(symbols: list[str]) -> tuple[dict[str, float], list[str]]:
    """Best-effort fallback prezzo sottostante via yfinance (senza IV/greche)."""
    prices: dict[str, float] = {}
    errs: list[str] = []
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:
        return {}, [f"yfinance import: {type(exc).__name__}: {exc}"]

    for s in symbols:
        sym = str(s or "").strip().upper()
        if not sym:
            continue
        try:
            tkr = yf.Ticker(sym)
            px = 0.0
            try:
                fi = getattr(tkr, "fast_info", None)
                px = float(getattr(fi, "last_price", 0.0) or 0.0)
            except Exception:
                px = 0.0

            if px <= 0.0:
                try:
                    hist = tkr.history(period="2d", auto_adjust=False)
                    if hist is not None and not hist.empty:
                        close = hist["Close"].dropna()
                        if len(close) > 0:
                            px = float(close.iloc[-1] or 0.0)
                except Exception:
                    pass

            if px > 0.0:
                prices[sym] = round(px, 4)
            else:
                errs.append(f"{sym}: prezzo non disponibile")
        except Exception as exc:
            errs.append(f"{sym}: {type(exc).__name__}")
    return prices, errs


@router.post("/opz/opportunity/scan_full")
def opz_opportunity_scan_full(req: ScanFullRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_opportunity_scan_full(req)


@router.post("/opz/demo_pipeline/auto")
def opz_demo_pipeline_auto(req: DemoPipelineAutoRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_demo_pipeline_auto(req)


@router.get("/opz/pipeline/feed_log")
def opz_pipeline_feed_log(
    profile: str = Query("dev"),
    days_back: int = Query(30, ge=1, le=365),
    feed: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Storico delle esecuzioni pipeline per fonte dati.

    Ritorna le ultime `days_back` giornate di ingestione,
    opzionalmente filtrate per `feed` (yfinance | fred | orats | ibkr_demo | ...).
    """
    from execution.storage import list_ingestion_runs

    runs = list_ingestion_runs(profile=profile, days_back=days_back, feed=feed)
    return {
        "ok": True,
        "profile": profile,
        "days_back": days_back,
        "feed_filter": feed,
        "n": len(runs),
        "runs": runs,
    }


@router.post("/opz/data/refresh")
def opz_data_refresh(
    profile: str = Query("dev"),
) -> Dict[str, Any]:
    """Aggiorna i dati di mercato (yfinance) e registra ogni fonte in ingestion_runs.

    Eseguito automaticamente all'apertura della UI se il feed_log e vuoto.
    Idempotente: il backend skippa la scrittura se i dati sono gia freschi.
    """
    from execution.storage import record_ingestion_run, list_ingestion_runs
    from api.opz_api import opz_universe_latest

    today = date.today().isoformat()
    results: Dict[str, Any] = {}

    def _rec(feed: str, t0: datetime, t1: datetime, n_in: int, n_out: int,
             status: str, error: Optional[str] = None) -> None:
        try:
            record_ingestion_run(
                profile=profile, feed=feed, run_date=today,
                started_at=t0.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                finished_at=t1.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                duration_ms=int((t1 - t0).total_seconds() * 1000),
                status=status, records_in=n_in, records_out=n_out,
                symbols_count=n_in, error_msg=error,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("record_ingestion_run(%s): %s", feed, exc)

    # 1) Universe symbols
    # I simboli vengono SEMPRE dall'universe scan. Nessun fallback hardcoded:
    # se l'universo e vuoto si esegue una scan automatica; se anche quella
    # fallisce si restituisce errore esplicito al chiamante.
    symbols: list[str] = []
    try:
        uni = opz_universe_latest(profile=profile)
        items = uni.get("items", []) or []
        symbols = list({r.get("symbol") for r in items if r.get("symbol")})
        if not symbols:
            # Universo vuoto -> scan automatica da impostazioni IBKR
            import logging as _log
            _log.getLogger(__name__).info("Universe vuoto - eseguo scan automatica prima del refresh")
            from execution.universe import run_universe_scan_from_ibkr_settings
            run_universe_scan_from_ibkr_settings(profile=profile, top_n=20)
            uni2 = opz_universe_latest(profile=profile)
            items2 = uni2.get("items", []) or []
            symbols = list({r.get("symbol") for r in items2 if r.get("symbol")})
    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).error("Errore recupero simboli universo: %s", exc)

    if not symbols:
        raise HTTPException(
            status_code=409,
            detail="Universo simboli non disponibile - eseguire prima una scan",
        )

    # 2) yfinance - IV history ATM
    t0 = datetime.now(timezone.utc)
    iv_ok = 0
    iv_err: list[str] = []
    try:
        from scripts.fetch_iv_history import fetch_iv_history, save_iv_history
        for sym in symbols:
            try:
                hist = fetch_iv_history(sym)
                save_iv_history(sym, hist)
                iv_ok += 1
            except Exception as exc:
                iv_err.append(f"{sym}: {exc}")
    except ImportError as exc:
        iv_err.append(f"import: {exc}")
    t1 = datetime.now(timezone.utc)
    status_yf_iv = "ok" if iv_ok == len(symbols) else ("partial" if iv_ok > 0 else "error")
    _rec("yfinance_iv_history", t0, t1, len(symbols), iv_ok, status_yf_iv,
         "; ".join(iv_err[:3]) if iv_err else None)
    results["yfinance_iv_history"] = {"ok": iv_ok, "total": len(symbols), "errors": len(iv_err)}

    # 3a) yfinance - earnings calendar
    t0 = datetime.now(timezone.utc)
    cal_ok = 0
    cal_err: list[str] = []
    try:
        from scripts.events_calendar import fetch_earnings_date
        for sym in symbols:
            try:
                fetch_earnings_date(sym)
                cal_ok += 1
            except Exception as exc:
                cal_err.append(f"{sym}: {exc}")
    except ImportError as exc:
        cal_err.append(f"import: {exc}")
    t1 = datetime.now(timezone.utc)
    status_cal = "ok" if cal_ok == len(symbols) else ("partial" if cal_ok > 0 else "error")
    _rec("yfinance_calendar", t0, t1, len(symbols), cal_ok, status_cal,
         "; ".join(cal_err[:3]) if cal_err else None)
    results["yfinance_calendar"] = {"ok": cal_ok, "total": len(symbols), "errors": len(cal_err)}

    # 3b) yfinance - ex-dividend dates
    t0 = datetime.now(timezone.utc)
    div_ok = 0
    div_err: list[str] = []
    try:
        from scripts.events_calendar import fetch_dividend_date
        for sym in symbols:
            try:
                fetch_dividend_date(sym)
                div_ok += 1
            except Exception as exc:
                div_err.append(f"{sym}: {exc}")
    except ImportError as exc:
        div_err.append(f"import: {exc}")
    t1 = datetime.now(timezone.utc)
    status_div = "ok" if div_ok == len(symbols) else ("partial" if div_ok > 0 else "error")
    _rec("yfinance_exdiv", t0, t1, len(symbols), div_ok, status_div,
         "; ".join(div_err[:3]) if div_err else None)
    results["yfinance_exdiv"] = {"ok": div_ok, "total": len(symbols), "errors": len(div_err)}

    # 4) yfinance - macro indicators (VIX, VIX3M, 10Y/30Y)
    t0 = datetime.now(timezone.utc)
    macro_n_in, macro_n_out, macro_status, macro_err = 0, 0, "error", None
    try:
        from scripts.fetch_macro import fetch_macro_indicators
        res_macro = fetch_macro_indicators(lookback_days=1, profile=profile)
        macro_n_in = int(res_macro.get("n_series", 0) or 0)
        macro_n_out = int(res_macro.get("n_saved", 0) or 0)
        if res_macro.get("n_errors", 0) == macro_n_in:
            macro_status = "error"
            macro_err = "Tutti i ticker macro in errore"
        elif res_macro.get("n_errors", 0) > 0:
            macro_status = "partial"
        else:
            macro_status = "ok"
    except Exception as exc:
        macro_err = str(exc)
    t1 = datetime.now(timezone.utc)
    _rec("yfinance_macro", t0, t1, macro_n_in, macro_n_out, macro_status, macro_err)
    results["yfinance_macro"] = {"ok": macro_n_out, "total": macro_n_in, "status": macro_status}

    # Compat aliases per report/script legacy
    results["yfinance"] = results["yfinance_iv_history"]
    results["events_calendar"] = results["yfinance_calendar"]
    results["fred"] = results["yfinance_macro"]

    # 5) IBKR - ingest reale (prezzi, chain, greeks, IV history, account)
    mgr = None
    try:
        from execution.ibkr_connection import get_manager
        from api.opz_api import opz_ibkr_account
        from scripts.fetch_iv_history import load_iv_history
        from scripts.fetch_iv_history_ibkr import capture_ibkr_universe_snapshot, merge_today_iv_point
        mgr = get_manager()
    except Exception as exc:
        t0 = datetime.now(timezone.utc)
        t1 = datetime.now(timezone.utc)
        msg = f"Import IBKR fallito: {exc}"
        for _feed in ("ibkr_prices", "ibkr_chain", "ibkr_greeks", "ibkr_iv_history", "ibkr_account", "ibkr_positions"):
            _rec(_feed, t0, t1, len(symbols) if _feed != "ibkr_account" else 1, 0, "error", msg)
        try:
            from execution.storage import save_symbol_snapshots
            snapshots = [{"symbol": s, "underlying_price": None, "atm_strike": None, "atm_iv": None,
                          "atm_call_iv": None, "atm_put_iv": None, "iv_source": "ibkr",
                          "atm_delta": None, "atm_gamma": None, "atm_theta": None, "atm_vega": None,
                          "greeks_complete": 0, "contracts_count": 0, "error": msg} for s in symbols]
            save_symbol_snapshots(snapshots, profile=profile)
        except Exception:
            pass
        results["ibkr"] = {"status": "error", "error": msg}
    else:
        ibkr_errs: list[str] = []
        yfin_price_errs: list[str] = []
        yfin_price_ok = 0

        t0 = datetime.now(timezone.utc)
        try:
            snapshots: list[dict[str, Any]] = capture_ibkr_universe_snapshot(symbols, profile=profile)
        except Exception as exc:
            snapshots = []
            ibkr_errs.append(str(exc))
        # raccoglie errori per-simbolo dai risultati
        for snap in snapshots:
            if snap.get("error"):
                ibkr_errs.append(f"{snap.get('symbol')}: {snap['error']}")
        t1 = datetime.now(timezone.utc)

        symbols_ok = len(snapshots)
        total_contracts = sum(int(s.get("contracts_count", 0) or 0) for s in snapshots)
        greeks_complete = sum(int(s.get("greeks_complete", 0) or 0) for s in snapshots)
        with_price = sum(1 for s in snapshots if float(s.get("underlying_price") or 0.0) > 0)
        with_chain = sum(1 for s in snapshots if int(s.get("contracts_count", 0) or 0) > 0)

        # Fallback locale: se IBKR non fornisce prezzi, prova yfinance per popolare
        # almeno il sottostante nella tabella "Dati derivati".
        if with_price < len(symbols):
            yfin_prices, yfin_price_errs = _yfinance_underlying_fallback(symbols)
            if yfin_prices:
                for snap in snapshots:
                    if float(snap.get("underlying_price") or 0.0) > 0:
                        continue
                    sym = str(snap.get("symbol") or "").upper()
                    px = yfin_prices.get(sym)
                    if px is not None and px > 0:
                        snap["underlying_price"] = float(px)
                with_price = sum(1 for s in snapshots if float(s.get("underlying_price") or 0.0) > 0)
                yfin_price_ok = len(yfin_prices)
                logger.info("data_refresh: yfinance price fallback applied ok=%s/%s", yfin_price_ok, len(symbols))

        # Fallback locale IV per tabella "Dati derivati":
        # se ATM IV non arriva da IBKR, usa l'ultimo punto storico yfinance.
        yfin_iv_ok = 0
        yfin_iv_errs: list[str] = []
        for snap in snapshots:
            if snap.get("atm_iv") is not None:
                continue
            sym = str(snap.get("symbol") or "").upper()
            if not sym:
                continue
            try:
                hist = load_iv_history(sym)
                if hist:
                    last_iv = float(hist[-1] or 0.0)
                    if last_iv > 0:
                        snap["atm_iv"] = round(last_iv, 6)
                        snap["iv_source"] = "yfinance"
                        if snap.get("error"):
                            snap["error"] = f"{snap.get('error')} | fallback IV=yfinance"
                        yfin_iv_ok += 1
                        continue
                yfin_iv_errs.append(f"{sym}: iv_history yfinance assente")
            except Exception as exc:
                yfin_iv_errs.append(f"{sym}: {type(exc).__name__}")

        if yfin_iv_ok > 0:
            logger.info("data_refresh: yfinance iv fallback applied ok=%s/%s", yfin_iv_ok, len(symbols))

        # Errori separati per tipo: prices/chain vs IV/greeks - evita contaminazione error_msg
        price_errs = [f"{s.get('symbol')}: {s['error']}" for s in snapshots
                      if s.get("error") and float(s.get("underlying_price") or 0.0) <= 0]
        chain_errs = [f"{s.get('symbol')}: {s['error']}" for s in snapshots
                      if s.get("error") and int(s.get("contracts_count", 0) or 0) == 0]
        iv_errs    = [f"{s.get('symbol')}: {s['error']}" for s in snapshots
                      if s.get("error") and s.get("atm_iv") is None
                      and float(s.get("underlying_price") or 0.0) > 0]

        price_status = "ok" if with_price == len(symbols) and len(symbols) > 0 else ("partial" if with_price > 0 else "error")
        if yfin_price_ok > 0:
            # Prezzi presenti, ma non tutti da IBKR: stato minimo partial.
            if price_status == "ok":
                price_status = "partial"
            price_errs = [f"IBKR prezzo non disponibile - fallback yfinance {yfin_price_ok}/{len(symbols)}"] + price_errs
            if yfin_price_errs:
                price_errs.extend(yfin_price_errs[:2])
        chain_status = "ok" if with_chain == len(symbols) and len(symbols) > 0 else ("partial" if with_chain > 0 else "error")
        chain_err_msg = "; ".join(_unique_errs(chain_errs or ibkr_errs, 3)) if (chain_errs or (with_chain < len(symbols) and ibkr_errs)) else None

        _rec("ibkr_prices", t0, t1, len(symbols), with_price, price_status,
             "; ".join(_unique_errs(price_errs or ibkr_errs, 3)) if (price_errs or (with_price < len(symbols) and ibkr_errs)) else None)
        _rec("ibkr_chain", t0, t1, len(symbols), with_chain, chain_status,
             chain_err_msg)

        # Regola operativa allineata alla tabella "Dati derivati" (stato OK):
        # chain presente + prezzo/strike/iv validi + greche complete 4/4 + nessun errore bloccante.
        def _is_blocking_snapshot_error(msg: Any) -> bool:
            txt = str(msg or "").upper()
            if not txt.strip():
                return False
            return ("PRE-MKT" not in txt) and ("NO MRKT" not in txt)

        symbols_greeks_ok = sum(
            1
            for s in snapshots
            if int(s.get("contracts_count", 0) or 0) > 0
            and float(s.get("underlying_price") or 0.0) > 0.0
            and float(s.get("atm_strike") or 0.0) > 0.0
            and float(s.get("atm_iv") or 0.0) > 0.0
            and int(s.get("greeks_complete", 0) or 0) >= 4
            and not _is_blocking_snapshot_error(s.get("error"))
        )
        if with_chain <= 0:
            _rec("ibkr_greeks", t0, t1, 0, 0, "error", "Catene opzioni assenti")
        else:
            if symbols_greeks_ok == with_chain:
                greek_status = "ok"
            elif symbols_greeks_ok == 0:
                greek_status = "error"
            else:
                greek_status = "partial"
            greek_errs: list[str] = []
            if symbols_greeks_ok < with_chain:
                greek_errs.append(f"righe derivati valide su {symbols_greeks_ok}/{with_chain} simboli con catena")
            if iv_errs:
                greek_errs.extend(iv_errs)
            _rec(
                "ibkr_greeks",
                t0,
                t1,
                with_chain,
                symbols_greeks_ok,
                greek_status,
                "; ".join(_unique_errs(greek_errs, 3)) if greek_errs else None,
            )

        t2 = datetime.now(timezone.utc)
        iv_ok_ibkr = 0
        iv_err_ibkr: list[str] = []
        for snap in snapshots:
            try:
                atm_iv = snap.get("atm_iv")
                sym = str(snap.get("symbol") or "")
                iv_src = str(snap.get("iv_source") or "ibkr").strip().lower()
                if sym and atm_iv is not None and iv_src != "yfinance":
                    merge_today_iv_point(sym, float(atm_iv))
                    iv_ok_ibkr += 1
            except Exception as exc:
                iv_err_ibkr.append(f"{snap.get('symbol')}: {exc}")
        t3 = datetime.now(timezone.utc)
        iv_err_all = _unique_errs(iv_err_ibkr + iv_errs + ibkr_errs, 3)
        if symbols_ok <= 0:
            _rec(
                "ibkr_iv_history",
                t2,
                t3,
                0,
                0,
                "error",
                "; ".join(iv_err_all) if iv_err_all else "IBKR snapshot assente",
            )
        elif iv_ok_ibkr == symbols_ok:
            _rec("ibkr_iv_history", t2, t3, symbols_ok, iv_ok_ibkr, "ok", None)
        elif iv_ok_ibkr > 0:
            _rec(
                "ibkr_iv_history",
                t2,
                t3,
                symbols_ok,
                iv_ok_ibkr,
                "partial",
                "; ".join(iv_err_all) if iv_err_all else None,
            )
        else:
            _rec(
                "ibkr_iv_history",
                t2,
                t3,
                symbols_ok,
                0,
                "partial",
                "; ".join(iv_err_all) if iv_err_all else "NO MRKT - IV ATM non disponibile per i simboli correnti",
            )

        # Persiste snapshot IV/greeks per-simbolo (quarta griglia DATI tab)
        try:
            from execution.storage import save_symbol_snapshots
            save_symbol_snapshots(snapshots, profile=profile)
        except Exception as _exc:
            logger.warning("save_symbol_snapshots failed: %s", _exc)

        t4 = datetime.now(timezone.utc)
        account_err = None
        account_status = "error"
        positions_out = 0
        try:
            acc = opz_ibkr_account()
            if acc.get("connected"):
                account_status = "ok"
                positions_out = len(acc.get("positions") or [])
            else:
                account_status = "error"
                account_err = acc.get("message") or "IBKR non connesso"
        except Exception as exc:
            account_err = str(exc)
            acc = {"connected": False, "positions": []}
        t5 = datetime.now(timezone.utc)
        _rec("ibkr_account", t4, t5, 1, 1 if account_status == "ok" else 0, account_status, account_err)
        _rec("ibkr_positions", t4, t5, 1 if account_status == "ok" else 0, positions_out,
             "ok" if account_status == "ok" else "error", account_err)

        compat_status = "ok" if with_chain > 0 else ("partial" if snapshots else "error")
        results["ibkr"] = {
            "status": compat_status,
            "error": chain_err_msg or account_err,
            "symbols_ok": symbols_ok,
            "contracts": total_contracts,
            "greeks_complete": greeks_complete,
            "iv_history_ok": iv_ok_ibkr,
            "positions": positions_out,
        }
    finally:
        if mgr is not None:
            try:
                mgr.disconnect()
            except Exception as _disc_exc:
                import logging as _log

                _log.getLogger(__name__).debug("IBKR disconnect after data refresh skipped: %s", _disc_exc)

    # Totale runs registrate oggi
    total_runs = list_ingestion_runs(profile=profile, days_back=1)
    return {
        "ok": True,
        "profile": profile,
        "symbols_count": len(symbols),
        "feeds": results,
        "runs_today": len(total_runs),
    }
