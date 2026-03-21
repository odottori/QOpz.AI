from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter

from api.models import WheelNewRequest, WheelTransitionRequest


router = APIRouter()


@router.get("/opz/wheel/positions")
def opz_wheel_positions(profile: str = "dev", symbol: Optional[str] = None) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_wheel_positions(profile, symbol)


@router.post("/opz/wheel/new")
def opz_wheel_new(req: WheelNewRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_wheel_new(req)


@router.post("/opz/wheel/{position_id}/transition")
def opz_wheel_transition(position_id: str, req: WheelTransitionRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_wheel_transition(position_id, req)

