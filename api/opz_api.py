from __future__ import annotations

import json
import math
import os
import re
import secrets
import shlex
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, time as time_cls, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("opz_api")

from execution.paper_metrics import (
    compute_paper_summary,
    record_equity_snapshot,
    record_trade,
)
from execution.storage import _connect, _prov, init_execution_schema
from execution.ibkr_settings_profile import extract_ibkr_universe_context
from execution.universe import (
    build_universe_compare,
    fetch_latest_universe_batch,
    run_universe_scan,
    run_universe_scan_from_ibkr_settings,
    UniverseDataUnavailableError,
)

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


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    try:
        init_execution_schema()
    except Exception as exc:
        logger.warning("STARTUP_STORAGE_WARN %s", exc)
    yield


app = FastAPI(title="OPZ Operator API", version="0.1.0", lifespan=_app_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"ok": False, "stage": "internal", "reason": f"{type(exc).__name__}: {exc}"},
    )


class PreviewRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    strategy: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)


class EquitySnapshotRequest(BaseModel):
    profile: str = Field(default="paper", min_length=1)
    asof_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    equity: float
    note: str = Field(default="")


class TradeJournalRequest(BaseModel):
    profile: str = Field(default="paper", min_length=1)
    symbol: str = Field(..., min_length=1)
    strategy: str = Field(..., min_length=1)
    entry_ts_utc: Optional[str] = None
    exit_ts_utc: Optional[str] = None
    strikes: Optional[list[float]] = None
    regime_at_entry: Optional[str] = None
    score_at_entry: Optional[float] = None
    kelly_fraction: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl: float
    pnl_pct: Optional[float] = None
    slippage_ticks: Optional[float] = None
    violations: int = Field(default=0, ge=0)
    note: str = Field(default="")


class PreviewResponse(BaseModel):
    confirm_token: str
    preview: Dict[str, Any]


class ConfirmRequest(BaseModel):
    confirm_token: str
    operator: str = Field(default="operator")
    decision: str = Field(..., pattern="^(APPROVE|REJECT)$")
    payload: Dict[str, Any] = Field(default_factory=dict)


class OpportunityDecisionRequest(BaseModel):
    profile: str = Field(default="paper", min_length=1)
    batch_id: Optional[str] = None
    symbol: str = Field(..., min_length=1)
    strategy: Optional[str] = None
    score: Optional[float] = None
    regime: Optional[str] = None
    scanner_name: Optional[str] = None
    source: Optional[str] = None
    decision: str = Field(..., pattern="^(APPROVE|REJECT|MODIFY)$")
    confidence: int = Field(..., ge=1, le=5)
    note: str = Field(default="")

class UniverseScanRequest(BaseModel):
    profile: str = Field(default="paper", min_length=1)
    symbols: Optional[list[str]] = None
    regime: str = Field(default="NORMAL")
    top_n: int = Field(default=8, ge=1, le=50)
    source: str = Field(default="auto")  # auto|manual|ibkr_settings
    scanner_name: Optional[str] = None
    settings_path: Optional[str] = None


class ScanFullRequest(BaseModel):
    profile: str = Field(default="paper", min_length=1)
    regime: str = Field(default="NORMAL")
    symbols: list[str] = Field(default_factory=list)
    top_n: int = Field(default=5, ge=1, le=50)
    account_size: float = Field(default=10_000.0, gt=0)
    min_score: float = Field(default=60.0, ge=0.0, le=100.0)
    signal_map: Optional[Dict[str, str]] = None
    signal_pct_map: Optional[Dict[str, float]] = None
    use_cache: bool = Field(default=True)


class DemoPipelineAutoRequest(BaseModel):
    profile: str = Field(default="paper", min_length=1)
    symbols: Optional[list[str]] = None
    settings_path: Optional[str] = None
    fetch_limit: int = Field(default=12, ge=1, le=100)
    top_n: int = Field(default=8, ge=1, le=50)
    regime: str = Field(default="NORMAL")
    extract_backend: str = Field(default="json-pass")  # json-pass|ollama
    auto_scan: bool = Field(default=True)


class NarratorTtsRequest(BaseModel):
    action: str = Field(..., pattern="^(play|pause|stop)$")
    text: str = Field(default="")


class AiPromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=12000)


class AiChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str = Field(..., min_length=1, max_length=12000)


class AiChatRequest(BaseModel):
    messages: list[AiChatMessage] = Field(default_factory=list)
    prompt: Optional[str] = None


def _clean_text(value: str, field_name: str) -> str:
    out = value.strip()
    if not out:
        raise HTTPException(status_code=400, detail=f"invalid {field_name} (empty)")
    return out


def _require_finite(value: float, field_name: str) -> float:
    if not math.isfinite(value):
        raise HTTPException(status_code=400, detail=f"invalid {field_name} (non-finite)")
    return float(value)


def _resolve_safe_path(path: Optional[str], *, field_name: str, allowed_roots: list[Path]) -> Optional[str]:
    if path is None:
        return None
    raw = str(path).strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    try:
        resolved = (ROOT / p).resolve() if not p.is_absolute() else p.resolve()
    except OSError:
        raise HTTPException(status_code=400, detail=f"invalid {field_name} (unresolvable path)")

    for base in allowed_roots:
        base_resolved = base.resolve()
        if resolved == base_resolved or base_resolved in resolved.parents:
            return str(resolved)
    raise HTTPException(status_code=400, detail=f"invalid {field_name} (path outside allowed roots)")


def _cmd_list_from_template(template: str, *, text_value: str = "") -> list[str]:
    expanded = template.replace("{text}", text_value)
    try:
        cmd = shlex.split(expanded, posix=False)
    except ValueError:
        return []
    return [c for c in cmd if c]


def _cmd_repr(cmd: list[str]) -> str:
    if not cmd:
        return ""
    if os.name == "nt":
        return subprocess.list2cmdline(cmd)
    return " ".join(shlex.quote(x) for x in cmd)


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _run_release_status_md() -> str:
    cmd = [sys.executable, str(ROOT / "tools" / "release_status.py"), "--format", "md"]
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return f"ERROR running release_status: rc={r.returncode}\n{r.stdout}\n{r.stderr}"
    return r.stdout


def _run_script_json(script_rel: str, args: list[str]) -> dict[str, Any]:
    cmd = [sys.executable, str(ROOT / script_rel), *args, "--format", "json"]
    r = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout = (r.stdout or "").strip()
    stderr = (r.stderr or "").strip()

    payload: dict[str, Any] = {}
    if stdout:
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            s = stdout.find("{")
            e = stdout.rfind("}")
            if s >= 0 and e > s:
                try:
                    parsed = json.loads(stdout[s : e + 1])
                    if isinstance(parsed, dict):
                        payload = parsed
                except json.JSONDecodeError:
                    payload = {}

    return {
        "ok": r.returncode == 0,
        "returncode": int(r.returncode),
        "command": cmd,
        "stdout": stdout,
        "stderr": stderr,
        "payload": payload,
    }


def _read_tutorial_markdown(path: Optional[str] = None) -> dict[str, Any]:
    p = Path(path).expanduser() if path else TUTORIAL_TEXT2SPEECH_PATH
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return {"path": str(p), "exists": False, "content": ""}
    try:
        content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = p.read_text(encoding="utf-8", errors="ignore")
    return {"path": str(p), "exists": True, "content": content}


def _read_fallback_tts_pid() -> Optional[int]:
    global _TTS_FALLBACK_PID_MEM
    with _TTS_LOCK:
        if not TTS_FALLBACK_PID_PATH.exists():
            return _TTS_FALLBACK_PID_MEM
        try:
            raw = TTS_FALLBACK_PID_PATH.read_text(encoding="utf-8").strip()
            pid = int(raw)
            _TTS_FALLBACK_PID_MEM = pid if pid > 0 else None
            return _TTS_FALLBACK_PID_MEM
        except (OSError, ValueError):
            return _TTS_FALLBACK_PID_MEM


def _write_fallback_tts_pid(pid: int) -> None:
    global _TTS_FALLBACK_PID_MEM
    with _TTS_LOCK:
        _TTS_FALLBACK_PID_MEM = int(pid)
        try:
            TTS_FALLBACK_PID_PATH.write_text(str(int(pid)), encoding="utf-8")
        except OSError:
            return


def _read_fallback_tts_state() -> str:
    global _TTS_FALLBACK_STATE_MEM
    with _TTS_LOCK:
        if not TTS_FALLBACK_STATE_PATH.exists():
            return _TTS_FALLBACK_STATE_MEM
        try:
            _TTS_FALLBACK_STATE_MEM = TTS_FALLBACK_STATE_PATH.read_text(encoding="utf-8").strip().lower()
            return _TTS_FALLBACK_STATE_MEM
        except OSError:
            return _TTS_FALLBACK_STATE_MEM


def _write_fallback_tts_state(state: str) -> None:
    global _TTS_FALLBACK_STATE_MEM
    with _TTS_LOCK:
        _TTS_FALLBACK_STATE_MEM = (state or "").strip().lower()
        try:
            TTS_FALLBACK_STATE_PATH.write_text(_TTS_FALLBACK_STATE_MEM, encoding="utf-8")
        except OSError:
            return


