from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter


router = APIRouter()


@router.get("/opz/state")
def opz_state() -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_state()


@router.get("/opz/release_status")
def opz_release_status() -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_release_status()


@router.post("/opz/bootstrap")
def opz_bootstrap(profile: str = "paper", allow_demo: bool = False) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_bootstrap(profile, allow_demo)


@router.get("/opz/tier")
def opz_tier(profile: str = "dev", regime: str = "NORMAL") -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_tier(profile, regime)

