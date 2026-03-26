from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()


@router.get("/opz/ibkr/status")
def opz_ibkr_status(try_connect: bool = False):
    from api import opz_api as compat

    return compat.opz_ibkr_status(try_connect)


@router.get("/opz/ibkr/account")
def opz_ibkr_account():
    from api import opz_api as compat

    return compat.opz_ibkr_account()


@router.post("/opz/ibkr/disconnect")
def opz_ibkr_disconnect():
    from api import opz_api as compat

    return compat.opz_ibkr_disconnect()