def _clear_fallback_tts_pid() -> None:
    global _TTS_FALLBACK_PID_MEM
    with _TTS_LOCK:
        _TTS_FALLBACK_PID_MEM = None
        try:
            if TTS_FALLBACK_PID_PATH.exists():
                TTS_FALLBACK_PID_PATH.unlink()
        except OSError:
            return


def _clear_fallback_tts_state() -> None:
    global _TTS_FALLBACK_STATE_MEM
    with _TTS_LOCK:
        _TTS_FALLBACK_STATE_MEM = ""
        try:
            if TTS_FALLBACK_STATE_PATH.exists():
                TTS_FALLBACK_STATE_PATH.unlink()
        except OSError:
            return


def _pause_fallback_tts_process() -> bool:
    pid = _read_fallback_tts_pid()
    if not pid:
        return False
    try:
        if os.name == "nt":
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"Suspend-Process -Id {pid} -ErrorAction Stop"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if r.returncode == 0:
                _write_fallback_tts_state("paused")
                return True
            return False
        return False
    except OSError:
        return False


def _resume_fallback_tts_process() -> bool:
    pid = _read_fallback_tts_pid()
    if not pid:
        return False
    try:
        if os.name == "nt":
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"Resume-Process -Id {pid} -ErrorAction Stop"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if r.returncode == 0:
                _write_fallback_tts_state("playing")
                return True
            return False
        return False
    except OSError:
        return False


def _stop_fallback_tts_process() -> bool:
    pid = _read_fallback_tts_pid()
    if not pid:
        return False
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        else:
            os.kill(pid, 9)
        return True
    except OSError:
        return False
    finally:
        _clear_fallback_tts_pid()
        _clear_fallback_tts_state()


def _run_qwen_tts(action: str, text: str) -> dict[str, Any]:
    act = (action or "").strip().lower()
    if act not in {"play", "pause", "stop"}:
        raise HTTPException(status_code=400, detail="invalid action")

    play_tpl = os.environ.get("QWEN_TTS_PLAY_CMD", "qwenTTS play --text \"{text}\"")
    pause_tpl = os.environ.get("QWEN_TTS_PAUSE_CMD", "qwenTTS pause")
    stop_tpl = os.environ.get("QWEN_TTS_STOP_CMD", "qwenTTS stop")
    tpl_map = {"play": play_tpl, "pause": pause_tpl, "stop": stop_tpl}

    safe_text = (text or "").replace("\r", " ").replace("\n", " ").strip()
    cmd_list = _cmd_list_from_template(tpl_map[act], text_value=safe_text)
    if not cmd_list:
        raise HTTPException(status_code=500, detail=f"invalid QWEN_TTS_{act.upper()}_CMD template")
    r = subprocess.run(cmd_list, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = {
        "ok": r.returncode == 0,
        "action": act,
        "command": _cmd_repr(cmd_list),
        "returncode": int(r.returncode),
        "stdout": (r.stdout or "").strip(),
        "stderr": (r.stderr or "").strip(),
        "fallback_used": False,
    }
    if out["ok"]:
        return out

    err_l = out["stderr"].lower()
    missing_cmd = ("not recognized" in err_l) or ("riconosciuto" in err_l) or ("comando interno o esterno" in err_l)

    if act == "pause":
        paused = _pause_fallback_tts_process()
        if paused:
            out.update(
                {
                    "ok": True,
                    "returncode": 0,
                    "stdout": (out["stdout"] + " windows-fallback pause").strip(),
                    "stderr": "",
                    "fallback_used": True,
                }
            )
            return out
        if missing_cmd:
            out.update(
                {
                    "ok": False,
                    "returncode": 2,
                    "stdout": "",
                    "stderr": "windows-fallback: pausa non supportata su questo host",
                    "fallback_used": True,
                }
            )
            return out
        return out

    if act == "stop":
        stopped = _stop_fallback_tts_process()
        if stopped or missing_cmd:
            out.update(
                {
                    "ok": True,
                    "returncode": 0,
                    "stdout": (out["stdout"] + " windows-fallback stop").strip(),
                    "stderr": "",
                    "fallback_used": True,
                }
            )
            return out
        return out

    if _read_fallback_tts_state() == "paused":
        if _resume_fallback_tts_process():
            return {
                "ok": True,
                "action": "play",
                "command": "windows-fallback resume",
                "returncode": 0,
                "stdout": "windows-fallback resumed",
                "stderr": "",
                "fallback_used": True,
                "fallback_pid": _read_fallback_tts_pid(),
            }
        return {
            "ok": False,
            "action": "play",
            "command": "windows-fallback resume",
            "returncode": 2,
            "stdout": "",
            "stderr": "windows-fallback: resume non supportato su questo host",
            "fallback_used": True,
        }

    if not missing_cmd:
        return out

    _stop_fallback_tts_process()
    safe_text_ps = (text or "").replace("\r", " ").replace("\n", " ").strip()
    fallback_play_cmd = os.environ.get("QWEN_TTS_FALLBACK_PLAY_CMD", "").strip()

    try:
        if fallback_play_cmd:
            cmd_fb_list = _cmd_list_from_template(fallback_play_cmd, text_value=safe_text_ps)
            if not cmd_fb_list:
                raise RuntimeError("invalid QWEN_TTS_FALLBACK_PLAY_CMD template")
            cmd_fb = _cmd_repr(cmd_fb_list)
            proc = subprocess.Popen(
                cmd_fb_list,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        else:
            cmd_fb_list = [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$s.Speak('{safe_text_ps}')"
                ),
            ]
            cmd_fb = "powershell -NoProfile -Command <System.Speech fallback>"
            proc = subprocess.Popen(
                cmd_fb_list,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
    except Exception as exc:
        out.update(
            {
                "ok": False,
                "command": _cmd_repr(cmd_list),
                "returncode": 1,
                "stderr": str(exc),
                "fallback_used": True,
            }
        )
        return out

    time.sleep(0.1)
    rc = proc.poll()
    if rc is None:
        _write_fallback_tts_pid(int(proc.pid))
        _write_fallback_tts_state("playing")
        out.update(
            {
                "ok": True,
                "command": cmd_fb,
                "returncode": 0,
                "stdout": "windows-fallback speaking",
                "stderr": "",
                "fallback_used": True,
                "fallback_pid": int(proc.pid),
            }
        )
        return out

    std_out, std_err = proc.communicate(timeout=1)
    out.update(
        {
            "ok": rc == 0,
            "command": cmd_fb,
            "returncode": int(rc),
            "stdout": (std_out or "").strip(),
            "stderr": (std_err or "").strip(),
            "fallback_used": True,
        }
    )
    _clear_fallback_tts_pid()
    _clear_fallback_tts_state()
    return out

def _run_ollama_prompt(prompt: str) -> dict[str, Any]:
    txt = (prompt or "").strip()
    if not txt:
        raise HTTPException(status_code=400, detail="prompt vuoto")

    model = (os.environ.get("OPZ_AI_MODEL") or "qwen2.5:latest").strip() or "qwen2.5:latest"
    timeout_sec_raw = os.environ.get("OPZ_AI_TIMEOUT_SEC", "180")
    try:
        timeout_sec = max(10, int(timeout_sec_raw))
    except (ValueError, TypeError):
        timeout_sec = 180

    cmd = ["ollama", "run", model, txt]
    started = time.time()
    try:
        r = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
        duration_ms = int((time.time() - started) * 1000)
        stdout_clean = _strip_ansi(r.stdout or "").strip()
        stderr_clean = "" if r.returncode == 0 else _strip_ansi(r.stderr or "").strip()
        return {
            "ok": r.returncode == 0,
            "model": model,
            "prompt": txt,
            "response": stdout_clean,
            "stdout": stdout_clean,
            "stderr": stderr_clean,
            "returncode": int(r.returncode),
            "duration_ms": duration_ms,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="ollama non trovato nel PATH")
    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - started) * 1000)
        return {
            "ok": False,
            "model": model,
            "prompt": txt,
            "response": "",
            "stdout": "",
            "stderr": f"timeout dopo {timeout_sec}s",
            "returncode": 124,
            "duration_ms": duration_ms,
        }

def _normalize_ai_chat_messages(messages: list[AiChatMessage], prompt: Optional[str] = None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in messages:
        role = (m.role or "").strip().lower()
        content = (m.content or "").strip()
        if role not in {"system", "user", "assistant"}:
            continue
        if not content:
            continue
        out.append({"role": role, "content": content})

    prompt_txt = (prompt or "").strip()
    if prompt_txt:
        out.append({"role": "user", "content": prompt_txt})

    return out[-16:]


def _compose_ai_chat_prompt(messages: list[dict[str, str]]) -> str:
    lines = [
        "Sei un assistente operativo per QuantOPTION.AI. Rispondi in modo conciso e pratico.",
    ]
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "").strip()
        if not content:
            continue
        if role == "system":
            lines.append(f"System: {content}")
        elif role == "assistant":
            lines.append(f"Assistant: {content}")
        else:
            lines.append(f"User: {content}")
    lines.append("Assistant:")
    return "\n\n".join(lines)

_ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _strip_ansi(value: str) -> str:
    if not value:
        return ""
    return _ANSI_RE.sub("", value)

