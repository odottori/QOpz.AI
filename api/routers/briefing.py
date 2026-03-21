from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter()


@router.get("/opz/briefing/list")
def opz_briefing_list() -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_briefing_list()


@router.get("/opz/briefing/file/{filename}")
def opz_briefing_file(filename: str):
    from api import opz_api as compat

    return compat.opz_briefing_file(filename)


@router.get("/opz/briefing/latest")
def opz_briefing_latest() -> FileResponse:
    from api import opz_api as compat

    return compat.opz_briefing_latest()


@router.post("/opz/briefing/generate")
async def opz_briefing_generate(no_telegram: bool = False) -> Dict[str, Any]:
    from api import opz_api as compat

    return await compat.opz_briefing_generate(no_telegram)


@router.get("/opz/briefing/text")
def opz_briefing_text() -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_briefing_text()

