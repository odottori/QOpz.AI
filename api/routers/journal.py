from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter

from api.models import EquitySnapshotRequest, TradeJournalRequest


router = APIRouter()


@router.get("/opz/last_actions")
def opz_last_actions(limit: int = 5) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_last_actions(limit)


@router.get("/opz/paper/summary")
def opz_paper_summary(
    profile: str = "paper",
    window_days: int = 60,
    asof_date: Optional[str] = None,
) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_paper_summary(profile, window_days, asof_date)


@router.get("/opz/paper/equity_history")
def opz_paper_equity_history(
    profile: str = "paper",
    limit: int = 60,
    asof_date: Optional[str] = None,
):
    from api import opz_api as compat

    return compat.opz_paper_equity_history(profile, limit, asof_date)


@router.post("/opz/paper/equity_snapshot")
def opz_paper_equity_snapshot(req: EquitySnapshotRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_paper_equity_snapshot(req)


@router.post("/opz/paper/trade")
def opz_paper_trade(req: TradeJournalRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_paper_trade(req)


@router.delete("/opz/paper/trade/{trade_id}")
def opz_delete_trade(trade_id: str) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_delete_trade(trade_id)


@router.delete("/opz/paper/snapshot/{snapshot_id}")
def opz_delete_snapshot(snapshot_id: str) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_delete_snapshot(snapshot_id)

