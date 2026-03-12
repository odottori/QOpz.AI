from __future__ import annotations

import json
import math
import os
import re
import secrets
import shlex
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, time as time_cls, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from execution.paper_metrics import (
    compute_paper_summary,
    record_equity_snapshot,
    record_trade,
)
from execution.storage import _connect, init_execution_schema
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


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    try:
        init_execution_schema()
    except Exception as exc:
        print(f"STARTUP_STORAGE_WARN {exc}")
    yield


app = FastAPI(title="OPZ Operator API", version="0.1.0", lifespan=_app_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    except Exception:
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
    except Exception:
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
        except Exception:
            s = stdout.find("{")
            e = stdout.rfind("}")
            if s >= 0 and e > s:
                try:
                    parsed = json.loads(stdout[s : e + 1])
                    if isinstance(parsed, dict):
                        payload = parsed
                except Exception:
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
    except Exception:
        content = p.read_text(encoding="utf-8", errors="ignore")
    return {"path": str(p), "exists": True, "content": content}


def _read_fallback_tts_pid() -> Optional[int]:
    global _TTS_FALLBACK_PID_MEM
    if not TTS_FALLBACK_PID_PATH.exists():
        return _TTS_FALLBACK_PID_MEM
    try:
        raw = TTS_FALLBACK_PID_PATH.read_text(encoding="utf-8").strip()
        pid = int(raw)
        _TTS_FALLBACK_PID_MEM = pid if pid > 0 else None
        return _TTS_FALLBACK_PID_MEM
    except Exception:
        return _TTS_FALLBACK_PID_MEM


def _write_fallback_tts_pid(pid: int) -> None:
    global _TTS_FALLBACK_PID_MEM
    _TTS_FALLBACK_PID_MEM = int(pid)
    try:
        TTS_FALLBACK_PID_PATH.write_text(str(int(pid)), encoding="utf-8")
    except Exception:
        return


def _read_fallback_tts_state() -> str:
    global _TTS_FALLBACK_STATE_MEM
    if not TTS_FALLBACK_STATE_PATH.exists():
        return _TTS_FALLBACK_STATE_MEM
    try:
        _TTS_FALLBACK_STATE_MEM = TTS_FALLBACK_STATE_PATH.read_text(encoding="utf-8").strip().lower()
        return _TTS_FALLBACK_STATE_MEM
    except Exception:
        return _TTS_FALLBACK_STATE_MEM


def _write_fallback_tts_state(state: str) -> None:
    global _TTS_FALLBACK_STATE_MEM
    _TTS_FALLBACK_STATE_MEM = (state or "").strip().lower()
    try:
        TTS_FALLBACK_STATE_PATH.write_text(_TTS_FALLBACK_STATE_MEM, encoding="utf-8")
    except Exception:
        return


def _clear_fallback_tts_pid() -> None:
    global _TTS_FALLBACK_PID_MEM
    _TTS_FALLBACK_PID_MEM = None
    try:
        if TTS_FALLBACK_PID_PATH.exists():
            TTS_FALLBACK_PID_PATH.unlink()
    except Exception:
        return


def _clear_fallback_tts_state() -> None:
    global _TTS_FALLBACK_STATE_MEM
    _TTS_FALLBACK_STATE_MEM = ""
    try:
        if TTS_FALLBACK_STATE_PATH.exists():
            TTS_FALLBACK_STATE_PATH.unlink()
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
        raise HTTPException(status_code=400, detail=f"invalid {field_name} (expected ISO datetime)")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _read_jsonl_tail(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    for raw in reversed(lines):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except Exception:
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
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    for raw in lines:
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
        except Exception:
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


@app.post("/opz/paper/equity_snapshot")
def opz_paper_equity_snapshot(req: EquitySnapshotRequest) -> Dict[str, Any]:
    profile = _clean_text(req.profile, "profile")
    equity = _require_finite(req.equity, "equity")
    if equity <= 0:
        raise HTTPException(status_code=400, detail="invalid equity (must be > 0)")
    try:
        from datetime import date as _date

        d = _date.fromisoformat(req.asof_date)
    except Exception:
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
        note=req.note.strip(),
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
    (LOG_DIR / "operator_previews.jsonl").open("a", encoding="utf-8").write(
        json.dumps({"token": token, "preview": preview}, ensure_ascii=False) + "\n"
    )
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
    (LOG_DIR / "operator_confirms.jsonl").open("a", encoding="utf-8").write(json.dumps(event, ensure_ascii=False) + "\n")
    return {"ok": True, "event": event}


@app.post("/opz/opportunity/decision")
def opz_opportunity_decision(req: OpportunityDecisionRequest) -> Dict[str, Any]:
    profile = _clean_text(req.profile, "profile")
    symbol = _clean_text(req.symbol, "symbol").upper()
    strategy = req.strategy.strip().upper() if req.strategy else ""
    regime = req.regime.strip().upper() if req.regime else ""
    scanner_name = req.scanner_name.strip() if req.scanner_name else ""
    source = req.source.strip() if req.source else ""
    score = None if req.score is None else _require_finite(req.score, "score")
    ts = datetime.now(timezone.utc)
    decision_id = secrets.token_urlsafe(12)

    init_execution_schema()
    con = _connect()
    con.execute(
        """
        INSERT INTO operator_opportunity_decisions
        (decision_id, profile, batch_id, symbol, strategy, score, regime, scanner_name, source, decision, confidence, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            req.note.strip(),
            ts,
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
            "note": req.note.strip(),
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
    return build_universe_compare(settings_path=safe_settings_path, ocr_path=safe_ocr_path, regime=reg)

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

        return run_universe_scan(profile=profile, symbols=symbols, regime=regime, top_n=req.top_n, source="manual")
    except UniverseDataUnavailableError as exc:
        raise HTTPException(status_code=409, detail={"stage": "universe_scan", **exc.detail}) from exc









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











