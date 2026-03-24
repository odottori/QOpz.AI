from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.models import UniverseScanRequest


class ScanItemStatusRequest(BaseModel):
    status: str          # EXECUTED | EXPIRED
    trade_id: Optional[str] = None


router = APIRouter()


@router.get("/opz/universe/latest")
def opz_universe_latest() -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_universe_latest()


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

