from __future__ import annotations

from typing import Any, Dict, Optional

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



@router.get("/opz/signals/observations")
def opz_signal_observations(
    profile: str = "paper",
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 100,
    include_outcomes: bool = True,
) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_signal_observations(profile, symbol, strategy, limit, include_outcomes)


@router.get("/opz/signals/scorecards")
def opz_signal_scorecards(
    profile: str = "paper",
    asof_date: Optional[str] = None,
    window_days: int = 90,
    horizon_days: Optional[int] = None,
    strategy: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_signal_scorecards(profile, asof_date, window_days, horizon_days, strategy, limit)


@router.post("/opz/signals/recompute")
def opz_signal_recompute(
    profile: str = "paper",
    asof_date: Optional[str] = None,
    window_days: int = 90,
    horizons: Optional[str] = None,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_signal_recompute(profile, asof_date, window_days, horizons, symbol)
