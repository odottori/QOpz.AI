from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from api.models import ConfirmRequest, KillSwitchRequest, PreviewRequest, PreviewResponse


router = APIRouter()


@router.post("/opz/execution/preview", response_model=PreviewResponse)
def execution_preview(req: PreviewRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.execution_preview(req)


@router.post("/opz/execution/confirm")
def execution_confirm(req: ConfirmRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.execution_confirm(req)


@router.post("/opz/execution/kill_switch")
def execution_kill_switch(req: KillSwitchRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.execution_kill_switch(req)