def _dt_to_iso_utc(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return ""
        return s
    return str(value)


def _parse_ts_utc(value: Optional[str], field_name: str) -> Optional[datetime]:
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid {field_name} (expected ISO datetime)")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _read_jsonl_tail(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    out: list[dict[str, Any]] = []
    for raw in reversed(lines):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
        if len(out) >= limit:
            break
    return out


def _read_jsonl_all(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    out: list[dict[str, Any]] = []
    for raw in lines:
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _find_preview_event(confirm_token: str) -> Optional[dict[str, Any]]:
    for item in reversed(_read_jsonl_all(LOG_DIR / "operator_previews.jsonl")):
        if str(item.get("token") or "").strip() == confirm_token:
            return item
    return None


def _confirm_token_already_used(confirm_token: str) -> bool:
    for item in reversed(_read_jsonl_all(LOG_DIR / "operator_confirms.jsonl")):
        if str(item.get("confirm_token") or "").strip() == confirm_token:
            return True
    return False


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps(str(value), ensure_ascii=False)


def _confirm_payload_matches_preview(confirm_payload: Dict[str, Any], preview: Dict[str, Any]) -> bool:
    symbol = _stringify_scalar(confirm_payload.get("symbol")).upper()
    strategy = _stringify_scalar(confirm_payload.get("strategy")).upper()
    expected_symbol = _stringify_scalar(preview.get("symbol")).upper()
    expected_strategy = _stringify_scalar(preview.get("strategy")).upper()
    if symbol != expected_symbol or strategy != expected_strategy:
        return False
    payload_obj = confirm_payload.get("payload")
    if not isinstance(payload_obj, dict):
        return False
    return _canonical_json(payload_obj) == _canonical_json(preview.get("payload") if isinstance(preview.get("payload"), dict) else {})


def _stringify_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()



def _count_profile_rows(con: Any, table_name: str, profile: str) -> int:
    row = con.execute(f"SELECT COUNT(*) FROM {table_name} WHERE profile = ?", (profile,)).fetchone()
    if not row:
        return 0
    try:
        return int(row[0])
    except (ValueError, TypeError):
        return 0


def _pick_bootstrap_candidate(profile: str) -> tuple[str, str, float]:
    latest = fetch_latest_universe_batch()
    if latest.get("has_data") and isinstance(latest.get("items"), list) and latest["items"]:
        top = latest["items"][0]
        symbol = str(top.get("symbol") or "SPY").strip().upper()
        strategy = str(top.get("strategy") or "BULL_PUT").strip().upper()
        score = float(top.get("score") or 0.62)
        return symbol, strategy, score

    try:
        out = run_universe_scan_from_ibkr_settings(profile=profile, regime="NORMAL", top_n=6)
    except Exception as _exc:  # IBKR settings unavailable — fall back to manual scan
        logger.debug("IBKR settings scan failed, falling back: %s", _exc)
        out = run_universe_scan(profile=profile, symbols=["SPY", "QQQ", "IWM"], regime="NORMAL", top_n=3, source="manual")

    items = out.get("items") if isinstance(out, dict) else None
    if isinstance(items, list) and items:
        top = items[0]
        symbol = str(top.get("symbol") or "SPY").strip().upper()
        strategy = str(top.get("strategy") or "BULL_PUT").strip().upper()
        score = float(top.get("score") or 0.62)
        return symbol, strategy, score

    return "SPY", "BULL_PUT", 0.62


def _bootstrap_runtime_data(profile: str = "paper") -> dict[str, Any]:
    init_execution_schema()
    con = _connect()
    snapshots_before = _count_profile_rows(con, "paper_equity_snapshots", profile)
    trades_before = _count_profile_rows(con, "paper_trades", profile)
    con.close()

    seeded_snapshots = 0
    seeded_trades = 0
    symbol = "SPY"
    strategy = "BULL_PUT"

    if snapshots_before > 0 and trades_before > 0:
        return {
            "ok": True,
            "changed": False,
            "profile": profile,
            "seeded_snapshots": 0,
            "seeded_trades": 0,
            "symbol": symbol,
            "strategy": strategy,
        }

    symbol, strategy, base_score = _pick_bootstrap_candidate(profile)
    today = datetime.now(timezone.utc).date()

    if snapshots_before == 0:
        equity = 10000.0
        start = today - timedelta(days=59)
        for i in range(60):
            d = start + timedelta(days=i)
            drift = 0.0009 if (i % 7) not in {2, 5} else -0.0004
            equity = round(equity * (1.0 + drift), 2)
            record_equity_snapshot(
                profile=profile,
                asof_date=d,
                equity=equity,
                note="AUTO_BOOTSTRAP_DEMO startup warmup",
            )
            seeded_snapshots += 1

    if trades_before == 0:
        pnl_values = [32, -12, 28, 24, -10, 35, 18, 22, -14, 30, 26, 19, -11, 27, 21, -9, 25, 16, 20, -8]
        start_day = today - timedelta(days=len(pnl_values) + 8)
        for idx, pnl in enumerate(pnl_values):
            d = start_day + timedelta(days=idx)
            entry = datetime.combine(d, time_cls(hour=14, minute=35), tzinfo=timezone.utc)
            exit_ = entry + timedelta(hours=2, minutes=10)
            score = max(0.0, min(1.0, base_score + ((idx % 5) - 2) * 0.015))
            slip = round(0.7 + (idx % 4) * 0.12, 2)
            kelly = round(max(0.03, min(0.15, 0.08 + ((idx % 3) - 1) * 0.01)), 3)
            exit_reason = "TAKE_PROFIT" if pnl >= 0 else "STOP_LOSS"
            record_trade(
                profile=profile,
                symbol=symbol,
                strategy=strategy,
                entry_ts_utc=entry,
                exit_ts_utc=exit_,
                strikes=[100.0, 105.0],
                regime_at_entry="NORMAL",
                score_at_entry=score,
                kelly_fraction=kelly,
                exit_reason=exit_reason,
                pnl=float(pnl),
                pnl_pct=round(float(pnl) / 10000.0, 4),
                slippage_ticks=slip,
                violations=0,
                note="AUTO_BOOTSTRAP_DEMO startup warmup",
            )
            seeded_trades += 1

    return {
        "ok": True,
        "changed": bool(seeded_snapshots or seeded_trades),
        "profile": profile,
        "seeded_snapshots": seeded_snapshots,
        "seeded_trades": seeded_trades,
        "symbol": symbol,
        "strategy": strategy,
    }


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/opz/state")
def opz_state() -> Dict[str, Any]:
    return _load_state()


@app.get("/opz/release_status")
def opz_release_status() -> Dict[str, Any]:
    return {"format": "md", "content": _run_release_status_md()}


@app.post("/opz/bootstrap")
def opz_bootstrap(profile: str = "paper", allow_demo: bool = False) -> Dict[str, Any]:
    profile_norm = _clean_text(profile, "profile")
    if not allow_demo:
        raise HTTPException(
            status_code=409,
            detail={
                "stage": "bootstrap",
                "reason": "demo bootstrap disabled by default; retry with allow_demo=true only for explicit demo warmup",
                "profile": profile_norm,
            },
        )
    return _bootstrap_runtime_data(profile=profile_norm)


@app.get("/opz/narrator/tutorial")
def opz_narrator_tutorial(path: Optional[str] = None) -> Dict[str, Any]:
    tutorial_path = _resolve_safe_path(path, field_name="path", allowed_roots=[ALLOWED_TUTORIAL_ROOT])
    out = _read_tutorial_markdown(path=tutorial_path)
    content = str(out.get("content") or "")
    return {
        "path": out.get("path"),
        "exists": bool(out.get("exists")),
        "content": content,
        "lines": len(content.splitlines()),
    }


@app.post("/opz/narrator/tts")
def opz_narrator_tts(req: NarratorTtsRequest) -> Dict[str, Any]:
    return _run_qwen_tts(action=req.action, text=req.text)


@app.post("/opz/ai/prompt")
def opz_ai_prompt(req: AiPromptRequest) -> Dict[str, Any]:
    return _run_ollama_prompt(prompt=req.prompt)


@app.post("/opz/ai/chat")
def opz_ai_chat(req: AiChatRequest) -> Dict[str, Any]:
    normalized = _normalize_ai_chat_messages(req.messages, req.prompt)
    if not normalized:
        raise HTTPException(status_code=400, detail="messages vuoto")

    composed_prompt = _compose_ai_chat_prompt(normalized)
    out = _run_ollama_prompt(prompt=composed_prompt)
    reply = str(out.get("response") or out.get("stdout") or "").strip()

    timeline = [dict(x) for x in normalized]
    if reply:
        timeline.append({"role": "assistant", "content": reply})

    return {
        "ok": bool(out.get("ok")),
        "model": out.get("model"),
        "reply": reply,
        "messages": timeline,
        "stdout": out.get("stdout", ""),
        "stderr": out.get("stderr", ""),
        "returncode": int(out.get("returncode", 1)),
        "duration_ms": int(out.get("duration_ms", 0)),
    }
@app.get("/opz/last_actions")
def opz_last_actions(limit: int = 5) -> Dict[str, Any]:
    n = max(1, min(int(limit), 20))
    init_execution_schema()
    con = _connect()

    snapshots_rows = con.execute(
        """
        SELECT created_at, asof_date, equity, note, profile
        FROM paper_equity_snapshots
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (n,),
    ).fetchall()
    trades_rows = con.execute(
        """
        SELECT created_at, symbol, strategy, pnl, pnl_pct, slippage_ticks, violations, note, profile,
               entry_ts_utc, exit_ts_utc, strikes_json, regime_at_entry, score_at_entry, kelly_fraction, exit_reason
        FROM paper_trades
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (n,),
    ).fetchall()
    opp_rows = con.execute(
        """
        SELECT created_at, batch_id, symbol, strategy, score, regime, scanner_name, source, decision, confidence, note, profile
        FROM operator_opportunity_decisions
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (n,),
    ).fetchall()
    con.close()

    previews_raw = _read_jsonl_tail(LOG_DIR / "operator_previews.jsonl", n)
    confirms_raw = _read_jsonl_tail(LOG_DIR / "operator_confirms.jsonl", n)

    snapshots = [
        {
            "ts_utc": _dt_to_iso_utc(r[0]),
            "asof_date": str(r[1]) if r[1] is not None else "",
            "equity": float(r[2]) if r[2] is not None else None,
            "note": str(r[3]) if r[3] is not None else "",
            "profile": str(r[4]) if r[4] is not None else "",
        }
        for r in snapshots_rows
    ]

    trades = [
        {
            "ts_utc": _dt_to_iso_utc(r[0]),
            "symbol": str(r[1]) if r[1] is not None else "",
            "strategy": str(r[2]) if r[2] is not None else "",
            "pnl": float(r[3]) if r[3] is not None else None,
            "pnl_pct": float(r[4]) if r[4] is not None else None,
            "slippage_ticks": float(r[5]) if r[5] is not None else None,
            "violations": int(r[6]) if r[6] is not None else 0,
            "note": str(r[7]) if r[7] is not None else "",
            "profile": str(r[8]) if r[8] is not None else "",
            "entry_ts_utc": _dt_to_iso_utc(r[9]),
            "exit_ts_utc": _dt_to_iso_utc(r[10]),
            "strikes_json": str(r[11]) if r[11] is not None else "",
            "regime_at_entry": str(r[12]) if r[12] is not None else "",
            "score_at_entry": float(r[13]) if r[13] is not None else None,
            "kelly_fraction": float(r[14]) if r[14] is not None else None,
            "exit_reason": str(r[15]) if r[15] is not None else "",
        }
        for r in trades_rows
    ]

    previews = []
    for item in previews_raw:
        pv = item.get("preview") if isinstance(item.get("preview"), dict) else {}
        previews.append(
            {
                "confirm_token": item.get("token"),
                "ts_unix": pv.get("ts_unix"),
                "symbol": pv.get("symbol"),
                "strategy": pv.get("strategy"),
            }
        )

    confirms = []
    for item in confirms_raw:
        confirms.append(
            {
                "confirm_token": item.get("confirm_token"),
                "ts_unix": item.get("ts_unix"),
                "operator": item.get("operator"),
                "decision": item.get("decision"),
            }
        )

    opportunity_decisions = [
        {
            "ts_utc": _dt_to_iso_utc(r[0]),
            "batch_id": str(r[1]) if r[1] is not None else "",
            "symbol": str(r[2]) if r[2] is not None else "",
            "strategy": str(r[3]) if r[3] is not None else "",
            "score": float(r[4]) if r[4] is not None else None,
            "regime": str(r[5]) if r[5] is not None else "",
            "scanner_name": str(r[6]) if r[6] is not None else "",
            "source": str(r[7]) if r[7] is not None else "",
            "decision": str(r[8]) if r[8] is not None else "",
            "confidence": int(r[9]) if r[9] is not None else 0,
            "note": str(r[10]) if r[10] is not None else "",
            "profile": str(r[11]) if r[11] is not None else "",
        }
        for r in opp_rows
    ]

    return {
        "limit": n,
        "paper_snapshots": snapshots,
        "paper_trades": trades,
        "execution_previews": previews,
        "execution_confirms": confirms,
        "opportunity_decisions": opportunity_decisions,
    }


@app.get("/opz/paper/summary")
def opz_paper_summary(profile: str = "paper", window_days: int = 60, asof_date: Optional[str] = None) -> Dict[str, Any]:
    d = None
    if asof_date:
        try:
            from datetime import date as _date

            d = _date.fromisoformat(asof_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid asof_date (expected YYYY-MM-DD)")
    s = compute_paper_summary(profile=profile, window_days=window_days, as_of_date=d)
    return {
        "profile": s.profile,
        "window_days": s.window_days,
        "as_of_date": s.as_of_date.isoformat(),
        "equity_points": s.equity_points,
        "trades": s.trades,
        "sharpe_annualized": s.sharpe_annualized,
        "max_drawdown": s.max_drawdown,
        "win_rate": s.win_rate,
        "profit_factor": s.profit_factor,
        "avg_slippage_ticks": s.avg_slippage_ticks,
        "compliance_violations": s.compliance_violations,
        "gates": s.gates,
    }


@app.get("/opz/paper/equity_history")
def opz_paper_equity_history(profile: str = "paper", limit: int = 60) -> Dict[str, Any]:
    """
    Ultimi N snapshot equity ordinati per data ASC (per sparkline).

    Response:
      ok              bool
      profile         str
      n_points        int
      latest_equity   float | null
      initial_equity  float | null
      points          list[{date: str, equity: float}]
    """
    n = max(1, min(int(limit), 500))
    con = _connect()
    try:
        rows = con.execute(
            """
            SELECT asof_date, equity
            FROM paper_equity_snapshots
            WHERE profile = ?
              AND equity IS NOT NULL
            ORDER BY asof_date DESC
            LIMIT ?
            """,
            (profile, n),
        ).fetchall()
    finally:
        con.close()

    # Reverse → ASC per sparkline left-to-right
    points = [
        {"date": str(r[0]), "equity": float(r[1])}
        for r in reversed(rows)
    ]
    latest_equity = points[-1]["equity"] if points else None
    initial_equity = points[0]["equity"] if points else None

    return {
        "ok": True,
        "profile": profile,
        "n_points": len(points),
        "latest_equity": latest_equity,
        "initial_equity": initial_equity,
        "points": points,
    }


@app.post("/opz/paper/equity_snapshot")
def opz_paper_equity_snapshot(req: EquitySnapshotRequest) -> Dict[str, Any]:
    profile = _clean_text(req.profile, "profile")
    equity = _require_finite(req.equity, "equity")
    if equity <= 0:
        raise HTTPException(status_code=400, detail="invalid equity (must be > 0)")
    try:
        from datetime import date as _date

        d = _date.fromisoformat(req.asof_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid asof_date (expected YYYY-MM-DD)")
    sid = record_equity_snapshot(profile=profile, asof_date=d, equity=equity, note=req.note.strip())
    return {"ok": True, "snapshot_id": sid}


@app.post("/opz/paper/trade")
def opz_paper_trade(req: TradeJournalRequest) -> Dict[str, Any]:
    profile = _clean_text(req.profile, "profile")
    symbol = _clean_text(req.symbol, "symbol")
    strategy = _clean_text(req.strategy, "strategy")

    entry_ts = _parse_ts_utc(req.entry_ts_utc, "entry_ts_utc")
    exit_ts = _parse_ts_utc(req.exit_ts_utc, "exit_ts_utc")

    pnl = _require_finite(req.pnl, "pnl")
    pnl_pct = _require_finite(req.pnl_pct, "pnl_pct") if req.pnl_pct is not None else None
    slippage_ticks = _require_finite(req.slippage_ticks, "slippage_ticks") if req.slippage_ticks is not None else None
    score_at_entry = _require_finite(req.score_at_entry, "score_at_entry") if req.score_at_entry is not None else None
    kelly_fraction = _require_finite(req.kelly_fraction, "kelly_fraction") if req.kelly_fraction is not None else None

    if slippage_ticks is not None and slippage_ticks < 0:
        raise HTTPException(status_code=400, detail="invalid slippage_ticks (must be >= 0)")
    if kelly_fraction is not None and (kelly_fraction < 0 or kelly_fraction > 1):
        raise HTTPException(status_code=400, detail="invalid kelly_fraction (must be in [0,1])")

    regime_at_entry = req.regime_at_entry.strip() if req.regime_at_entry else None
    exit_reason = req.exit_reason.strip() if req.exit_reason else None
    note = req.note.strip()

    tid = record_trade(
        profile=profile,
        symbol=symbol,
        strategy=strategy,
        entry_ts_utc=entry_ts,
        exit_ts_utc=exit_ts,
        strikes=req.strikes,
        regime_at_entry=regime_at_entry,
        score_at_entry=score_at_entry,
        kelly_fraction=kelly_fraction,
        exit_reason=exit_reason,
        pnl=pnl,
        pnl_pct=pnl_pct,
        slippage_ticks=slippage_ticks,
        violations=req.violations,
        note=note,
    )
    return {"ok": True, "trade_id": tid}


@app.post("/opz/execution/preview", response_model=PreviewResponse)
def execution_preview(req: PreviewRequest) -> PreviewResponse:
    symbol = _clean_text(req.symbol, "symbol")
    strategy = _clean_text(req.strategy, "strategy")

    token = secrets.token_urlsafe(24)
    preview = {
        "symbol": symbol,
        "strategy": strategy,
        "payload": req.payload,
        "ts_unix": int(time.time()),
        "note": "PREVIEW ONLY. Requires explicit operator confirmation (confirm endpoint).",
    }
    with (LOG_DIR / "operator_previews.jsonl").open("a", encoding="utf-8") as _fh:
        _fh.write(json.dumps({"token": token, "preview": preview}, ensure_ascii=False) + "\n")
    return PreviewResponse(confirm_token=token, preview=preview)


@app.post("/opz/execution/confirm")
def execution_confirm(req: ConfirmRequest) -> Dict[str, Any]:
    operator = _clean_text(req.operator, "operator")
    if req.decision not in {"APPROVE", "REJECT"}:
        raise HTTPException(status_code=400, detail="invalid decision")
    confirm_token = _clean_text(req.confirm_token, "confirm_token")
    preview_event = _find_preview_event(confirm_token)
    if preview_event is None or not isinstance(preview_event.get("preview"), dict):
        raise HTTPException(status_code=409, detail={"stage": "execution_confirm", "reason": "preview not found for confirm_token"})
    if _confirm_token_already_used(confirm_token):
        raise HTTPException(status_code=409, detail={"stage": "execution_confirm", "reason": "confirm_token already used"})
    if not _confirm_payload_matches_preview(req.payload, preview_event["preview"]):
        raise HTTPException(status_code=409, detail={"stage": "execution_confirm", "reason": "confirm payload does not match preview"})
    event = {
        "confirm_token": confirm_token,
        "operator": operator,
        "decision": req.decision,
        "payload": req.payload,
        "ts_unix": int(time.time()),
        "note": "HUMAN CONFIRMED. No broker submit performed in F6-T1 skeleton.",
    }
    with (LOG_DIR / "operator_confirms.jsonl").open("a", encoding="utf-8") as _fh:
        _fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return {"ok": True, "event": event}


@app.post("/opz/opportunity/decision")
def opz_opportunity_decision(req: OpportunityDecisionRequest) -> Dict[str, Any]:
    profile = _clean_text(req.profile, "profile")
    symbol = _clean_text(req.symbol, "symbol").upper()
    strategy = req.strategy.strip().upper() if req.strategy else ""
    regime = req.regime.strip().upper() if req.regime else ""
    scanner_name = req.scanner_name.strip() if req.scanner_name else ""
    source = req.source.strip() if req.source else ""
    note = req.note.strip()
    if req.decision in {"REJECT", "MODIFY"} and not note:
        raise HTTPException(status_code=400, detail={"stage": "opportunity_decision", "reason": f"note required for {req.decision}"})
    score = None if req.score is None else _require_finite(req.score, "score")
    ts = datetime.now(timezone.utc)
    ts_s = ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    decision_id = secrets.token_urlsafe(12)
    prov = _prov(profile, ts_s)

    init_execution_schema()
    con = _connect()
    con.execute(
        """
        INSERT INTO operator_opportunity_decisions
        (decision_id, profile, batch_id, symbol, strategy, score, regime, scanner_name, source, decision, confidence, note, created_at, source_system, source_mode, source_quality, asof_ts, received_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            profile,
            req.batch_id,
            symbol,
            strategy,
            score,
            regime,
            scanner_name,
            source,
            req.decision,
            int(req.confidence),
            note,
            ts_s,
            *prov,
        ),
    )
    if hasattr(con, "commit"):
        con.commit()
    con.close()
    return {
        "ok": True,
        "decision": {
            "decision_id": decision_id,
            "profile": profile,
            "batch_id": req.batch_id,
            "symbol": symbol,
            "strategy": strategy,
            "score": score,
            "regime": regime,
            "scanner_name": scanner_name,
            "source": source,
            "decision": req.decision,
            "confidence": int(req.confidence),
            "note": note,
            "ts_utc": ts.isoformat().replace("+00:00", "Z"),
        },
    }


@app.get("/opz/universe/latest")
def opz_universe_latest() -> Dict[str, Any]:
    return fetch_latest_universe_batch()


@app.get("/opz/universe/ibkr_context")
def opz_universe_ibkr_context(settings_path: Optional[str] = None) -> Dict[str, Any]:
    safe_settings_path = _resolve_safe_path(
        settings_path,
        field_name="settings_path",
        allowed_roots=[ALLOWED_SETTINGS_ROOT],
    )
    return extract_ibkr_universe_context(settings_path=safe_settings_path)



@app.get("/opz/universe/provenance")
def opz_universe_provenance(
    settings_path: Optional[str] = None,
    ocr_path: Optional[str] = None,
    regime: str = "NORMAL",
    batch_id: Optional[str] = None,
) -> Dict[str, Any]:
    reg = (regime or "NORMAL").strip().upper()
    if reg not in {"NORMAL", "CAUTION", "SHOCK"}:
        raise HTTPException(status_code=400, detail="invalid regime (expected NORMAL|CAUTION|SHOCK)")
    safe_settings_path = _resolve_safe_path(
        settings_path,
        field_name="settings_path",
        allowed_roots=[ALLOWED_SETTINGS_ROOT],
    )
    safe_ocr_path = _resolve_safe_path(
        ocr_path,
        field_name="ocr_path",
        allowed_roots=ALLOWED_OCR_ROOTS,
    )
    safe_batch_id = batch_id.strip() if batch_id else None
    return build_universe_compare(settings_path=safe_settings_path, ocr_path=safe_ocr_path, regime=reg, batch_id=safe_batch_id)

@app.post("/opz/universe/scan")
def opz_universe_scan(req: UniverseScanRequest) -> Dict[str, Any]:
    profile = _clean_text(req.profile, "profile")
    regime = req.regime.strip().upper() if req.regime else "NORMAL"
    if regime not in {"NORMAL", "CAUTION", "SHOCK"}:
        raise HTTPException(status_code=400, detail="invalid regime (expected NORMAL|CAUTION|SHOCK)")

    source = (req.source or "auto").strip().lower()
    if source not in {"auto", "manual", "ibkr_settings"}:
        raise HTTPException(status_code=400, detail="invalid source (expected auto|manual|ibkr_settings)")

    symbols = req.symbols if req.symbols is None else [str(x) for x in req.symbols]
    safe_settings_path = _resolve_safe_path(
        req.settings_path,
        field_name="settings_path",
        allowed_roots=[ALLOWED_SETTINGS_ROOT],
    )

    try:
        if source == "ibkr_settings" or (source == "auto" and not symbols):
            return run_universe_scan_from_ibkr_settings(
                profile=profile,
                regime=regime,
                top_n=req.top_n,
                scanner_name=req.scanner_name,
                settings_path=safe_settings_path,
            )

        return run_universe_scan(
            profile=profile,
            symbols=symbols,
            regime=regime,
            top_n=req.top_n,
            source="manual",
            ibkr_settings_path=safe_settings_path,
            ibkr_settings_exists=bool(safe_settings_path and Path(safe_settings_path).exists()),
        )
    except UniverseDataUnavailableError as exc:
        raise HTTPException(status_code=409, detail={"stage": "universe_scan", **exc.detail}) from exc









@app.post("/opz/opportunity/scan_full")
def opz_opportunity_scan_full(req: ScanFullRequest) -> Dict[str, Any]:
    """Full opportunity scan: IV history -> chain fetch -> analytics -> 4-pillar score.

    Returns a ranked list of OpportunityCandidate (score >= min_score).
    Results are persisted to opportunity_candidates and opportunity_chain_snapshots.
    Watermark: data_mode field reflects OPZ_DATA_MODE env var.
    """
    import dataclasses

    profile = _clean_text(req.profile, "profile")
    regime = (req.regime or "NORMAL").strip().upper()
    if regime not in {"NORMAL", "CAUTION", "SHOCK"}:
        raise HTTPException(status_code=400, detail="invalid regime (expected NORMAL|CAUTION|SHOCK)")

    symbols = [str(s).strip().upper() for s in (req.symbols or []) if str(s).strip()]
    if not symbols and regime != "SHOCK":
        raise HTTPException(status_code=400, detail="symbols list is empty")

    from strategy.opportunity_scanner import scan_opportunities
    from execution.storage import init_execution_schema, save_opportunity_scan

    batch_id = secrets.token_hex(8)

    try:
        result = scan_opportunities(
            profile=profile,
            regime=regime,
            symbols=symbols or None,
            top_n=req.top_n,
            account_size=req.account_size,
            min_score=req.min_score,
            signal_map=req.signal_map,
            signal_pct_map=req.signal_pct_map,
            use_cache=req.use_cache,
        )
    except Exception as exc:
        logger.exception("SCAN_FULL_ERROR profile=%s regime=%s", profile, regime)
        raise HTTPException(status_code=502, detail={"stage": "scan", "error": str(exc)}) from exc

    try:
        init_execution_schema()
        save_opportunity_scan(batch_id=batch_id, profile=profile, scan_result=result)
    except Exception as exc:
        logger.warning("SCAN_SAVE_WARN batch=%s %s", batch_id, exc)

    candidates_out = [
        dataclasses.asdict(c)
        if dataclasses.is_dataclass(c) and not isinstance(c, type)
        else dict(c)
        for c in result.candidates
    ]

    return {
        "ok": True,
        "batch_id": batch_id,
        "profile": result.profile,
        "regime": result.regime,
        "data_mode": result.data_mode,
        "events_source": getattr(result, "events_source", "yfinance"),
        "scan_ts": result.scan_ts,
        "symbols_scanned": result.symbols_scanned,
        "symbols_with_chain": result.symbols_with_chain,
        "filtered_count": result.filtered_count,
        "cache_used": result.cache_used,
        "cache_age_hours": result.cache_age_hours,
        "ranking_suspended": result.ranking_suspended,
        "suspension_reason": result.suspension_reason,
        "candidates": candidates_out,
    }


@app.get("/opz/opportunity/ev_report")
def opz_opportunity_ev_report(
    profile: str = "paper",
    window_days: int = 30,
) -> Dict[str, Any]:
    """Report EV: statistiche sui candidati salvati negli ultimi window_days.

    Legge opportunity_candidates per profilo/finestra.
    opportunity_ev_tracking è popolato quando i trade vengono collegati.
    Watermark DATA_MODE nel risultato.
    """
    from execution.storage import init_execution_schema, _connect

    profile = (profile or "paper").strip()
    if window_days < 1 or window_days > 365:
        raise HTTPException(status_code=400, detail="window_days deve essere tra 1 e 365")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()

    init_execution_schema()
    con = _connect()
    try:
        rows = con.execute(
            """
            SELECT score, strategy, regime, human_review_required, events_flag, data_mode
            FROM opportunity_candidates
            WHERE profile = ? AND scan_ts >= ?
            ORDER BY scan_ts DESC
            """,
            (profile, cutoff),
        ).fetchall()

        total     = len(rows)
        below_70  = sum(1 for r in rows if r[0] is not None and r[0] < 70)
        s_70_80   = sum(1 for r in rows if r[0] is not None and 70 <= r[0] < 80)
        s_80_plus = sum(1 for r in rows if r[0] is not None and r[0] >= 80)

        strategies: dict[str, int] = {}
        regimes:    dict[str, int] = {}
        human_rev   = 0
        evts_flag   = 0
        data_modes: set[str] = set()

        for _score, strategy, regime, human_rev_req, events_flag, data_mode in rows:
            if strategy:
                strategies[strategy] = strategies.get(strategy, 0) + 1
            if regime:
                regimes[regime] = regimes.get(regime, 0) + 1
            if human_rev_req:
                human_rev += 1
            if events_flag:
                evts_flag += 1
            if data_mode:
                data_modes.add(data_mode)

        tracked_row = con.execute(
            "SELECT COUNT(*) FROM opportunity_ev_tracking WHERE profile = ?",
            (profile,),
        ).fetchone()
        total_tracked = tracked_row[0] if tracked_row else 0

    finally:
        con.close()

    return {
        "ok": True,
        "profile": profile,
        "window_days": window_days,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data_mode": ", ".join(sorted(data_modes)) if data_modes else os.environ.get("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED"),
        "total_candidates": total,
        "total_tracked": total_tracked,
        "score_distribution": {"below_70": below_70, "score_70_80": s_70_80, "score_80_plus": s_80_plus},
        "strategies": strategies,
        "regimes": regimes,
        "human_review_required": human_rev,
        "events_flagged": evts_flag,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ROC5 — GET /opz/ibkr/status
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/opz/ibkr/status")
def opz_ibkr_status(try_connect: bool = False) -> Dict[str, Any]:
    """
    Stato della connessione IBKR (TWS/Gateway).

    Query params:
      try_connect=true  → tenta connessione se non già connessa (timeout 2s)
      try_connect=false → solo lettura stato corrente (default)

    Response:
      ok            bool
      connected     bool
      host          str
      port          int | null
      client_id     int
      source_system str   — "ibkr_live" | "yfinance"
      connected_at  str | null  — ISO timestamp UTC
      ports_probed  list[int]   — porte candidate (ordine priorità)
      message       str   — descrizione leggibile dello stato
    """
    from execution.ibkr_connection import get_manager, IBKR_PORTS

    mgr = get_manager()
    # Ottieni info prima (legge is_connected una sola volta)
    info = mgr.connection_info()
    if try_connect and not info["connected"]:
        mgr.try_connect()
        info = mgr.connection_info()

    connected = info["connected"]

    if connected:
        message = f"Connesso a TWS/Gateway su porta {info['port']}"
    elif try_connect:
        message = "TWS/Gateway non disponibile — fallback yfinance attivo"
    else:
        message = "Stato corrente: non connesso (usa try_connect=true per tentare)"

    return {
        "ok": True,
        "connected": connected,
        "host": info["host"],
        "port": info["port"],
        "client_id": info["client_id"],
        "source_system": info["source_system"],
        "connected_at": info["connected_at"],
        "ports_probed": IBKR_PORTS,
        "message": message,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ROC6 — GET /opz/ibkr/account
# ─────────────────────────────────────────────────────────────────────────────

def _empty_account_response(connected: bool, message: str) -> Dict[str, Any]:
    """Risposta account vuota riutilizzata per 'non connesso' e 'fetch fallito'."""
    return {
        "ok": True,
        "connected": connected,
        "source_system": "ibkr_live" if connected else "yfinance",
        "account_id": None,
        "net_liquidation": None,
        "realized_pnl": None,
        "unrealized_pnl": None,
        "buying_power": None,
        "positions": [],
        "message": message,
    }

@app.get("/opz/ibkr/account")
def opz_ibkr_account() -> Dict[str, Any]:
    """
    Sommario account IBKR (net liquidation, P&L, posizioni aperte).

    Richiede connessione attiva a TWS/Gateway.
    Se non connesso → ok=True, connected=False, dati vuoti.

    Response:
      ok                bool
      connected         bool
      source_system     str
      account_id        str | null
      net_liquidation   float | null
      realized_pnl      float | null
      unrealized_pnl    float | null
      buying_power      float | null
      positions         list[PositionItem]
      message           str
    """
    from execution.ibkr_connection import get_manager

    mgr = get_manager()

    if not mgr.is_connected:
        return _empty_account_response(False, "Non connesso a TWS/Gateway — chiama prima /opz/ibkr/status?try_connect=true")

    try:
        ib = mgr._ib
        if ib is None or not ib.isConnected():
            raise RuntimeError("IB instance not available")

        # Account summary: tags IBKR standard
        tags = [
            "NetLiquidation", "RealizedPnL", "UnrealizedPnL",
            "BuyingPower", "AccountCode",
        ]
        summary = ib.accountSummary()  # list of AccountValue

        def _get(tag: str) -> str | None:
            for av in summary:
                if av.tag == tag:
                    return av.value
            return None

        def _float(tag: str) -> float | None:
            v = _get(tag)
            try:
                return float(v) if v is not None else None
            except (ValueError, TypeError):
                return None

        account_id = _get("AccountCode")
        net_liq = _float("NetLiquidation")
        realized = _float("RealizedPnL")
        unrealized = _float("UnrealizedPnL")
        buying_power = _float("BuyingPower")

        # Positions
        portfolio = ib.portfolio()  # list of PortfolioItem
        positions_out = []
        for item in portfolio:
            contract = item.contract
            positions_out.append({
                "symbol":          getattr(contract, "symbol", "?"),
                "sec_type":        getattr(contract, "secType", "?"),
                "expiry":          getattr(contract, "lastTradeDateOrContractMonth", None),
                "strike":          getattr(contract, "strike", None),
                "right":           getattr(contract, "right", None),
                "quantity":        item.position,
                "avg_cost":        item.averageCost,
                "market_price":    item.marketPrice,
                "market_value":    item.marketValue,
                "unrealized_pnl":  item.unrealizedPNL,
                "realized_pnl":    item.realizedPNL,
            })

        return {
            "ok": True,
            "connected": True,
            "source_system": "ibkr_live",
            "account_id": account_id,
            "net_liquidation": net_liq,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "buying_power": buying_power,
            "positions": positions_out,
            "message": f"Account {account_id} — {len(positions_out)} posizioni aperte",
        }

    except Exception as exc:
        logger.warning("IBKR account fetch failed: %s", exc)
        return _empty_account_response(True, f"Connesso ma fetch account fallito: {exc}")


@app.get("/opz/regime/current")
def opz_regime_current(window: int = 20) -> Dict[str, Any]:
    """
    Regime corrente basato sugli ultimi N candidati registrati in DuckDB.

    Parametri:
      window  int  — quanti record recenti considerare (default 20, max 100)

    Response:
      ok              bool
      regime          str   — regime più frequente (NORMAL/CAUTION/SHOCK/UNKNOWN)
      regime_counts   dict  — {NORMAL: int, CAUTION: int, SHOCK: int}
      regime_pct      dict  — {NORMAL: float, CAUTION: float, SHOCK: float}
      last_scan_ts    str|null — ISO timestamp ultimo candidato
      n_recent        int   — record trovati nella finestra
      source          str   — "opportunity_candidates" | "paper_trades" | "none"
    """
    n = max(1, min(int(window), 100))
    counts: dict[str, int] = {"NORMAL": 0, "CAUTION": 0, "SHOCK": 0}
    last_scan_ts: str | None = None
    source = "none"
    regime = "UNKNOWN"

    try:
        import duckdb
        import execution.storage as _st
        db_path = str(_st.EXEC_DB_PATH)
        if Path(db_path).exists():
            con = duckdb.connect(db_path, read_only=True)
            try:
                rows = con.execute(
                    """
                    SELECT regime, scan_ts
                    FROM opportunity_candidates
                    WHERE regime IS NOT NULL
                    ORDER BY scan_ts DESC
                    LIMIT ?
                    """,
                    (n,),
                ).fetchall()
                if rows:
                    source = "opportunity_candidates"
                    for row in rows:
                        lbl = str(row[0]).strip().upper()
                        if lbl in counts:
                            counts[lbl] += 1
                    # last_scan_ts = most recent (first row after DESC order)
                    ts_raw = rows[0][1]
                    if ts_raw is not None:
                        last_scan_ts = ts_raw.isoformat() if hasattr(ts_raw, "isoformat") else str(ts_raw)
                else:
                    # Fallback: paper_trades
                    rows2 = con.execute(
                        """
                        SELECT regime_at_entry, entry_ts_utc
                        FROM paper_trades
                        WHERE regime_at_entry IS NOT NULL
                        ORDER BY entry_ts_utc DESC
                        LIMIT ?
                        """,
                        (n,),
                    ).fetchall()
                    if rows2:
                        source = "paper_trades"
                        for row in rows2:
                            lbl = str(row[0]).strip().upper()
                            if lbl in counts:
                                counts[lbl] += 1
                        ts_raw2 = rows2[0][1]
                        if ts_raw2 is not None:
                            last_scan_ts = str(ts_raw2)
            finally:
                con.close()
    except Exception:
        pass

    total = sum(counts.values())
    regime_pct = {
        k: round(v / total * 100, 1) if total > 0 else 0.0
        for k, v in counts.items()
    }

    if total > 0:
        regime = max(counts, key=lambda k: counts[k])

    return {
        "ok": True,
        "regime": regime,
        "regime_counts": counts,
        "regime_pct": regime_pct,
        "last_scan_ts": last_scan_ts,
        "n_recent": total,
        "source": source,
    }


@app.get("/opz/system/status")
def opz_system_status() -> Dict[str, Any]:
    """
    Snapshot aggregato dello stato operativo del sistema.

    Campi ritornati:
      ok                     bool   — sempre True
      timestamp_utc          str    — ISO 8601
      api_online             bool   — True (se risponde, è online)
      kill_switch_active     bool   — file ops/kill_switch.trigger presente
      data_mode              str    — da OPZ_DATA_MODE env (o default)
      kelly_enabled          bool   — data_mode=VENDOR_REAL_CHAIN + n_closed≥50
      ibkr_connected         bool   — IBKRConnectionManager.is_connected
      ibkr_port              int|null
      ibkr_source_system     str    — "ibkr_live" | "yfinance"
      ibkr_connected_at      str|null
      execution_config_ready bool   — config/dev.toml o paper.toml esiste
      n_closed_trades        int    — da DuckDB paper_trades
      regime                 str    — ultima riga regime DuckDB o "UNKNOWN"
      signals                list[dict] — semafori operativi [name, status, detail]
    """
    ts_now = datetime.now(timezone.utc).isoformat()

    # ── Kill switch ───────────────────────────────────────────────────────────
    ks_path = Path("ops/kill_switch.trigger")
    kill_switch_active = ks_path.exists()

    # ── Data mode ─────────────────────────────────────────────────────────────
    data_mode = os.environ.get("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")

    # ── IBKR ──────────────────────────────────────────────────────────────────
    ibkr_connected = False
    ibkr_port: int | None = None
    ibkr_source_system = "yfinance"
    ibkr_connected_at: str | None = None
    try:
        from execution.ibkr_connection import get_manager as _get_ibkr_mgr
        _mgr = _get_ibkr_mgr()
        info = _mgr.connection_info()
        ibkr_connected = bool(info.get("connected"))
        ibkr_port = info.get("port")
        ibkr_source_system = info.get("source_system", "yfinance")
        ibkr_connected_at = info.get("connected_at")
    except Exception:
        pass

    # ── Execution config (ROOT-anchored paths) ────────────────────────────────
    execution_config_ready = (
        (ROOT / "config" / "dev.toml").exists()
        or (ROOT / "config" / "paper.toml").exists()
        or (ROOT / "config" / "live.toml").exists()
    )

    # ── n_closed_trades + regime — singola connessione DuckDB ─────────────────
    n_closed_trades = 0
    regime = "UNKNOWN"
    try:
        import duckdb
        import execution.storage as _st
        db_path = str(_st.EXEC_DB_PATH)
        if Path(db_path).exists():
            con = duckdb.connect(db_path, read_only=True)
            try:
                row_n = con.execute(
                    "SELECT COUNT(*) FROM paper_trades WHERE exit_ts_utc IS NOT NULL"
                ).fetchone()
                n_closed_trades = int(row_n[0]) if row_n else 0

                row_r = con.execute(
                    "SELECT regime FROM paper_trades WHERE regime IS NOT NULL ORDER BY entry_ts_utc DESC LIMIT 1"
                ).fetchone()
                if row_r:
                    regime = str(row_r[0])
            except Exception:
                pass
            finally:
                con.close()
    except Exception:
        pass

    # ── Kelly gate ────────────────────────────────────────────────────────────
    kelly_enabled = (data_mode == "VENDOR_REAL_CHAIN") and (n_closed_trades >= 50)

    # ── Semafori operativi ────────────────────────────────────────────────────
    signals: list[dict] = [
        {
            "name": "kill_switch",
            "status": "ALERT" if kill_switch_active else "OK",
            "detail": "ATTIVO — esecuzione bloccata" if kill_switch_active else "Inattivo",
        },
        {
            "name": "ibkr",
            "status": "OK" if ibkr_connected else "WARN",
            "detail": f"Porta {ibkr_port}" if ibkr_connected else "Fallback yfinance",
        },
        {
            "name": "data_mode",
            "status": "OK" if data_mode == "VENDOR_REAL_CHAIN" else "WARN",
            "detail": data_mode,
        },
        {
            "name": "kelly",
            "status": "OK" if kelly_enabled else "DISABLED",
            "detail": f"Abilitato (n={n_closed_trades})" if kelly_enabled
                      else f"Disabilitato (n={n_closed_trades} / data_mode={data_mode})",
        },
        {
            "name": "execution_config",
            "status": "OK" if execution_config_ready else "ALERT",
            "detail": "Config trovata" if execution_config_ready else "Nessun config trovato",
        },
    ]

    return {
        "ok": True,
        "timestamp_utc": ts_now,
        "api_online": True,
        "kill_switch_active": kill_switch_active,
        "data_mode": data_mode,
        "kelly_enabled": kelly_enabled,
        "ibkr_connected": ibkr_connected,
        "ibkr_port": ibkr_port,
        "ibkr_source_system": ibkr_source_system,
        "ibkr_connected_at": ibkr_connected_at,
        "execution_config_ready": execution_config_ready,
        "n_closed_trades": n_closed_trades,
        "regime": regime,
        "signals": signals,
    }


@app.post("/opz/demo_pipeline/auto")
def opz_demo_pipeline_auto(req: DemoPipelineAutoRequest) -> Dict[str, Any]:
    profile = _clean_text(req.profile, "profile")
    safe_settings_path = _resolve_safe_path(
        req.settings_path,
        field_name="settings_path",
        allowed_roots=[ALLOWED_SETTINGS_ROOT],
    )
    regime = (req.regime or "NORMAL").strip().upper()
    if regime not in {"NORMAL", "CAUTION", "SHOCK"}:
        raise HTTPException(status_code=400, detail="invalid regime (expected NORMAL|CAUTION|SHOCK)")

    backend = (req.extract_backend or "json-pass").strip().lower()
    if backend not in {"json-pass", "ollama"}:
        raise HTTPException(status_code=400, detail="invalid extract_backend (expected json-pass|ollama)")

    symbols_csv = ""
    if req.symbols:
        symbols_csv = ",".join([str(x).strip().upper() for x in req.symbols if str(x).strip()])

    fetch_args: list[str] = ["--profile", profile, "--limit", str(int(req.fetch_limit))]
    if symbols_csv:
        fetch_args.extend(["--symbols", symbols_csv])
    if safe_settings_path:
        fetch_args.extend(["--settings-path", safe_settings_path])

    fetch_run = _run_script_json("scripts/ibkr_demo_fetch_inbox.py", fetch_args)
    if not fetch_run["ok"]:
        raise HTTPException(status_code=502, detail={"stage": "fetch", "returncode": fetch_run["returncode"], "stderr": fetch_run["stderr"] or fetch_run["stdout"]})

    capture_run = _run_script_json(
        "scripts/capture_pages.py",
        ["--source", "ibkr_demo", "--freshness-minutes", "30", "--retention-days", "30", "--max-store-mb", "2048"],
    )
    if not capture_run["ok"]:
        raise HTTPException(status_code=502, detail={"stage": "capture", "returncode": capture_run["returncode"], "stderr": capture_run["stderr"] or capture_run["stdout"]})

    extract_run = _run_script_json(
        "scripts/extract_with_ollama.py",
        ["--backend", backend, "--model", "qwen2.5", "--max-retries", "2", "--limit", "500"],
    )
    if not extract_run["ok"]:
        raise HTTPException(status_code=502, detail={"stage": "extract", "returncode": extract_run["returncode"], "stderr": extract_run["stderr"] or extract_run["stdout"]})

    dataset_name = f"ibkr_demo_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    dataset_run = _run_script_json(
        "scripts/build_test_dataset.py",
        ["--dataset-name", dataset_name, "--model", "qwen2.5", "--prompt-version", "v1", "--limit", "50000"],
    )
    if not dataset_run["ok"]:
        raise HTTPException(status_code=502, detail={"stage": "dataset", "returncode": dataset_run["returncode"], "stderr": dataset_run["stderr"] or dataset_run["stdout"]})

    scan_out: Dict[str, Any] | None = None
    if req.auto_scan:
        try:
            scan_out = run_universe_scan_from_ibkr_settings(
                profile=profile,
                regime=regime,
                top_n=req.top_n,
                settings_path=safe_settings_path,
            )
        except UniverseDataUnavailableError as exc:
            raise HTTPException(status_code=409, detail={"stage": "universe_scan", **exc.detail}) from exc

    return {
        "ok": True,
        "policy": {"synthetic_data": False},
        "profile": profile,
        "regime": regime,
        "fetch": fetch_run.get("payload", {}),
        "capture": capture_run.get("payload", {}),
        "extract": extract_run.get("payload", {}),
        "dataset": dataset_run.get("payload", {}),
        "scan": scan_out,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ROC13 — Exit Candidates scoring
# ─────────────────────────────────────────────────────────────────────────────

# Exit score weights
_EXIT_W_THETA   = 3   # unrealized_pnl >= 70% of max_profit (target reached)
_EXIT_W_TIME    = 2   # dte_remaining <= 7 (gamma risk)
_EXIT_W_LOSS    = 4   # unrealized_pnl < -50% of max_profit (loss limit)

_THETA_DECAY_THRESHOLD = 0.70   # fraction of max_profit collected
_LOSS_LIMIT_THRESHOLD  = 0.50   # fraction of max_profit lost
_TIME_STOP_DTE         = 7      # remaining calendar days


def _parse_expiry(expiry_raw: Any) -> Optional[date]:
    """Parse YYYYMMDD or YYYY-MM-DD expiry string to date, or None on failure."""
    if not expiry_raw:
        return None
    s = str(expiry_raw).strip()
    try:
        return date.fromisoformat(s) if "-" in s else datetime.strptime(s, "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def _score_position(pos: dict, today: date | None = None) -> tuple[int, list[str]]:
    """
    Compute exit_score for one open option position.

    pos keys used:
      unrealized_pnl  float   — current unrealized P&L (positive = profitable)
      avg_cost        float   — average cost per share (credit received for shorts, positive)
      quantity        float   — number of shares (negative for short)
      expiry          str     — option expiry YYYYMMDD or YYYY-MM-DD

    Returns: (score: int, reasons: list[str])
    Score 0 = no exit signal.
    """
    if today is None:
        today = date.today()

    score = 0
    reasons: list[str] = []

    unrealized = float(pos.get("unrealized_pnl") or 0.0)
    avg_cost   = float(pos.get("avg_cost")       or 0.0)
    quantity   = float(pos.get("quantity")        or 0.0)

    # Max profit estimate: premium received = avg_cost * |quantity| * 100
    # For short options IBKR reports avg_cost as positive (credit received per share)
    max_profit = abs(avg_cost * quantity * 100) if (avg_cost != 0.0 and quantity != 0.0) else 0.0

    # Theta decay criterion
    if max_profit > 0.0 and unrealized >= _THETA_DECAY_THRESHOLD * max_profit:
        score += _EXIT_W_THETA
        reasons.append(f"theta_decay {unrealized/max_profit:.0%}")

    # Loss limit criterion
    if max_profit > 0.0 and unrealized < -_LOSS_LIMIT_THRESHOLD * max_profit:
        score += _EXIT_W_LOSS
        reasons.append(f"loss_limit {unrealized/max_profit:.0%}")

    # Time stop criterion
    exp_date = _parse_expiry(pos.get("expiry"))
    if exp_date is not None:
        dte_rem = (exp_date - today).days
        if dte_rem <= _TIME_STOP_DTE:
            score += _EXIT_W_TIME
            reasons.append(f"time_stop dte={dte_rem}")

    return score, reasons


@app.get("/opz/opportunity/exit_candidates")
def opz_exit_candidates(top_n: int = 10, min_score: int = 1) -> Dict[str, Any]:
    """
    Score open option positions for exit urgency.

    Source precedence:
      1. IBKR live positions  (if connected)
      2. paper_trades open    (exit_ts_utc IS NULL — fallback for dev/paper)

    Exit criteria (additive score):
      +3  theta_decay : unrealized_pnl >= 70% of max_profit
      +4  loss_limit  : unrealized_pnl < -50% of max_profit
      +2  time_stop   : dte_remaining <= 7

    Returns top_n candidates with score >= min_score, sorted desc by score.
    Always ok=True (errors degrade gracefully).
    """
    today = date.today()
    candidates: list[dict] = []
    source = "none"

    # ── 1. IBKR live positions ────────────────────────────────────────────────
    try:
        from execution.ibkr_connection import get_manager
        mgr = get_manager()
        if mgr.is_connected:
            ib = mgr._ib
            if ib is not None and ib.isConnected():
                portfolio = ib.portfolio()
                for item in portfolio:
                    contract = item.contract
                    if getattr(contract, "secType", "") not in ("OPT", "FOP"):
                        continue
                    pos = {
                        "symbol":         getattr(contract, "symbol", "?"),
                        "expiry":         getattr(contract, "lastTradeDateOrContractMonth", None),
                        "strike":         getattr(contract, "strike", None),
                        "right":          getattr(contract, "right", None),
                        "quantity":       item.position,
                        "avg_cost":       item.averageCost,
                        "market_price":   item.marketPrice,
                        "unrealized_pnl": item.unrealizedPNL,
                        "source":         "ibkr_live",
                    }
                    sc, reasons = _score_position(pos, today)
                    pos["exit_score"] = sc
                    pos["exit_reasons"] = reasons
                    candidates.append(pos)
                source = "ibkr_live"
    except Exception as exc:
        logger.debug("exit_candidates IBKR fetch skipped: %s", exc)

    # ── 2. Fallback: paper_trades open positions ──────────────────────────────
    if not candidates:
        try:
            db_path = str(DB_PATH)
            with duckdb.connect(db_path, read_only=True) as con:
                rows = con.execute(
                    """
                    SELECT symbol, entry_ts_utc, strikes_json, score_at_entry, pnl
                    FROM   paper_trades
                    WHERE  exit_ts_utc IS NULL
                    ORDER  BY entry_ts_utc DESC
                    LIMIT  100
                    """
                ).fetchall()
            for r in rows:
                sym         = str(r[0]) if r[0] else "?"
                strikes_raw = str(r[2]) if r[2] else "{}"
                pnl         = float(r[4]) if r[4] is not None else 0.0
                try:
                    strikes = json.loads(strikes_raw)
                except (json.JSONDecodeError, TypeError):
                    strikes = {}
                expiry = strikes.get("expiry") or strikes.get("exp") or strikes.get("expiry_date")
                pos = {
                    "symbol":         sym,
                    "expiry":         expiry,
                    "strike":         strikes.get("strike"),
                    "right":          strikes.get("right"),
                    "quantity":       -1,             # short = negative qty
                    "avg_cost":       float(strikes.get("premium", 0.0)),
                    "market_price":   None,
                    "unrealized_pnl": pnl,
                    "source":         "paper_trades",
                }
                sc, reasons = _score_position(pos, today)
                pos["exit_score"] = sc
                pos["exit_reasons"] = reasons
                candidates.append(pos)
            if candidates:
                source = "paper_trades"
        except Exception as exc:
            logger.debug("exit_candidates paper_trades fetch skipped: %s", exc)

    # ── 3. Filter + sort ──────────────────────────────────────────────────────
    filtered = [c for c in candidates if c["exit_score"] >= min_score]
    filtered.sort(key=lambda x: x["exit_score"], reverse=True)
    top = filtered[:top_n]

    return {
        "ok":         True,
        "source":     source,
        "today":      today.isoformat(),
        "n_total":    len(candidates),
        "n_flagged":  len(filtered),
        "candidates": top,
        "thresholds": {
            "theta_decay_pct":  _THETA_DECAY_THRESHOLD,
            "loss_limit_pct":   _LOSS_LIMIT_THRESHOLD,
            "time_stop_dte":    _TIME_STOP_DTE,
        },
    }











