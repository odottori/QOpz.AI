from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from api.models import OpportunityDecisionRequest


router = APIRouter()


@router.post("/opz/opportunity/decision")
def opz_opportunity_decision(req: OpportunityDecisionRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_opportunity_decision(req)


@router.get("/opz/opportunity/ev_report")
def opz_opportunity_ev_report(profile: str = "paper", window_days: int = 30) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_opportunity_ev_report(profile, window_days)


@router.get("/opz/opportunity/exit_candidates")
def opz_exit_candidates(top_n: int = 10, min_score: int = 1):
    from api import opz_api as compat

    return compat.opz_exit_candidates(top_n, min_score)

