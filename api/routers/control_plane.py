from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Header

from api.models import IbwrServiceRequest, ObserverSwitchRequest


router = APIRouter()


@router.post("/opz/execution/observer")
def execution_observer_switch(req: ObserverSwitchRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.execution_observer_switch(req)


@router.post("/opz/ibwr/service")
def ibwr_service_switch(req: IbwrServiceRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.ibwr_service_switch(req)


@router.get("/opz/control/status")
def opz_control_status() -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_control_status()

@router.post("/opz/admin/vm_update")
def opz_admin_vm_update(
    x_api_key: str = Header(default=""),
    dry_run: bool = False,
) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_vm_update(x_api_key, dry_run)
