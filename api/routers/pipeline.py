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

    # ── 2. IV history (yfinance) ──────────────────────────────────────────────
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
    status_yf = "ok" if iv_ok == len(symbols) else ("partial" if iv_ok > 0 else "error")
    _rec("yfinance", t0, t1, len(symbols), iv_ok, status_yf,
         "; ".join(iv_err[:3]) if iv_err else None)
    results["yfinance"] = {"ok": iv_ok, "total": len(symbols), "errors": len(iv_err)}

    # ── 3. Events calendar (yfinance) ─────────────────────────────────────────
    t0 = datetime.now(timezone.utc)
    ev_ok = 0
    ev_err: list[str] = []
    try:
        from scripts.events_calendar import check_events
        for sym in symbols:
            try:
                check_events(sym)
                ev_ok += 1
            except Exception as exc:
                ev_err.append(f"{sym}: {exc}")
    except ImportError as exc:
        ev_err.append(f"import: {exc}")
    t1 = datetime.now(timezone.utc)
    status_ev = "ok" if ev_ok == len(symbols) else ("partial" if ev_ok > 0 else "error")
    _rec("events_calendar", t0, t1, len(symbols), ev_ok, status_ev,
         "; ".join(ev_err[:3]) if ev_err else None)
    results["events_calendar"] = {"ok": ev_ok, "total": len(symbols), "errors": len(ev_err)}

    # ── Totale runs registrate oggi ───────────────────────────────────────────
    total_runs = list_ingestion_runs(profile=profile, days_back=1)
    return {
        "ok": True,
        "profile": profile,
        "symbols_count": len(symbols),
        "feeds": results,
        "runs_today": len(total_runs),
    }

