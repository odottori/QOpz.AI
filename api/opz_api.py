from __future__ import annotations

import asyncio
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
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, time as time_cls, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

import logging

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

logger = logging.getLogger("opz_api")

from execution.paper_metrics import (
    compute_paper_summary,
    record_equity_snapshot,
    record_trade,
)
from execution.storage import _connect, _prov, init_execution_schema
from execution.wheel_storage import (
    init_wheel_schema,
    save_wheel_position,
    load_wheel_position,
    list_wheel_positions,
)
from execution.ibkr_settings_profile import extract_ibkr_universe_context
from execution.universe import (
    build_universe_compare,
    fetch_latest_universe_batch,
    run_universe_scan,
    run_universe_scan_from_ibkr_settings,
    UniverseDataUnavailableError,
)

# ─────────────────────────────────────────────────────────────────────────────
# Response TypedDicts — ROC6-14 endpoints
# Forniscono type-checking statico (mypy/pyright) senza overhead a runtime.
# ─────────────────────────────────────────────────────────────────────────────

class _Signal(TypedDict):
    name: str
    status: str   # "OK" | "WARN" | "ALERT" | "DISABLED"
    detail: str

class HistoryReadinessOut(TypedDict):
    profile: str
    window_days: int
    target_days: int
    days_observed: int
    days_remaining: int
    target_events: int
    events_observed: int
    events_remaining: int
    event_breakdown: Dict[str, int]
    quality_completeness: float
    quality_target: float
    quality_gap: float
    compliance_violations_window: int
    pace_events_per_day: float
    eta_days: Optional[int]
    eta_date_utc: Optional[str]
    blockers: List[str]
    ready: bool
    score_pct: float

class IbkrStatusOut(TypedDict):
    ok: bool; connected: bool; host: str; port: Optional[int]
    client_id: Optional[int]; source_system: str
    connected_at: Optional[str]; ports_probed: List[int]; message: str

class IbkrAccountPositionOut(TypedDict):
    symbol: str; sec_type: str; expiry: Optional[str]
    strike: Optional[float]; right: Optional[str]
    quantity: float; avg_cost: float; market_price: float
    market_value: float; unrealized_pnl: float; realized_pnl: float

class IbkrAccountOut(TypedDict):
    ok: bool; connected: bool; source_system: str
    account_id: Optional[str]; net_liquidation: Optional[float]
    realized_pnl: Optional[float]; unrealized_pnl: Optional[float]
    buying_power: Optional[float]; positions: List[IbkrAccountPositionOut]
    message: str

class RegimeCurrentOut(TypedDict):
    ok: bool; regime: str; n_recent: int
    regime_counts: Dict[str, int]; regime_pct: Dict[str, float]
    last_scan_ts: Optional[str]; source: str

class SystemStatusOut(TypedDict):
    ok: bool; timestamp_utc: str; api_online: bool
    kill_switch_active: bool; data_mode: str; kelly_enabled: bool
    ibkr_connected: bool; ibkr_port: Optional[int]
    ibkr_source_system: str; ibkr_connected_at: Optional[str]
    execution_config_ready: bool; n_closed_trades: int
    regime: str; signals: List[_Signal]
    history_readiness: HistoryReadinessOut

class EquityPointOut(TypedDict):
    date: str; equity: float

class EquityHistoryOut(TypedDict):
    ok: bool; profile: str; n_points: int
    latest_equity: Optional[float]; initial_equity: Optional[float]
    points: List[EquityPointOut]

class ExitCandidateOut(TypedDict):
    symbol: str; expiry: Optional[str]; strike: Optional[float]
    right: Optional[str]; quantity: float; avg_cost: float
    market_price: Optional[float]; unrealized_pnl: Optional[float]
    exit_score: int; exit_reasons: List[str]; source: str

class _ExitThresholds(TypedDict):
    theta_decay_pct: float; loss_limit_pct: float; time_stop_dte: int

class ExitCandidatesOut(TypedDict):
    ok: bool; source: str; today: str
    n_total: int; n_flagged: int
    candidates: List[ExitCandidateOut]; thresholds: _ExitThresholds


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


# ─────────────────────────────────────────────────────────────────────────────
# Session scheduler — asyncio-based, no external deps
# ─────────────────────────────────────────────────────────────────────────────

_SESSION_STATE: dict[str, Any] = {
    "last_morning":  None,   # ISO timestamp ultima morning session
    "last_eod":      None,   # ISO timestamp ultima eod session
    "next_morning":  None,   # ISO timestamp prossima morning session
    "next_eod":      None,   # ISO timestamp prossima eod session
    "last_result":   None,   # dict risultato ultima sessione eseguita
    "running":       False,  # True durante esecuzione
    "enabled":       False,  # True se scheduler attivo
}
_SESSION_TASK: Optional[asyncio.Task] = None  # type: ignore[type-arg]


def _load_sessions_config() -> dict[str, Any]:
    """
    Legge [sessions] dal file di config attivo (paper > dev).
    Restituisce dict con valori di default se sezione assente.
    """
    defaults: dict[str, Any] = {
        "enabled": False,
        "morning_time": "09:00",
        "eod_time": "16:30",
        "timezone": "America/New_York",
        "duration_max_min": 10,
        "skip_weekends": True,
        "skip_holidays": True,
        "profile": "paper",
        "api_base": "http://localhost:8765",
    }
    for profile in ("paper", "dev"):
        cfg_path = ROOT / "config" / f"{profile}.toml"
        if cfg_path.exists():
            try:
                import tomllib
                with open(cfg_path, "rb") as f:
                    data = tomllib.load(f)
                sess = data.get("sessions", {})
                return {**defaults, **sess}
            except Exception as exc:
                logger.warning("SESSION_CFG_WARN %s: %s", cfg_path, exc)
    return defaults


def _parse_session_time(time_str: str, tz_name: str) -> "time_cls":
    """Converte '09:00' → time object."""
    h, m = (int(x) for x in time_str.split(":"))
    return time_cls(h, m, tzinfo=None)


def _next_session_dt(
    now: datetime,
    morning_time: "time_cls",
    eod_time: "time_cls",
    tz_name: str,
) -> tuple[datetime, str]:
    """Delega a scripts.session_runner._next_session_dt (unica implementazione)."""
    from scripts.session_runner import _next_session_dt as _sr_next
    return _sr_next(now, morning_time, eod_time, tz_name)


