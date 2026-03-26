from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".qoaistate.json"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
TUTORIAL_TEXT2SPEECH_PATH = ROOT / "docs" / "TUTORIAL_APPLICAZIONE.md"
ALLOWED_SETTINGS_ROOT = ROOT / "docs"
ALLOWED_TUTORIAL_ROOT = ROOT / "docs"
ALLOWED_OCR_ROOTS = [ROOT / "data", ROOT / "docs"]
TTS_FALLBACK_PID_PATH = LOG_DIR / "tts_fallback_pid.txt"
TTS_FALLBACK_STATE_PATH = LOG_DIR / "tts_fallback_state.txt"
_TTS_FALLBACK_PID_MEM: Optional[int] = None
_TTS_FALLBACK_STATE_MEM: str = ""
_TTS_LOCK = threading.Lock()
_JSONL_LOCK = threading.Lock()  # serializza scritture su operator_previews/confirms.jsonl

_SESSION_STATE: dict[str, Any] = {
    "last_morning": None,
    "last_eod": None,
    "next_morning": None,
    "next_eod": None,
    "last_result": None,
    "running": False,
    "enabled": False,
    "scheduler_mode": "internal",
}
_SESSION_TASK: Optional[asyncio.Task] = None  # type: ignore[type-arg]
