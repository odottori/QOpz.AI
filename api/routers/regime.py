from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()


@router.get("/opz/regime/current")
def opz_regime_current(window: int = 20):
    from api import opz_api as compat

    return compat.opz_regime_current(window)
