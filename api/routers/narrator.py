from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter

from api.models import AiChatRequest, AiPromptRequest, NarratorTtsRequest


router = APIRouter()


@router.get("/opz/narrator/tutorial")
def opz_narrator_tutorial(path: Optional[str] = None) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_narrator_tutorial(path)


@router.post("/opz/narrator/tts")
def opz_narrator_tts(req: NarratorTtsRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_narrator_tts(req)


@router.post("/opz/ai/prompt")
def opz_ai_prompt(req: AiPromptRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_ai_prompt(req)


@router.post("/opz/ai/chat")
def opz_ai_chat(req: AiChatRequest) -> Dict[str, Any]:
    from api import opz_api as compat

    return compat.opz_ai_chat(req)

