from __future__ import annotations

from typing import Any, Dict, List, Optional
import threading

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.models import UniverseScanRequest


class ScanItemStatusRequest(BaseModel):
    status: str          # EXECUTED | EXPIRED
    trade_id: Optional[str] = None


router = APIRouter()
_TERM_REFRESH_LOCK = threading.Lock()


@router.get("/opz/universe/latest")
def opz_universe_latest(profile: str = "paper") -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_universe_latest(profile=profile)


@router.get("/opz/universe/ibkr_context")
def opz_universe_ibkr_context(settings_path: Optional[str] = None) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_universe_ibkr_context(settings_path)


@router.get("/opz/universe/provenance")
def opz_universe_provenance(
    settings_path: Optional[str] = None,
    ocr_path: Optional[str] = None,
    regime: str = "NORMAL",
    batch_id: Optional[str] = None,
) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_universe_provenance(settings_path, ocr_path, regime, batch_id)


@router.get("/opz/universe/symbol_snapshots")
def opz_universe_symbol_snapshots(profile: str = "paper") -> Dict[str, Any]:
    """Dati derivati per simbolo: IV ATM, greeks, fonte (ibkr/bs), aggiornamento."""
    from execution.storage import list_symbol_snapshots
    items = list_symbol_snapshots(profile=profile)
    return {"profile": profile, "count": len(items), "items": items}


@router.get("/opz/universe/term_structure")
def opz_universe_term_structure(
    profile: str = "paper",
    top_n: int = Query(3, ge=1, le=6),
) -> Dict[str, Any]:
    """
    Term-structure panel for current universe symbols.
    Returns top-N regular monthly-like expiries by liquidity for each symbol,
    with ATM IV and 1sigma/2sigma price bands.
    """
    from api import opz_api as compat
    from api.term_structure_cache import read_cache

    uni = compat.opz_universe_latest(profile=profile)
    raw_items = uni.get("items") or []
    symbols: List[str] = []
    seen: set[str] = set()
    for row in raw_items:
        sym = str((row or {}).get("symbol") or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        symbols.append(sym)

    if not symbols:
        return {
            "profile": profile,
            "count": 0,
            "top_n": int(top_n),
            "sigma_levels": [1, 2],
            "items": [],
            "error": "universe symbols unavailable",
        }

    try:
        return read_cache(profile, symbols, int(top_n))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/opz/universe/term_structure/refresh')
def refresh_universe_term_structure(profile: str = 'paper', top_n: int = Query(3, ge=1, le=6)) -> Dict[str, Any]:
    from api import opz_api as compat
    from api.term_structure_cache import _path, read_cache, save_cache
    from scripts.fetch_iv_history_ibkr import capture_ibkr_universe_term_structure

    try:
        _path(profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not _TERM_REFRESH_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail='Curve refresh already running')
    try:
        rows = compat.opz_universe_latest(profile=profile).get('items') or []
        symbols = list(dict.fromkeys(str(row.get('symbol') or '').strip().upper() for row in rows if row.get('symbol')))
        if not symbols:
            raise HTTPException(status_code=409, detail='Universe unavailable; run the explicit data refresh first')
        items = capture_ibkr_universe_term_structure(symbols[:50], profile=profile, top_n=int(top_n))
        if not any(item.get('chains') for item in items):
            raise HTTPException(status_code=503, detail='Broker curves unavailable; previous cache preserved')
        save_cache(profile, items)
        return read_cache(profile, symbols, int(top_n))
    finally:
        _TERM_REFRESH_LOCK.release()


@router.post("/opz/universe/scan")
def opz_universe_scan(req: UniverseScanRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_universe_scan(req)


@router.patch("/opz/universe/scan_item/{item_id}/status")
def opz_scan_item_status(item_id: str, req: ScanItemStatusRequest) -> Dict[str, Any]:
    allowed = {"EXECUTED", "EXPIRED", "PENDING"}
    if req.status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    from execution.universe import update_scan_item_status
    update_scan_item_status(item_id=item_id, status=req.status, trade_id=req.trade_id)
    return {"ok": True, "item_id": item_id, "status": req.status}


@router.get("/opz/universe/backtest")
def opz_universe_backtest(
    profile: str = "paper",
    from_ts: str = "",
    to_ts: str = "",
) -> Dict[str, Any]:
    if not from_ts or not to_ts:
        raise HTTPException(status_code=400, detail="from_ts and to_ts required (ISO format)")
    from execution.universe import query_backtest_applied
    rows = query_backtest_applied(profile=profile, from_ts=from_ts, to_ts=to_ts)
    executed   = [r for r in rows if r["status"] in ("EXECUTED", "AUTO_EXECUTED")]
    expired    = [r for r in rows if r["status"] == "EXPIRED"]
    pending    = [r for r in rows if r["status"] == "PENDING"]
    pnl_executed = sum(r["pnl"] or 0 for r in executed if r["pnl"] is not None)
    return {
        "ok": True,
        "profile": profile,
        "from_ts": from_ts,
        "to_ts": to_ts,
        "n_total": len(rows),
        "n_executed": len(executed),
        "n_expired": len(expired),
        "n_pending": len(pending),
        "pnl_executed": pnl_executed,
        "rows": rows,
    }
