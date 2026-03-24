from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from api.models import DemoPipelineAutoRequest, ScanFullRequest


router = APIRouter()


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

    Eseguito automaticamente all'apertura della UI se il feed_log è vuoto.
    Idempotente: il backend skippa la scrittura se i dati sono già freschi.
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

    # ── 1. Universe symbols ───────────────────────────────────────────────────
    symbols: list[str] = []
    try:
        uni = opz_universe_latest()
        rows = uni.get("market_rows", []) or []
        symbols = list({r.get("symbol") for r in rows if r.get("symbol")})
        if not symbols:
            # fallback: leggi da DB
            from execution.storage import _connect
            con = _connect()
            try:
                res = con.execute(
                    "SELECT DISTINCT symbol FROM universe_latest WHERE symbol IS NOT NULL LIMIT 50"
                ).fetchall()
                symbols = [r[0] for r in res]
            finally:
                con.close()
    except Exception:
        pass

    if not symbols:
        symbols = ["SPY", "QQQ", "AAPL", "MSFT", "AMZN", "TSLA", "NVDA", "META"]

    # ── 2. yfinance — IV history ATM ─────────────────────────────────────────
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

    # ── 3a. yfinance — earnings calendar ──────────────────────────────────────
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

    # ── 3b. yfinance — ex-dividend dates ──────────────────────────────────────
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

    # ── 4. yfinance — macro indicators (VIX, VIX3M, 10Y/30Y) ────────────────
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

    # ── 5. IBKR — ingest reale (prezzi, chain, greeks, IV history, account) ─
    try:
        from api.opz_api import opz_ibkr_account
        from scripts.fetch_iv_history_ibkr import capture_ibkr_universe_snapshot, merge_today_iv_point
    except Exception as exc:
        t0 = datetime.now(timezone.utc)
        t1 = datetime.now(timezone.utc)
        msg = f"Import IBKR fallito: {exc}"
        for _feed in ("ibkr_prices", "ibkr_chain", "ibkr_greeks", "ibkr_iv_history", "ibkr_account", "ibkr_positions"):
            _rec(_feed, t0, t1, len(symbols) if _feed != "ibkr_account" else 1, 0, "error", msg)
        results["ibkr"] = {"status": "error", "error": msg}
    else:
        ibkr_errs: list[str] = []

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

        # Errori separati per tipo: prices/chain vs IV/greeks — evita contaminazione error_msg
        price_errs = [f"{s.get('symbol')}: {s['error']}" for s in snapshots
                      if s.get("error") and float(s.get("underlying_price") or 0.0) <= 0]
        chain_errs = [f"{s.get('symbol')}: {s['error']}" for s in snapshots
                      if s.get("error") and int(s.get("contracts_count", 0) or 0) == 0]
        iv_errs    = [f"{s.get('symbol')}: {s['error']}" for s in snapshots
                      if s.get("error") and s.get("atm_iv") is None
                      and float(s.get("underlying_price") or 0.0) > 0]

        price_status = "ok" if with_price == len(symbols) and len(symbols) > 0 else ("partial" if with_price > 0 else "error")
        chain_status = "ok" if with_chain == len(symbols) and len(symbols) > 0 else ("partial" if with_chain > 0 else "error")

        _rec("ibkr_prices", t0, t1, len(symbols), with_price, price_status,
             "; ".join((price_errs or ibkr_errs)[:3]) if (price_errs or (with_price < len(symbols) and ibkr_errs)) else None)
        _rec("ibkr_chain", t0, t1, len(symbols), with_chain, chain_status,
             "; ".join((chain_errs or ibkr_errs)[:3]) if (chain_errs or (with_chain < len(symbols) and ibkr_errs)) else None)

        # greeks_complete=0 con catene catturate = mercato chiuso, non un errore
        # records_in = simboli_ok * 4 (4 campi greek per simbolo: delta,gamma,theta,vega)
        max_greeks = symbols_ok * 4
        if greeks_complete == 0 and with_chain > 0:
            greek_status = "ok"
            _rec("ibkr_greeks", t0, t1, 0, 0, "ok", None)
        else:
            greek_status = "ok" if max_greeks > 0 and greeks_complete >= max_greeks * 0.75 else ("partial" if greeks_complete > 0 else "error")
            _rec("ibkr_greeks", t0, t1, max_greeks, greeks_complete, greek_status,
                 "; ".join(iv_errs[:3]) if iv_errs else None)

        t2 = datetime.now(timezone.utc)
        iv_ok_ibkr = 0
        iv_err_ibkr: list[str] = []
        for snap in snapshots:
            try:
                atm_iv = snap.get("atm_iv")
                sym = str(snap.get("symbol") or "")
                if sym and atm_iv is not None:
                    merge_today_iv_point(sym, float(atm_iv))
                    iv_ok_ibkr += 1
            except Exception as exc:
                iv_err_ibkr.append(f"{snap.get('symbol')}: {exc}")
        t3 = datetime.now(timezone.utc)
        # iv_ok_ibkr=0 con snapshots catturati = mercato chiuso, non un errore
        if iv_ok_ibkr == 0 and symbols_ok > 0 and not iv_err_ibkr:
            _rec("ibkr_iv_history", t2, t3, 0, 0, "ok", None)
        else:
            iv_status_ibkr = "ok" if iv_ok_ibkr == symbols_ok and symbols_ok > 0 else ("partial" if iv_ok_ibkr > 0 else "error")
            _rec("ibkr_iv_history", t2, t3, symbols_ok, iv_ok_ibkr, iv_status_ibkr,
                 "; ".join((iv_err_ibkr or ibkr_errs)[:3]) if (iv_err_ibkr or ibkr_errs) else None)

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

    # ── Totale runs registrate oggi ───────────────────────────────────────────
    total_runs = list_ingestion_runs(profile=profile, days_back=1)
    return {
        "ok": True,
        "profile": profile,
        "symbols_count": len(symbols),
        "feeds": results,
        "runs_today": len(total_runs),
    }