async def _run_session_subprocess(session_type: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Esegue session_runner.py come subprocess asyncio."""
    script = ROOT / "scripts" / "session_runner.py"
    cmd = [
        sys.executable, str(script),
        "--type", session_type,
        "--profile", cfg.get("profile", "paper"),
        "--api-base", cfg.get("api_base", "http://localhost:8765"),
        "--format", "json",
    ]
    timeout_sec = int(cfg.get("duration_max_min", 10)) * 60
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(ROOT),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        raw = (stdout or b"").decode(errors="replace").strip()
        try:
            result = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            result = {"ok": False, "raw": raw[:500]}
        result["returncode"] = proc.returncode
        result["stderr"] = (stderr or b"").decode(errors="replace")[-500:]
        return result
    except asyncio.TimeoutError:
        return {"ok": False, "reason": f"timeout ({timeout_sec}s)", "type": session_type}
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "type": session_type}


async def _scheduler_loop(cfg: dict[str, Any]) -> None:
    """Loop infinito che dorme fino alla prossima sessione e la esegue."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(cfg.get("timezone", "America/New_York"))
    morning_t = _parse_session_time(cfg.get("morning_time", "09:00"), cfg.get("timezone", "America/New_York"))
    eod_t     = _parse_session_time(cfg.get("eod_time", "16:30"),    cfg.get("timezone", "America/New_York"))

    logger.info("SESSION_SCHEDULER started | morning=%s eod=%s tz=%s",
                cfg.get("morning_time"), cfg.get("eod_time"), cfg.get("timezone"))

    while True:
        now = datetime.now(timezone.utc)
        next_dt, session_type = _next_session_dt(now, morning_t, eod_t, cfg.get("timezone", "America/New_York"))

        # Aggiorna stato
        _SESSION_STATE[f"next_{session_type}"] = next_dt.isoformat()
        sleep_sec = max(1.0, (next_dt.astimezone(timezone.utc) - now).total_seconds())
        logger.info("SESSION_SCHEDULER sleeping %.0fs until %s (%s)",
                    sleep_sec, next_dt.isoformat(), session_type)

        try:
            await asyncio.sleep(sleep_sec)
        except asyncio.CancelledError:
            logger.info("SESSION_SCHEDULER cancelled")
            return

        # Esegui sessione
        _SESSION_STATE["running"] = True
        logger.info("SESSION_SCHEDULER launching %s session", session_type)
        try:
            result = await _run_session_subprocess(session_type, cfg)
            _SESSION_STATE[f"last_{session_type}"] = datetime.now(timezone.utc).isoformat()
            _SESSION_STATE["last_result"] = result
            ok_str = "OK" if result.get("ok") else "WARN"
            logger.info("SESSION_%s %s errors=%s", session_type.upper(), ok_str,
                        len(result.get("errors", [])))
        except Exception as exc:
            logger.exception("SESSION_%s FAILED: %s", session_type.upper(), exc)
            _SESSION_STATE["last_result"] = {"ok": False, "reason": str(exc)}
        finally:
            _SESSION_STATE["running"] = False


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    global _SESSION_TASK
    try:
        init_execution_schema()
        init_wheel_schema()
    except Exception as exc:
        logger.warning("STARTUP_STORAGE_WARN %s", exc)

    # Avvia scheduler se abilitato in config
    cfg = _load_sessions_config()
    _SESSION_STATE["enabled"] = bool(cfg.get("enabled", False))
    if _SESSION_STATE["enabled"]:
        _SESSION_TASK = asyncio.create_task(_scheduler_loop(cfg))
        logger.info("SESSION_SCHEDULER task created (morning=%s, eod=%s)",
                    cfg.get("morning_time"), cfg.get("eod_time"))
    else:
        logger.info("SESSION_SCHEDULER disabled (enabled=false in config)")

    try:
        yield
    finally:
        if _SESSION_TASK and not _SESSION_TASK.done():
            _SESSION_TASK.cancel()
            try:
                await _SESSION_TASK
            except asyncio.CancelledError:
                pass
        logger.info("SESSION_SCHEDULER stopped")


app = FastAPI(title="OPZ Operator API", version="0.1.0", lifespan=_app_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8173", "http://127.0.0.1:8173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# ── Auth ──────────────────────────────────────────────────────────────────────
# Gestita da nginx (basic auth). FastAPI è interno alla rete Docker.
# DESIGN CHOICE: nessun auth middleware in FastAPI per scelta architetturale —
# l'assunzione è che FastAPI non sia mai esposto direttamente senza nginx davanti.
# Se si vuole esporre FastAPI standalone, aggiungere HTTPBasic o API-key middleware.


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
    if path:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = ROOT / p
    else:
        p = TUTORIAL_TEXT2SPEECH_PATH
        if not p.exists():
            # fallback: guida_completa è il documento operativo principale
            p = ROOT / "docs" / "guide" / "guida_completa.md"
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
    # Single quotes doubled: PowerShell string escape convention.
    # Prevents injection via text like: hello'; Invoke-Expression 'malicious'
    safe_text_ps = (
        (text or "")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("'", "''")   # PS escape: '' = literal single quote inside '...'
        .strip()
    )
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
        duration_ms = int((time.time() - started) * 1000)
        return {
            "ok": False,
            "model": model,
            "prompt": txt,
            "response": "",
            "stdout": "",
            "stderr": "ollama non trovato nel PATH",
            "returncode": 127,
            "duration_ms": duration_ms,
        }
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
        try:
            out = run_universe_scan(profile=profile, symbols=["SPY", "QQQ", "IWM"], regime="NORMAL", top_n=3, source="manual")
        except Exception as _exc2:  # manual scan also failed (e.g. UniverseDataUnavailableError in test env)
            logger.debug("Manual scan fallback also failed: %s", _exc2)
            return "SPY", "BULL_PUT", 0.62

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


_CONSOLE_HTML = Path(__file__).parent / "console_operatore.html"


@app.get("/console", response_class=FileResponse)
def console():
    if not _CONSOLE_HTML.exists():
        raise HTTPException(status_code=404, detail="console not found")
    return FileResponse(_CONSOLE_HTML, media_type="text/html")


_GUIDE_BASE = os.environ.get("GUIDE_URL", "http://qopz-guide")


_GUIDE_LOCAL_FALLBACK = ROOT / "docs" / "guide" / "guida_completa.md"


@app.get("/guide/{path:path}")
@app.get("/guide")
async def guide_proxy(request: Request, path: str = ""):
    target = f"{_GUIDE_BASE}/{path}" if path else f"{_GUIDE_BASE}/"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(target)
        return Response(content=r.content, status_code=r.status_code,
                        media_type=r.headers.get("content-type", "text/html"))
    except httpx.ConnectError:
        # Fallback locale: serve guida_completa.md come testo
        if _GUIDE_LOCAL_FALLBACK.exists():
            return Response(
                content=_GUIDE_LOCAL_FALLBACK.read_text(encoding="utf-8"),
                media_type="text/plain; charset=utf-8",
            )
        raise HTTPException(status_code=503, detail="guide service unavailable and local fallback missing")


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
def opz_paper_equity_history(profile: str = "paper", limit: int = 60) -> EquityHistoryOut:
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
    # Kill switch check — must be the first gate (invariante CLAUDE.md)
    if (ROOT / "ops" / "kill_switch.trigger").exists():
        raise HTTPException(
            status_code=503,
            detail={"stage": "execution_confirm", "reason": "KILL SWITCH ATTIVO — esecuzione bloccata"},
        )

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


class KillSwitchRequest(BaseModel):
    action: str = Field(..., description="'activate' oppure 'deactivate'")


class ObserverSwitchRequest(BaseModel):
    action: str = Field(..., description="'on' oppure 'off' (alias: yes/no, activate/deactivate)")
    notify_telegram: bool = Field(default=True, description="Invia conferma su Telegram")
    telegram_chat_id: Optional[str] = Field(default=None, description="Override chat id telegram")
    source: str = Field(default="operator_ui")


class IbwrServiceRequest(BaseModel):
    action: str = Field(..., description="'on', 'off', 'status' (alias: start/stop)")
    notify_telegram: bool = Field(default=False, description="Invia conferma su Telegram")
    telegram_chat_id: Optional[str] = Field(default=None, description="Override chat id telegram")
    source: str = Field(default="operator_ui")


def _load_telegram_cfg() -> dict:
    cfg_path = ROOT / "config" / "telegram.toml"
    if not cfg_path.exists():
        return {}
    try:
        import tomllib
        with open(cfg_path, "rb") as f:
            data = tomllib.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _telegram_target(chat_id_override: Optional[str] = None) -> tuple[str, str]:
    cfg = _load_telegram_cfg()
    tg = cfg.get("telegram", {}) if isinstance(cfg.get("telegram"), dict) else {}
    token = str(tg.get("bot_token") or os.environ.get("TG_BOT_TOKEN", "")).strip()
    chat_id = str(chat_id_override or tg.get("chat_id") or os.environ.get("TG_CHAT_ID", "")).strip()
    return token, chat_id


def _send_telegram_text(text: str, chat_id_override: Optional[str] = None) -> tuple[bool, Optional[str]]:
    token, chat_id = _telegram_target(chat_id_override)
    if not token or not chat_id:
        return False, "telegram target missing (bot_token/chat_id)"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = httpx.post(url, data={"chat_id": chat_id, "text": text}, timeout=10.0)
    except Exception as exc:
        return False, str(exc)

    if resp.status_code >= 400:
        return False, f"http {resp.status_code}: {resp.text[:200]}"

    try:
        payload = resp.json()
    except ValueError:
        return True, None
    if isinstance(payload, dict) and payload.get("ok") is False:
        return False, str(payload.get("description") or "telegram api error")
    return True, None


def _normalize_observer_action(raw: str) -> str:
    action = str(raw or "").strip().lower()
    on_aliases = {"on", "yes", "enable", "enabled", "start", "deactivate", "1"}
    off_aliases = {"off", "no", "disable", "disabled", "stop", "activate", "0"}
    if action in on_aliases:
        return "on"
    if action in off_aliases:
        return "off"
    raise HTTPException(status_code=400, detail="action must be on/off (aliases: yes/no, activate/deactivate)")


def _normalize_ibwr_action(raw: str) -> str:
    action = str(raw or "").strip().lower()
    on_aliases = {"on", "start", "enable", "enabled", "up", "1"}
    off_aliases = {"off", "stop", "disable", "disabled", "down", "0"}
    status_aliases = {"status", "state", "check", "info"}
    if action in on_aliases:
        return "on"
    if action in off_aliases:
        return "off"
    if action in status_aliases:
        return "status"
    raise HTTPException(status_code=400, detail="action must be on/off/status (aliases: start/stop/state)")


def _control_api_json(
    path: str,
    *,
    method: str = "GET",
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    base = str(os.environ.get("CONTROL_API_BASE", "http://control-plane:8770")).strip().rstrip("/")
    token = str(os.environ.get("CONTROL_API_TOKEN", "")).strip()
    headers: dict[str, str] = {}
    if token:
        headers["X-Control-Token"] = token
    url = f"{base}{path}"
    try:
        with httpx.Client(timeout=15.0) as client:
            if method.upper() == "POST":
                resp = client.post(url, json=(payload or {}), headers=headers)
            else:
                resp = client.get(url, headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"control-plane unreachable: {type(exc).__name__}: {exc}") from exc

    if resp.status_code >= 400:
        body = (resp.text or "").strip()
        detail = f"control-plane {path} failed ({resp.status_code})"
        if body:
            detail += f": {body[:240]}"
        raise HTTPException(status_code=502, detail=detail)
    data = resp.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail=f"invalid control-plane payload for {path}")
    return data


def _ibkr_connected_for_observer() -> tuple[bool, str]:
    try:
        from execution.ibkr_connection import get_manager
        info = get_manager().connection_info()
        connected = bool(info.get("connected"))
        detail = f"ibkr={'CONNECTED' if connected else 'DISCONNECTED'}"
        return connected, detail
    except Exception as exc:
        return False, f"ibkr=DISCONNECTED manager_error={type(exc).__name__}"


@app.post("/opz/execution/kill_switch")
def execution_kill_switch(req: KillSwitchRequest) -> Dict[str, Any]:
    """Attiva o disattiva il kill switch operativo.

    Activate  → crea ops/kill_switch.trigger (blocca execution_confirm).
    Deactivate → rimuove ops/kill_switch.trigger (sblocca esecuzione).
    """
    if req.action not in {"activate", "deactivate"}:
        raise HTTPException(status_code=400, detail="action must be 'activate' or 'deactivate'")

    ks_path = ROOT / "ops" / "kill_switch.trigger"
    ks_path.parent.mkdir(parents=True, exist_ok=True)
    ts_now = datetime.now(timezone.utc).isoformat()

    if req.action == "activate":
        ks_path.write_text(
            json.dumps({"activated_at": ts_now, "source": "operator_ui"}, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.warning("KILL SWITCH ATTIVATO via API — %s", ts_now)
        return {"ok": True, "kill_switch_active": True, "action": "activate", "ts_utc": ts_now}
    else:
        removed = ks_path.exists()
        if removed:
            ks_path.unlink()
        logger.warning("Kill switch disattivato via API — %s", ts_now)
        return {"ok": True, "kill_switch_active": False, "action": "deactivate", "ts_utc": ts_now, "was_active": removed}


@app.post("/opz/execution/observer")
def execution_observer_switch(req: ObserverSwitchRequest) -> Dict[str, Any]:
    """
    OBSERVER ON/OFF command surface with Telegram acknowledgement.

    - OFF -> forza kill switch attivo (trading bloccato)
    - ON  -> consente sblocco solo se IBKR connesso, altrimenti resta OFF
    """
    action = _normalize_observer_action(req.action)
    ks_path = ROOT / "ops" / "kill_switch.trigger"
    ks_path.parent.mkdir(parents=True, exist_ok=True)
    ts_now = datetime.now(timezone.utc).isoformat()
    ibkr_connected, ibkr_detail = _ibkr_connected_for_observer()

    result_ok = True
    reason = "OK"
    applied_action = "noop"
    observer_state = "OFF"

    if action == "off":
        ks_path.write_text(
            json.dumps({"activated_at": ts_now, "source": req.source or "observer_api", "observer": "OFF"}, ensure_ascii=False),
            encoding="utf-8",
        )
        applied_action = "activate"
        observer_state = "OFF"
        reason = "MANUAL_OFF"
    else:
        if not ibkr_connected:
            if not ks_path.exists():
                ks_path.write_text(
                    json.dumps({"activated_at": ts_now, "source": req.source or "observer_api", "observer": "OFF"}, ensure_ascii=False),
                    encoding="utf-8",
                )
            applied_action = "blocked"
            observer_state = "OFF"
            reason = "IBKR_DISCONNECTED"
            result_ok = False
        else:
            if ks_path.exists():
                ks_path.unlink()
            applied_action = "deactivate"
            observer_state = "ON"
            reason = "READY"

    kill_switch_active = ks_path.exists()
    if observer_state == "ON":
        msg = f"OBSERVER ON | kill_switch=OFF | {ibkr_detail} | ts={ts_now}"
    else:
        msg = f"OBSERVER OFF | kill_switch=ON | reason={reason} | {ibkr_detail} | ts={ts_now}"

    telegram_notified = False
    telegram_error: Optional[str] = None
    if req.notify_telegram:
        telegram_notified, telegram_error = _send_telegram_text(msg, req.telegram_chat_id)

    logger.warning("OBSERVER_SWITCH action=%s applied=%s state=%s reason=%s", action, applied_action, observer_state, reason)
    return {
        "ok": result_ok,
        "requested_action": action,
        "applied_action": applied_action,
        "observer_state": observer_state,
        "kill_switch_active": kill_switch_active,
        "ibkr_connected": ibkr_connected,
        "reason": reason,
        "message": msg,
        "ts_utc": ts_now,
        "telegram_notified": telegram_notified,
        "telegram_error": telegram_error,
    }


@app.post("/opz/ibwr/service")
def ibwr_service_switch(req: IbwrServiceRequest) -> Dict[str, Any]:
    action = _normalize_ibwr_action(req.action)
    result = _control_api_json(
        "/control/ibwr",
        method="POST",
        payload={"action": action, "source": req.source or "operator_ui"},
    )

    ks_path = ROOT / "ops" / "kill_switch.trigger"
    ks_path.parent.mkdir(parents=True, exist_ok=True)
    ks_forced = False
    if action == "off":
        ts_now = datetime.now(timezone.utc).isoformat()
        ks_path.write_text(
            json.dumps({"activated_at": ts_now, "source": req.source or "ibwr_service", "ibwr": "OFF"}, ensure_ascii=False),
            encoding="utf-8",
        )
        ks_forced = True

    service_state = str(result.get("service_state", "OFF"))
    applied_action = str(result.get("applied_action", "status")).upper()
    reason = str(result.get("reason", "UNKNOWN"))
    msg = (
        f"IBWR {action.upper()} | state={service_state} | reason={reason} | "
        f"applied={applied_action} | ts={result.get('ts_utc')}"
    )

    telegram_notified = False
    telegram_error: Optional[str] = None
    if req.notify_telegram:
        telegram_notified, telegram_error = _send_telegram_text(msg, req.telegram_chat_id)

    out = dict(result)
    out["message"] = msg
    out["kill_switch_active"] = ks_path.exists()
    out["kill_switch_forced"] = ks_forced
    out["telegram_notified"] = telegram_notified
    out["telegram_error"] = telegram_error
    return out


@app.get("/opz/control/status")
def opz_control_status() -> Dict[str, Any]:
    ts_now = datetime.now(timezone.utc).isoformat()
    system = opz_system_status()

    control: dict[str, Any] = {}
    control_error: Optional[str] = None
    try:
        control = _control_api_json("/control/status", method="GET")
    except HTTPException as exc:
        control_error = str(exc.detail)

    observer_state = "OFF" if bool(system.get("kill_switch_active")) else "ON"
    ibwr = control.get("ibwr") if isinstance(control.get("ibwr"), dict) else {}
    services = control.get("services") if isinstance(control.get("services"), dict) else {}

    return {
        "ok": True,
        "timestamp_utc": ts_now,
        "observer": {
            "state": observer_state,
            "kill_switch_active": bool(system.get("kill_switch_active")),
            "reason": "KILL_SWITCH_ACTIVE" if bool(system.get("kill_switch_active")) else "READY",
        },
        "ibwr": ibwr,
        "ibkr": {
            "connected": bool(system.get("ibkr_connected")),
            "port": system.get("ibkr_port"),
            "source_system": system.get("ibkr_source_system"),
            "connected_at": system.get("ibkr_connected_at"),
        },
        "vm": {
            "services": services,
            "control_plane_ok": bool(control.get("ok")) if isinstance(control, dict) and control else False,
            "control_plane_error": control_error,
        },
        "regime": system.get("regime"),
        "data_mode": system.get("data_mode"),
        "history_readiness": system.get("history_readiness"),
    }


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
def opz_ibkr_status(try_connect: bool = False) -> IbkrStatusOut:
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
# DB helper — context manager per connessioni read-only DuckDB
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def _db_connect_ro():
    """
    Context manager per connessioni DuckDB read-only.

    Uso:
        with _db_connect_ro() as con:
            rows = con.execute("SELECT ...").fetchall()

    Nota: apre/chiude una connessione per ogni request — accettabile per
    traffico basso (dev/paper). Per produzione ad alto traffico sostituire
    con un connection pool (duckdb >= 1.1 supporta ConnectionPool).
    Solleva FileNotFoundError se il DB non esiste ancora.
    """
    import duckdb
    import execution.storage as _st
    db_path = str(_st.EXEC_DB_PATH)
    if not Path(db_path).exists():
        raise FileNotFoundError(f"DB non trovato: {db_path}")
    # Use the same connection configuration used by execution.storage._connect().
    # Mixing read_only=True and default connections on the same file can trigger:
    # "Can't open a connection to same database file with a different configuration".
    con = duckdb.connect(db_path)
    try:
        yield con
    finally:
        con.close()


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
def opz_ibkr_account() -> IbkrAccountOut:
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
        try:
            mgr.try_connect(timeout=1.5)
        except (TimeoutError, OSError, RuntimeError) as exc:
            logger.info("IBKR quick reconnect attempt failed: %s", exc)

    if not mgr.is_connected:
        return _empty_account_response(False, "Non connesso a TWS/Gateway — chiama prima /opz/ibkr/status?try_connect=true")

    try:
        ib = mgr._ib
        if ib is None or not ib.isConnected():
            raise RuntimeError("IB instance not available")

        timeout_raw = os.environ.get("IBKR_ACCOUNT_TIMEOUT_SEC", "5")
        try:
            account_timeout_sec = max(2.0, float(timeout_raw))
        except (TypeError, ValueError):
            account_timeout_sec = 5.0
        prev_timeout = getattr(ib, "RequestTimeout", None)
        ib.RequestTimeout = account_timeout_sec

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
    finally:
        try:
            if "ib" in locals() and ib is not None and "prev_timeout" in locals():
                ib.RequestTimeout = prev_timeout
        except (AttributeError, RuntimeError, TypeError) as exc:
            logger.debug("IBKR account timeout restore skipped: %s", exc)


@app.get("/opz/regime/current")
def opz_regime_current(window: int = 20) -> RegimeCurrentOut:
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
        with _db_connect_ro() as con:
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
    except Exception as _exc:
        logger.debug("opz_regime_current: DB unavailable — %s", _exc)

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


def _env_int(name: str, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(value, high))


def _env_float(name: str, default: float, low: float, high: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(value, high))


def _table_exists(con: Any, table_name: str) -> bool:
    try:
        row = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
            (table_name,),
        ).fetchone()
        return bool(row and int(row[0]) > 0)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        # In test mocks information_schema may be unavailable: assume table exists.
        return True


def _to_day_key(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    txt = str(value).strip()
    if len(txt) < 10:
        return None
    return txt[:10]


def _build_history_readiness(profile: str = "paper") -> HistoryReadinessOut:
    window_days = _env_int("OPZ_HISTORY_READINESS_WINDOW_DAYS", 10, 3, 30)
    target_days = _env_int("OPZ_HISTORY_READINESS_TARGET_DAYS", 10, 3, 90)
    target_events = _env_int("OPZ_HISTORY_READINESS_TARGET_EVENTS", 40, 1, 10000)
    quality_target = _env_float("OPZ_HISTORY_READINESS_QUALITY_TARGET", 0.95, 0.50, 1.00)

    d0 = datetime.now(timezone.utc).date()
    d1 = d0 - timedelta(days=window_days - 1)
    d1_iso = d1.isoformat()
    d0_iso = d0.isoformat()

    days_seen: set[str] = set()
    snapshot_events = 0
    trade_events = 0
    decision_events = 0
    compliance_events_window = 0
    trade_violation_sum = 0
    quality_completeness = 0.0

    required_missing = {
        "entry_ts_utc": 0,
        "symbol_strategy_strikes": 0,
        "regime_at_entry": 0,
        "score_at_entry": 0,
        "kelly_fraction": 0,
        "pnl_realized": 0,
        "slippage_actual": 0,
        "exit_reason": 0,
        "note_operational": 0,
    }
    missing_cells = 0
    trade_rows_in_window = 0

    try:
        with _db_connect_ro() as con:
            if _table_exists(con, "paper_equity_snapshots"):
                row = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM paper_equity_snapshots
                    WHERE profile = ? AND asof_date >= ? AND asof_date <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchone()
                snapshot_events = int(row[0]) if row and row[0] is not None else 0
                rows = con.execute(
                    """
                    SELECT DISTINCT asof_date
                    FROM paper_equity_snapshots
                    WHERE profile = ? AND asof_date >= ? AND asof_date <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchall()
                for r in rows:
                    day_key = _to_day_key(r[0] if r else None)
                    if day_key:
                        days_seen.add(day_key)

            if _table_exists(con, "paper_trades"):
                row = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM paper_trades
                    WHERE profile = ? AND created_at IS NOT NULL
                      AND CAST(created_at AS DATE) >= ? AND CAST(created_at AS DATE) <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchone()
                trade_events = int(row[0]) if row and row[0] is not None else 0
                rows = con.execute(
                    """
                    SELECT DISTINCT CAST(created_at AS DATE)
                    FROM paper_trades
                    WHERE profile = ? AND created_at IS NOT NULL
                      AND CAST(created_at AS DATE) >= ? AND CAST(created_at AS DATE) <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchall()
                for r in rows:
                    day_key = _to_day_key(r[0] if r else None)
                    if day_key:
                        days_seen.add(day_key)

                quality_rows = con.execute(
                    """
                    SELECT
                      entry_ts_utc, symbol, strategy, strikes_json, regime_at_entry,
                      score_at_entry, kelly_fraction, pnl, slippage_ticks, exit_reason,
                      note, violations
                    FROM paper_trades
                    WHERE profile = ? AND created_at IS NOT NULL
                      AND CAST(created_at AS DATE) >= ? AND CAST(created_at AS DATE) <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchall()
                trade_rows_in_window = len(quality_rows)
                for row in quality_rows:
                    (
                        entry_ts,
                        symbol,
                        strategy,
                        strikes_json,
                        regime_at_entry,
                        score_at_entry,
                        kelly_fraction,
                        pnl,
                        slippage_ticks,
                        exit_reason,
                        note,
                        violations,
                    ) = row

                    pnl_ok = False
                    if pnl is not None:
                        try:
                            _ = float(pnl)
                            pnl_ok = True
                        except (TypeError, ValueError):
                            pnl_ok = False
                    if not pnl_ok:
                        required_missing["pnl_realized"] += 1

                    slippage_ok = False
                    if slippage_ticks is not None:
                        try:
                            _ = float(slippage_ticks)
                            slippage_ok = True
                        except (TypeError, ValueError):
                            slippage_ok = False
                    if not slippage_ok:
                        required_missing["slippage_actual"] += 1

                    if not _is_present_text(entry_ts):
                        required_missing["entry_ts_utc"] += 1

                    has_symbol = _is_present_text(symbol)
                    has_strategy = _is_present_text(strategy)
                    has_strikes = _is_present_text(strikes_json)
                    if not (has_symbol and has_strategy and has_strikes):
                        required_missing["symbol_strategy_strikes"] += 1

                    if not _is_present_text(regime_at_entry):
                        required_missing["regime_at_entry"] += 1
                    if score_at_entry is None:
                        required_missing["score_at_entry"] += 1
                    if kelly_fraction is None:
                        required_missing["kelly_fraction"] += 1
                    if not _is_present_text(exit_reason):
                        required_missing["exit_reason"] += 1
                    if not _is_present_text(note):
                        required_missing["note_operational"] += 1

                    try:
                        trade_violation_sum += int(violations or 0)
                    except (TypeError, ValueError):
                        pass

            if _table_exists(con, "operator_opportunity_decisions"):
                row = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM operator_opportunity_decisions
                    WHERE profile = ? AND created_at IS NOT NULL
                      AND CAST(created_at AS DATE) >= ? AND CAST(created_at AS DATE) <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchone()
                decision_events = int(row[0]) if row and row[0] is not None else 0
                rows = con.execute(
                    """
                    SELECT DISTINCT CAST(created_at AS DATE)
                    FROM operator_opportunity_decisions
                    WHERE profile = ? AND created_at IS NOT NULL
                      AND CAST(created_at AS DATE) >= ? AND CAST(created_at AS DATE) <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchall()
                for r in rows:
                    day_key = _to_day_key(r[0] if r else None)
                    if day_key:
                        days_seen.add(day_key)

            if _table_exists(con, "compliance_events"):
                row = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM compliance_events
                    WHERE profile = ? AND ts_utc IS NOT NULL
                      AND CAST(ts_utc AS DATE) >= ? AND CAST(ts_utc AS DATE) <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchone()
                compliance_events_window = int(row[0]) if row and row[0] is not None else 0
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        logger.debug("SYSTEM_STATUS_HISTORY_READINESS_FALLBACK reason=%s", exc)

    for misses in required_missing.values():
        missing_cells += misses
    fields_count = len(required_missing)
    denom = trade_rows_in_window * fields_count
    if denom > 0:
        quality_completeness = max(0.0, min(1.0, 1.0 - (missing_cells / denom)))

    days_observed = len(days_seen)
    days_remaining = max(0, target_days - days_observed)

    events_observed = trade_events + decision_events
    events_remaining = max(0, target_events - events_observed)

    pace_events_per_day = round(events_observed / days_observed, 2) if days_observed > 0 else 0.0
    quality_gap = round(max(0.0, quality_target - quality_completeness), 4)
    compliance_violations_window = max(0, compliance_events_window + trade_violation_sum)

    blockers: list[str] = []
    if days_remaining > 0:
        blockers.append(f"coverage_days {days_observed}/{target_days}")
    if events_remaining > 0:
        blockers.append(f"events {events_observed}/{target_events}")
    if quality_gap > 0:
        blockers.append(
            f"journal_quality {(quality_completeness * 100):.1f}% < {(quality_target * 100):.1f}%"
        )
    if compliance_violations_window > 0:
        blockers.append(f"compliance_violations_window={compliance_violations_window}")

    ready = len(blockers) == 0

    eta_events_days: Optional[int] = None
    if events_remaining <= 0:
        eta_events_days = 0
    elif pace_events_per_day > 0:
        eta_events_days = int(math.ceil(events_remaining / pace_events_per_day))

    if ready:
        eta_days: Optional[int] = 0
    elif events_remaining > 0 and eta_events_days is None:
        eta_days = None
    else:
        eta_days = max(days_remaining, eta_events_days or 0)

    eta_date_utc = (d0 + timedelta(days=eta_days)).isoformat() if eta_days is not None else None

    day_score = min(1.0, (days_observed / target_days) if target_days > 0 else 0.0)
    event_score = min(1.0, (events_observed / target_events) if target_events > 0 else 0.0)
    quality_score = min(1.0, (quality_completeness / quality_target) if quality_target > 0 else 0.0)
    compliance_score = 1.0 if compliance_violations_window == 0 else 0.0
    score_pct = round((0.35 * day_score + 0.35 * event_score + 0.20 * quality_score + 0.10 * compliance_score) * 100.0, 1)

    return {
        "profile": profile,
        "window_days": window_days,
        "target_days": target_days,
        "days_observed": days_observed,
        "days_remaining": days_remaining,
        "target_events": target_events,
        "events_observed": events_observed,
        "events_remaining": events_remaining,
        "event_breakdown": {
            "equity_snapshots": snapshot_events,
            "paper_trades": trade_events,
            "opportunity_decisions": decision_events,
        },
        "quality_completeness": round(quality_completeness, 4),
        "quality_target": round(quality_target, 4),
        "quality_gap": quality_gap,
        "compliance_violations_window": compliance_violations_window,
        "pace_events_per_day": pace_events_per_day,
        "eta_days": eta_days,
        "eta_date_utc": eta_date_utc,
        "blockers": blockers,
        "ready": ready,
        "score_pct": score_pct,
    }


@app.get("/opz/system/status")
def opz_system_status() -> SystemStatusOut:
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
    ks_path = ROOT / "ops" / "kill_switch.trigger"
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
    except Exception as _exc:
        logger.debug("opz_system_status: IBKR manager unavailable — %s", _exc)

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
        with _db_connect_ro() as con:
            row_n = con.execute(
                "SELECT COUNT(*) FROM paper_trades WHERE exit_ts_utc IS NOT NULL"
            ).fetchone()
            n_closed_trades = int(row_n[0]) if row_n else 0

            row_r = con.execute(
                "SELECT regime_at_entry FROM paper_trades WHERE regime_at_entry IS NOT NULL ORDER BY entry_ts_utc DESC LIMIT 1"
            ).fetchone()
            if row_r:
                regime = str(row_r[0])
    except Exception as _exc:
        logger.debug("opz_system_status: DB unavailable — %s", _exc)

    # ── Kelly gate ────────────────────────────────────────────────────────────
    kelly_enabled = (data_mode == "VENDOR_REAL_CHAIN") and (n_closed_trades >= 50)
    history_profile = os.environ.get("OPZ_HISTORY_READINESS_PROFILE", "paper").strip().lower() or "paper"
    history_readiness = _build_history_readiness(profile=history_profile)

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
        {
            "name": "history_readiness",
            "status": "OK" if history_readiness["ready"] else ("WARN" if history_readiness["score_pct"] >= 70.0 else "ALERT"),
            "detail": (
                f"{history_readiness['days_observed']}/{history_readiness['target_days']}d · "
                f"{history_readiness['events_observed']}/{history_readiness['target_events']} ev · "
                f"Q {(history_readiness['quality_completeness'] * 100):.0f}%"
            ),
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
        "history_readiness": history_readiness,
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
def opz_exit_candidates(top_n: int = 10, min_score: int = 1) -> ExitCandidatesOut:
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
            with _db_connect_ro() as con:
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


# ── Wheel positions ────────────────────────────────────────────────────────────


class WheelNewRequest(BaseModel):
    symbol: str = Field(..., description="Underlying symbol, e.g. IWM")
    profile: str = Field("dev")
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class WheelTransitionRequest(BaseModel):
    event_type: str = Field(..., description="open_csp | expire_csp | assign | open_cc | expire_cc | call_away")
    profile: str = Field("dev")
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    # fields required by each event type
    strike: Optional[float] = None
    expiry: Optional[str] = None      # YYYYMMDD
    premium: Optional[float] = None
    shares: int = 100


@app.get("/opz/tier")
def opz_tier(profile: str = "dev", regime: str = "NORMAL") -> Dict[str, Any]:
    """
    Return capital_tier, active_mode and block_visibility from config/<profile>.toml.

    `regime` param: pass current regime from the UI (NORMAL/CAUTION/SHOCK).
    `block_visibility` drives dynamic UI composition — each block specifies whether
    it is visible, interactive, which gate controls it, and why (for tooltips).

    Gate types:
      always_visible  — kill switch, regime pill, monitoring panels
      capital_gate    — capital_tier insufficient
      validation_gate — active_mode gate not yet passed (copilot warning, not hard block)
      data_gate       — Kelly: requires DATA_MODE=VENDOR_REAL_CHAIN and N≥50 closed trades
      regime_gate     — SHOCK: trading suspended, blocks become read-only
    """
    import tomllib

    config_path = ROOT / "config" / f"{profile}.toml"
    if not config_path.exists():
        config_path = ROOT / "config" / "dev.toml"

    try:
        with open(config_path, "rb") as f:
            cfg = tomllib.load(f)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        cfg = {}

    tier_cfg = cfg.get("tier", {})
    capital_tier = tier_cfg.get("capital_tier", "MICRO")
    active_mode  = tier_cfg.get("active_mode",  "MICRO")

    _TIER_ORDER = ["MICRO", "SMALL", "MEDIUM", "ADVANCED"]

    def tier_gte(a: str, b: str) -> bool:
        try:
            return _TIER_ORDER.index(a) >= _TIER_ORDER.index(b)
        except ValueError:
            return False

    # features_validated: gate superato (active_mode) — strategia operativa certificata
    features_validated = {
        "bull_put":         True,
        "iron_condor":      tier_gte(active_mode, "SMALL"),
        "wheel":            tier_gte(active_mode, "SMALL"),
        "pmcc_calendar":    tier_gte(active_mode, "MEDIUM"),
        "hedge_active":     tier_gte(active_mode, "MEDIUM"),
        "ratio_spread":     tier_gte(active_mode, "ADVANCED"),
        "delta_overlay":    tier_gte(active_mode, "ADVANCED"),
        "kelly_enabled":    tier_gte(active_mode, "SMALL"),
        "twap_vwap":        tier_gte(active_mode, "MEDIUM"),
        "multi_underlying": tier_gte(active_mode, "ADVANCED"),
    }

    # features_available: capitale sufficiente (capital_tier) — copilota avvisa, non blocca
    features_available = {
        "bull_put":         True,
        "iron_condor":      tier_gte(capital_tier, "SMALL"),
        "wheel":            tier_gte(capital_tier, "SMALL"),
        "pmcc_calendar":    tier_gte(capital_tier, "MEDIUM"),
        "hedge_active":     tier_gte(capital_tier, "MEDIUM"),
        "ratio_spread":     tier_gte(capital_tier, "ADVANCED"),
        "delta_overlay":    tier_gte(capital_tier, "ADVANCED"),
        "kelly_enabled":    tier_gte(capital_tier, "SMALL"),
        "twap_vwap":        tier_gte(capital_tier, "MEDIUM"),
        "multi_underlying": tier_gte(capital_tier, "ADVANCED"),
    }

    tier_info = {
        "MICRO":    {"capital": "€1k–2k", "strategies": ["Bull Put"], "max_positions": 2},
        "SMALL":    {"capital": "€2k–5k", "strategies": ["Bull Put", "Iron Condor", "Wheel"], "max_positions": 3},
        "MEDIUM":   {"capital": "€5k–15k", "strategies": ["Bull Put", "Iron Condor", "Wheel", "PMCC", "Calendar"], "max_positions": 5},
        "ADVANCED": {"capital": "€15k+", "strategies": ["All + Ratio Spread", "Delta Overlay"], "max_positions": 8},
    }

    next_tier_map = {"MICRO": "SMALL", "SMALL": "MEDIUM", "MEDIUM": "ADVANCED", "ADVANCED": None}

    # ── Block visibility ──────────────────────────────────────────────────────
    shock = (regime == "SHOCK")
    kill_switch_active = (ROOT / "ops" / "kill_switch.trigger").exists()

    # data_gate: Kelly requires real chain data AND enough closed trades
    data_mode = os.environ.get("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")
    n_closed = 0
    import duckdb as _duckdb
    try:
        with _db_connect_ro() as _con:
            _row = _con.execute(
                "SELECT COUNT(*) FROM paper_trades WHERE exit_ts_utc IS NOT NULL"
            ).fetchone()
            n_closed = int(_row[0]) if _row else 0
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError, _duckdb.Error) as exc:
        logger.debug("SYSTEM_STATUS_DB_COUNT_FALLBACK reason=%s", exc)
    data_gate_ok = (data_mode == "VENDOR_REAL_CHAIN") and (n_closed >= 50)

    def _blk(visible: bool, interactive: bool, gate: str, reason: Optional[str] = None) -> Dict[str, Any]:
        return {"visible": visible, "interactive": interactive, "gate": gate, "reason": reason}

    def _strategy_blk(tier_req: str, label: str) -> Dict[str, Any]:
        """Capital + validation + regime gate for a strategy block."""
        cap_ok = tier_gte(capital_tier, tier_req)
        val_ok = tier_gte(active_mode, tier_req)
        if not cap_ok:
            return _blk(False, False, "capital_gate",
                        f"{label}: richiede capitale {tier_req} (attuale: {capital_tier})")
        if shock:
            return _blk(True, False, "regime_gate", f"SHOCK: {label} sospeso")
        if not val_ok:
            # capitale OK ma gate non validato → copilot warning, pannello usabile
            return _blk(True, True, "validation_gate",
                        f"⚠ {label}: gate {tier_req} non ancora validato")
        return _blk(True, True, "validation_gate")

    trading_ok = not shock and not kill_switch_active
    trading_reason = ("SHOCK: trading sospeso" if shock
                      else "Kill switch attivo" if kill_switch_active
                      else None)

    block_visibility: Dict[str, Any] = {
        # ── ALWAYS VISIBLE — mai toccati dal gate system ──────────────────────
        "kill_switch":       _blk(True, True,  "always_visible"),
        "regime_pill":       _blk(True, False, "always_visible"),
        "risk_summary":      _blk(True, False, "always_visible"),
        "connection_status": _blk(True, False, "always_visible"),
        "equity_chart":      _blk(True, False, "always_visible"),
        "gate_status":       _blk(True, False, "always_visible"),
        "ibkr_account":      _blk(True, False, "always_visible"),
        "exit_candidates":   _blk(True, False, "always_visible"),
        "trade_log":         _blk(True, False, "always_visible"),
        "regime_matrix":     _blk(True, False, "always_visible"),
        # ── SCANNING — read-only in SHOCK ─────────────────────────────────────
        "universe_scanner":  _blk(True, not shock, "regime_gate" if shock else "always_visible",
                                  "SHOCK: scanning sospeso" if shock else None),
        "opportunity_scan":  _blk(True, not shock, "regime_gate" if shock else "always_visible",
                                  "SHOCK: scan sospeso" if shock else None),
        "pipeline_auto":     _blk(True, not shock, "regime_gate" if shock else "always_visible",
                                  "SHOCK: pipeline sospesa" if shock else None),
        # ── STRATEGY BLOCKS — capital + validation + regime ───────────────────
        "strategy_bull_put":      _strategy_blk("MICRO",    "Bull Put"),
        "strategy_iron_condor":   _strategy_blk("SMALL",    "Iron Condor"),
        "strategy_wheel":         _strategy_blk("SMALL",    "Wheel"),
        "wheel_panel":            _strategy_blk("SMALL",    "Wheel"),
        "strategy_pmcc_calendar": _strategy_blk("MEDIUM",   "PMCC/Calendar"),
        "strategy_hedge_active":  _strategy_blk("MEDIUM",   "Hedge Attivo"),
        "strategy_ratio_spread":  _strategy_blk("ADVANCED", "Ratio Spread"),
        "strategy_delta_overlay": _strategy_blk("ADVANCED", "Delta Overlay"),
        # ── ORDER FLOW — trading_ok gate ──────────────────────────────────────
        "order_preview": _blk(True, trading_ok, "regime_gate", trading_reason),
        "order_confirm": _blk(True, trading_ok, "regime_gate", trading_reason),
        # ── KELLY — data_gate only ────────────────────────────────────────────
        "kelly_sizing": _blk(
            data_gate_ok, data_gate_ok and not shock, "data_gate",
            None if data_gate_ok else (
                f"Kelly disabilitato — richiede DATA_MODE=VENDOR_REAL_CHAIN "
                f"e N≥50 trade chiusi (attuale: {data_mode}, N={n_closed})"
            )
        ),
    }

    return {
        "ok": True,
        "profile": profile,
        "capital_tier": capital_tier,
        "active_mode": active_mode,
        "regime": regime,
        "features": features_validated,           # backward compat
        "features_validated": features_validated,
        "features_available": features_available,
        "tier_detail": tier_info.get(active_mode, {}),
        "next_tier": next_tier_map.get(active_mode),
        "next_capital_tier": next_tier_map.get(capital_tier),
        "next_operational_tier": next_tier_map.get(active_mode),
        "block_visibility": block_visibility,
        "data_gate": {"ok": data_gate_ok, "data_mode": data_mode, "n_closed": n_closed},
        "kill_switch_active": kill_switch_active,
    }


# ── Briefing audio ────────────────────────────────────────────────────────────

_AUDIO_DIR = ROOT / "data" / "audio"
_BRIEFING_LATEST = _AUDIO_DIR / "briefing_latest.mp3"


def _resolve_latest_briefing_path() -> Optional[Path]:
    """Return latest briefing path with fallback to newest timestamped file."""
    if _BRIEFING_LATEST.exists():
        return _BRIEFING_LATEST
    if not _AUDIO_DIR.exists():
        return None
    files = sorted(_AUDIO_DIR.glob("briefing_2*.mp3"), reverse=True)
    return files[0] if files else None


@app.get("/opz/briefing/list")
def opz_briefing_list() -> list:
    """Lista dei briefing MP3 disponibili, ordinati per data discendente (max 20)."""
    if not _AUDIO_DIR.exists():
        return []
    files = sorted(
        [f.name for f in _AUDIO_DIR.glob("briefing_2*.mp3")],
        reverse=True,
    )
    return files[:20]


@app.get("/opz/briefing/file/{filename}")
def opz_briefing_file(filename: str):
    """Serve un briefing MP3 specifico per filename."""
    if not filename.startswith("briefing_") or not filename.endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Filename non valido")
    path = _AUDIO_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File non trovato")
    return FileResponse(path=str(path), media_type="audio/mpeg", filename=filename)


@app.get("/opz/briefing/latest")
def opz_briefing_latest():
    """Serve l'ultimo briefing audio MP3 generato."""
    latest_path = _resolve_latest_briefing_path()
    if latest_path is None:
        raise HTTPException(status_code=404, detail="Nessun briefing disponibile - esegui POST /opz/briefing/generate")
    return FileResponse(
        path=str(latest_path),
        media_type="audio/mpeg",
        filename=latest_path.name,
    )


@app.post("/opz/briefing/generate")
async def opz_briefing_generate(no_telegram: bool = False) -> Dict[str, Any]:
    """
    Avvia la generazione del briefing audio in background.
    Richiede edge-tts installato nell'ambiente Python.
    """
    script = ROOT / "scripts" / "generate_briefing.py"
    if not script.exists():
        raise HTTPException(status_code=500, detail="Script generate_briefing.py non trovato")

    cmd = [sys.executable, str(script), "--api", "http://localhost:8765"]
    if no_telegram:
        cmd.append("--no-telegram")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(ROOT),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        ok = proc.returncode == 0
        return {
            "ok": ok,
            "returncode": proc.returncode,
            "stdout": stdout.decode(errors="replace")[-2000:],
            "stderr": stderr.decode(errors="replace")[-1000:],
            "mp3_path": str(_BRIEFING_LATEST) if _BRIEFING_LATEST.exists() else None,
        }
    except asyncio.TimeoutError:
        return {"ok": False, "reason": "timeout (120s) — edge-tts potrebbe non essere installato"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/opz/briefing/text")
def opz_briefing_text() -> Dict[str, Any]:
    """Restituisce il testo del briefing senza generare audio (debug/preview)."""
    import importlib.util
    script = ROOT / "scripts" / "generate_briefing.py"
    spec = importlib.util.spec_from_file_location("generate_briefing", script)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    data = mod._fetch_data("http://localhost:8765")
    text = mod._compose_text(data)
    return {"ok": True, "text": text, "chars": len(text)}


@app.get("/opz/wheel/positions")
def opz_wheel_positions(profile: str = "dev", symbol: Optional[str] = None) -> Dict[str, Any]:
    """List active Wheel positions (excludes CLOSED). Optionally filter by symbol."""
    from strategy.wheel import WheelState
    import dataclasses

    rows = list_wheel_positions(profile=profile, symbol=symbol or None)
    positions = []
    for pid, pos in rows:
        positions.append({
            "position_id": pid,
            "symbol": pos.symbol,
            "state": pos.state.value,
            "csp_strike": pos.csp_strike,
            "csp_expiry": pos.csp_expiry,
            "csp_premium_received": pos.csp_premium_received,
            "shares": pos.shares,
            "cost_basis": pos.cost_basis,
            "cc_strike": pos.cc_strike,
            "cc_expiry": pos.cc_expiry,
            "cc_premium_received": pos.cc_premium_received,
            "total_premium_collected": pos.total_premium_collected,
            "cycle_count": pos.cycle_count,
            "unrealized_cost_basis": pos.unrealized_cost_basis_per_share(),
        })
    return {"ok": True, "profile": profile, "n": len(positions), "positions": positions}


@app.post("/opz/wheel/new")
def opz_wheel_new(req: WheelNewRequest) -> Dict[str, Any]:
    """Create a new IDLE Wheel position for tracking. Returns position_id."""
    from strategy.wheel import WheelPosition

    symbol = _clean_text(req.symbol, "symbol")
    pos = WheelPosition(symbol=symbol)
    position_id = str(uuid.uuid4())
    save_wheel_position(
        pos,
        position_id=position_id,
        profile=req.profile,
        run_id=req.run_id,
        event_type="created",
    )
    return {"ok": True, "position_id": position_id, "symbol": symbol, "state": "IDLE"}


@app.post("/opz/wheel/{position_id}/transition")
def opz_wheel_transition(position_id: str, req: WheelTransitionRequest) -> Dict[str, Any]:
    """
    Apply a state transition to a tracked Wheel position.
    Requires prior human confirmation via /opz/execution/preview + /opz/execution/confirm
    for event_types that open orders (open_csp, open_cc).
    For post-fill events (assign, expire_csp, expire_cc, call_away) confirmation is implicit.
    """
    from strategy.wheel import WheelPosition, WheelState

    pos = load_wheel_position(position_id, profile=req.profile)
    if pos is None:
        raise HTTPException(status_code=404, detail=f"position {position_id} not found for profile {req.profile}")

    prev_state = pos.state
    event = req.event_type

    try:
        if event == "open_csp":
            if req.strike is None or req.expiry is None or req.premium is None:
                raise HTTPException(status_code=400, detail="open_csp requires strike, expiry, premium")
            pos.open_csp(strike=req.strike, expiry=req.expiry, premium=req.premium, shares=req.shares)
        elif event == "expire_csp":
            pos.expire_csp()
        elif event == "assign":
            pos.assign()
        elif event == "open_cc":
            if req.strike is None or req.expiry is None or req.premium is None:
                raise HTTPException(status_code=400, detail="open_cc requires strike, expiry, premium")
            pos.open_cc(strike=req.strike, expiry=req.expiry, premium=req.premium)
        elif event == "expire_cc":
            pos.expire_cc()
        elif event == "call_away":
            pos.call_away()
        else:
            raise HTTPException(status_code=400, detail=f"unknown event_type: {event}")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    save_wheel_position(
        pos,
        position_id=position_id,
        profile=req.profile,
        run_id=req.run_id,
        prev_state=prev_state,
        event_type=event,
    )

    return {
        "ok": True,
        "position_id": position_id,
        "symbol": pos.symbol,
        "prev_state": prev_state.value,
        "new_state": pos.state.value,
        "event_type": event,
        "realized_pnl": pos.realized_pnl(),
    }













# ─────────────────────────────────────────────────────────────────────────────
# Session scheduler endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/opz/session/status")
def opz_session_status() -> Dict[str, Any]:
    """
    Stato dello scheduler di sessioni automatiche.
    Restituisce last/next morning+eod, running, enabled.
    """
    return {
        "ok": True,
        "enabled": _SESSION_STATE.get("enabled", False),
        "running": _SESSION_STATE.get("running", False),
        "last_morning": _SESSION_STATE.get("last_morning"),
        "last_eod": _SESSION_STATE.get("last_eod"),
        "next_morning": _SESSION_STATE.get("next_morning"),
        "next_eod": _SESSION_STATE.get("next_eod"),
        "last_result": _SESSION_STATE.get("last_result"),
    }


class SessionRunRequest(BaseModel):
    type: str = Field(default="morning", pattern="^(morning|eod)$")
    profile: str = Field(default="paper")
    force: bool = Field(default=False, description="Esegui anche se non è giorno di trading")


@app.post("/opz/session/run")
async def opz_session_run(req: SessionRunRequest) -> Dict[str, Any]:
    """
    Trigger manuale di una sessione morning o eod.
    Esegue in foreground e restituisce il risultato completo.
    Usabile dalla UI e dal bot Telegram.
    """
    if _SESSION_STATE.get("running"):
        raise HTTPException(status_code=409, detail="Sessione già in corso — attendi il completamento")

    cfg = _load_sessions_config()
    cfg["profile"] = req.profile

    _SESSION_STATE["running"] = True
    try:
        # Se --force non è richiesto, verifica giorno di trading
        script = ROOT / "scripts" / "session_runner.py"
        extra_args = ["--force"] if req.force else []
        cmd = [
            sys.executable, str(script),
            "--type", req.type,
            "--profile", req.profile,
            "--api-base", cfg.get("api_base", "http://localhost:8765"),
            "--format", "json",
            *extra_args,
        ]
        timeout_sec = int(cfg.get("duration_max_min", 10)) * 60
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(ROOT),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        raw = (stdout or b"").decode(errors="replace").strip()
        try:
            result = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            result = {"ok": False, "raw": raw[:500]}
        result["returncode"] = proc.returncode
        result["stderr_tail"] = (stderr or b"").decode(errors="replace")[-300:]

        # Aggiorna stato globale
        now_iso = datetime.now(timezone.utc).isoformat()
        _SESSION_STATE[f"last_{req.type}"] = now_iso
        _SESSION_STATE["last_result"] = result
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Timeout sessione {req.type} (>{cfg.get('duration_max_min', 10)} min)")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        _SESSION_STATE["running"] = False
