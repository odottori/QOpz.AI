from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter

from api.models import UniverseScanRequest


router = APIRouter()


@router.get("/opz/universe/latest")
def opz_universe_latest() -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_universe_latest()


@router.get("/opz/universe/ibkr_context")
def opz_universe_ibkr_context(settings_path: Optional[str] = None) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_universe_ibkr_context(settings_path)


@router.get("/opz/universe/provenance")
def opz_universe_provenance(
    settings_path: Optional[str] = None,
    ocr_path: Optional[str] = None,
    regime: str = "NORMAL",
    batch_id: Optional[str] = None,
) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_universe_provenance(settings_path, ocr_path, regime, batch_id)


@router.post("/opz/universe/scan")
def opz_universe_scan(req: UniverseScanRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_universe_scan(req)

