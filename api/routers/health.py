from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response


router = APIRouter()


@router.get("/health")
def health() -> dict:
    from api import opz_api as compat

    return compat.health()


@router.get("/console", response_class=FileResponse)
def console() -> FileResponse:
    from api import opz_api as compat

    return compat.console()


@router.get("/guide/{path:path}")
@router.get("/guide")
async def guide_proxy(request: Request, path: str = "") -> Response:
    from api import opz_api as compat

    return await compat.guide_proxy(request, path)


@router.get("/opz/system/status")
def opz_system_status():
    from api import opz_api as compat

    return compat.opz_system_status()
