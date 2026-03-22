from __future__ import annotations

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

