from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from api.models import DemoPipelineAutoRequest, ScanFullRequest


router = APIRouter()


@router.post("/opz/opportunity/scan_full")
def opz_opportunity_scan_full(req: ScanFullRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_opportunity_scan_full(req)


@router.post("/opz/demo_pipeline/auto")
def opz_demo_pipeline_auto(req: DemoPipelineAutoRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_demo_pipeline_auto(req)

