from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter

from api.models import SessionLogRequest, SessionRunRequest


router = APIRouter()


@router.get("/opz/session/status")
def opz_session_status() -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_session_status()


@router.post("/opz/session/run")
async def opz_session_run(req: SessionRunRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return await compat.opz_session_run(req)


@router.post("/opz/session/log")
def opz_session_log(req: SessionLogRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_session_log(req)


@router.get("/opz/session/logs")
def opz_session_logs(
    profile: str = "paper",
    limit: int = 30,
    session_type: Optional[str] = None,
) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_session_logs(profile, limit, session_type)

