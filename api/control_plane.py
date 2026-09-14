from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="OPZ Control Plane", version="0.2.0")

_LOCK = threading.Lock()
_TOKEN = str(os.environ.get("CONTROL_API_TOKEN", "")).strip()
_SOCK_PATH = str(os.environ.get("DOCKER_SOCK_PATH", "/var/run/docker.sock")).strip() or "/var/run/docker.sock"
_PROJECT = str(os.environ.get("CONTROL_COMPOSE_PROJECT", "qopz")).strip() or "qopz"
_IBWR_SERVICE = str(os.environ.get("CONTROL_IBWR_SERVICE", "ibg")).strip() or "ibg"
_BACKEND = str(os.environ.get("CONTROL_BACKEND", "docker")).strip().lower() or "docker"
_EVENTS_PATH = Path(
    str(os.environ.get("CONTROL_EVENTS_PATH", "/app/data/control/ibwr_events.jsonl")).strip()
    or "/app/data/control/ibwr_events.jsonl"
)
_STATE_PATH = Path(
    str(os.environ.get("CONTROL_STATE_PATH", "/app/data/control/ibwr_state.json")).strip()
    or "/app/data/control/ibwr_state.json"
)
_LOCAL_PID_PATH = Path(
    str(os.environ.get("CONTROL_LOCAL_IBG_PID_PATH", str(_STATE_PATH.parent / "ibg_local.pid"))).strip()
    or str(_STATE_PATH.parent / "ibg_local.pid")
)
_LOCAL_CMD_RAW = str(os.environ.get("CONTROL_LOCAL_IBG_CMD", "")).strip()
_LOCAL_AUTO_LAUNCH = str(os.environ.get("CONTROL_LOCAL_IBG_AUTO_LAUNCH", "0")).strip().lower() in {"1", "true", "yes", "on"}
_LOCAL_PORTS = [4004, 4002, 7497, 7496, 4001]


class IbwrControlRequest(BaseModel):
    action: str = Field(..., description="'on', 'off', 'status'")
    source: str = Field(default="api")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_token(x_control_token: Optional[str]) -> None:
    if not _TOKEN:
        return
    if str(x_control_token or "").strip() != _TOKEN:
        raise HTTPException(status_code=401, detail="invalid control token")


def _normalize_action(raw: str) -> str:
    action = str(raw or "").strip().lower()
    if action in {"on", "start", "up", "enable", "1"}:
        return "on"
    if action in {"off", "stop", "down", "disable", "0"}:
        return "off"
    if action in {"status", "state", "check", "info"}:
        return "status"
    raise HTTPException(status_code=400, detail="action must be on/off/status")


def _docker_client() -> httpx.Client:
    sock = Path(_SOCK_PATH)
    if not sock.exists():
        raise HTTPException(status_code=503, detail=f"docker socket not available: {_SOCK_PATH}")
    transport = httpx.HTTPTransport(uds=str(sock))
    return httpx.Client(base_url="http://docker", transport=transport, timeout=15.0)


def _raise_docker(prefix: str, resp: httpx.Response) -> None:
    body = (resp.text or "").strip()
    detail = f"{prefix} failed ({resp.status_code})"
    if body:
        detail += f": {body[:240]}"
    raise HTTPException(status_code=502, detail=detail)


def _list_containers(client: httpx.Client, all_containers: bool = True) -> list[dict[str, Any]]:
    resp = client.get("/containers/json", params={"all": 1 if all_containers else 0})
    if resp.status_code >= 400:
        _raise_docker("docker list containers", resp)
    payload = resp.json()
    return payload if isinstance(payload, list) else []


def _find_compose_service(containers: list[dict[str, Any]], service: str) -> Optional[dict[str, Any]]:
    want = str(service).strip().lower()
    for item in containers:
        labels = item.get("Labels") if isinstance(item.get("Labels"), dict) else {}
        svc = str(labels.get("com.docker.compose.service") or "").strip().lower()
        proj = str(labels.get("com.docker.compose.project") or "").strip().lower()
        if svc == want and (not _PROJECT or not proj or proj == _PROJECT.lower()):
            return item
    for item in containers:
        labels = item.get("Labels") if isinstance(item.get("Labels"), dict) else {}
        svc = str(labels.get("com.docker.compose.service") or "").strip().lower()
        if svc == want:
            return item
    return None


def _inspect_container(client: httpx.Client, container_id: str) -> dict[str, Any]:
    resp = client.get(f"/containers/{container_id}/json")
    if resp.status_code >= 400:
        _raise_docker("docker inspect container", resp)
    payload = resp.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="invalid docker inspect payload")
    return payload


def _derive_service_state(inspect_payload: dict[str, Any]) -> tuple[str, str, Optional[str]]:
    state_obj = inspect_payload.get("State") if isinstance(inspect_payload.get("State"), dict) else {}
    docker_status = str(state_obj.get("Status") or "").strip().lower()
    health_obj = state_obj.get("Health") if isinstance(state_obj.get("Health"), dict) else {}
    health = str(health_obj.get("Status") or "").strip().lower() or None

    if docker_status == "running":
        if health == "healthy":
            return "ON", docker_status, health
        if health == "starting":
            return "STARTING", docker_status, health
        if health == "unhealthy":
            return "ERROR", docker_status, health
        return "ON", docker_status, health
    if docker_status in {"restarting", "created"}:
        return "STARTING", docker_status, health
    if docker_status in {"exited", "dead", "removing"}:
        return "OFF", docker_status, health
    if docker_status in {"paused"}:
        return "ERROR", docker_status, health
    return "ERROR", docker_status or "unknown", health


def _append_event(event: dict[str, Any]) -> None:
    _EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def _write_state(state: dict[str, Any]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _wait_for_state(client: httpx.Client, container_id: str, action: str, timeout_sec: int = 20) -> dict[str, Any]:
    deadline = time.time() + max(1, timeout_sec)
    last = _inspect_container(client, container_id)
    while time.time() < deadline:
        last = _inspect_container(client, container_id)
        svc_state, _, _ = _derive_service_state(last)
        if action == "on" and svc_state in {"ON", "STARTING"}:
            return last
        if action == "off" and svc_state == "OFF":
            return last
        time.sleep(1.0)
    return last


def _probe_port(host: str, port: int, timeout: float = 0.25) -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _standard_open_ports(host: str = "127.0.0.1") -> list[int]:
    return [port for port in _LOCAL_PORTS if _probe_port(host, port)]


def _local_cmd() -> list[str]:
    if not _LOCAL_CMD_RAW:
        raise HTTPException(status_code=503, detail="local ibg command not configured")
    try:
        data = json.loads(_LOCAL_CMD_RAW)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"invalid CONTROL_LOCAL_IBG_CMD: {exc}") from exc
    if not isinstance(data, list) or not data or not all(isinstance(x, str) and x.strip() for x in data):
        raise HTTPException(status_code=503, detail="CONTROL_LOCAL_IBG_CMD must be a non-empty JSON string list")
    return data


def _read_pid() -> Optional[int]:
    try:
        raw = _LOCAL_PID_PATH.read_text(encoding="utf-8").strip()
        return int(raw)
    except Exception:
        return None


def _write_pid(pid: int) -> None:
    _LOCAL_PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LOCAL_PID_PATH.write_text(str(int(pid)), encoding="utf-8")


def _clear_pid() -> None:
    try:
        _LOCAL_PID_PATH.unlink()
    except FileNotFoundError:
        pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, 0, int(pid))
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def _terminate_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(int(pid))], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(int(pid), signal.SIGTERM)
    except Exception:
        pass


def _local_service_payload(*, action: str, source: str, applied_action: str, state_before: str, state_after: str, reason: str, pid: Optional[int], open_ports: list[int]) -> dict[str, Any]:
    ts_now = _now_utc()
    out = {
        "ok": True,
        "requested_action": action,
        "applied_action": applied_action,
        "service_name": _IBWR_SERVICE,
        "service_state": state_after,
        "state_before": state_before,
        "state_after": state_after,
        "docker_status_before": None,
        "docker_status_after": None,
        "docker_health_before": None,
        "docker_health_after": None,
        "reason": reason,
        "container_id": None,
        "backend": "local_process",
        "launch_mode": "auto_launch" if _LOCAL_AUTO_LAUNCH else "attach_first",
        "pid": pid,
        "open_ports": open_ports,
        "ts_utc": ts_now,
        "source": source,
    }
    _append_event(out)
    _write_state(out)
    return out


def _ibwr_action_local(action: str, source: str) -> dict[str, Any]:
    open_before = _standard_open_ports()
    pid_before = _read_pid()
    pid_alive_before = _pid_alive(pid_before or 0)
    state_before = "ON" if open_before else ("STARTING" if pid_alive_before else "OFF")

    applied_action = "status"
    reason = "RUNNING" if state_before in {"ON", "STARTING"} else "STOPPED"

    if action == "on":
        if open_before:
            applied_action = "noop"
            reason = "ALREADY_RUNNING"
            return _local_service_payload(action=action, source=source, applied_action=applied_action, state_before=state_before, state_after="ON", reason=reason, pid=pid_before if pid_alive_before else None, open_ports=open_before)
        if pid_alive_before:
            return _local_service_payload(action=action, source=source, applied_action="wait", state_before=state_before, state_after="STARTING", reason="WAITING_FOR_LOGIN", pid=pid_before, open_ports=_standard_open_ports())
        if not _LOCAL_AUTO_LAUNCH:
            return _local_service_payload(action=action, source=source, applied_action="attach_only", state_before=state_before, state_after="OFF", reason="BROKER_NOT_LISTENING", pid=None, open_ports=[])

        cmd = _local_cmd()
        kwargs: dict[str, Any] = {
            "cwd": str(Path(cmd[0]).resolve().parent) if Path(cmd[0]).suffix.lower() in {".exe", ".bat", ".cmd"} else str(Path.cwd()),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            kwargs["shell"] = False
        proc = subprocess.Popen(cmd, **kwargs)
        _write_pid(proc.pid)
        applied_action = "start"
        deadline = time.time() + 30.0
        open_after = []
        while time.time() < deadline:
            open_after = _standard_open_ports()
            if open_after:
                break
            time.sleep(1.0)
        if open_after:
            return _local_service_payload(action=action, source=source, applied_action=applied_action, state_before=state_before, state_after="ON", reason="RUNNING", pid=proc.pid, open_ports=open_after)
        state_after = "STARTING" if _pid_alive(proc.pid) else "ERROR"
        reason = "WAITING_FOR_LOGIN" if state_after == "STARTING" else "START_FAILED"
        return _local_service_payload(action=action, source=source, applied_action=applied_action, state_before=state_before, state_after=state_after, reason=reason, pid=proc.pid if _pid_alive(proc.pid) else None, open_ports=_standard_open_ports())

    elif action == "off":
        if pid_before and pid_alive_before:
            _terminate_pid(pid_before)
        _clear_pid()
        applied_action = "stop" if state_before != "OFF" else "noop"
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if not _standard_open_ports():
                break
            time.sleep(1.0)
        open_after = _standard_open_ports()
        state_after = "OFF" if not open_after else "ERROR"
        reason = "STOPPED" if state_after == "OFF" else "STOP_FAILED"
        return _local_service_payload(action=action, source=source, applied_action=applied_action, state_before=state_before, state_after=state_after, reason=reason, pid=None, open_ports=open_after)

    open_after = _standard_open_ports()
    state_after = "ON" if open_after else ("STARTING" if _pid_alive(_read_pid() or 0) else "OFF")
    reason = "RUNNING" if state_after == "ON" else ("STARTING" if state_after == "STARTING" else "STOPPED")
    return _local_service_payload(action=action, source=source, applied_action=applied_action, state_before=state_before, state_after=state_after, reason=reason, pid=_read_pid() if _pid_alive(_read_pid() or 0) else None, open_ports=open_after)


def _ibwr_action_docker(action: str, source: str) -> dict[str, Any]:
    with _docker_client() as client:
        containers = _list_containers(client, all_containers=True)
        item = _find_compose_service(containers, _IBWR_SERVICE)
        if not item:
            raise HTTPException(status_code=404, detail=f"{_IBWR_SERVICE} container not found")

        container_id = str(item.get("Id") or "")
        if not container_id:
            raise HTTPException(status_code=502, detail="ibwr container id missing")

        before = _inspect_container(client, container_id)
        before_state, before_docker_status, before_health = _derive_service_state(before)

        applied_action = "status"
        reason = "RUNNING" if before_state in {"ON", "STARTING"} else "STOPPED"
        if action == "on":
            if before_state in {"ON", "STARTING"}:
                applied_action = "noop"
                reason = "ALREADY_RUNNING"
            else:
                resp = client.post(f"/containers/{container_id}/start")
                if resp.status_code >= 400:
                    _raise_docker("docker start ibwr", resp)
                applied_action = "start"
                reason = "START_REQUESTED"
        elif action == "off":
            if before_state == "OFF":
                applied_action = "noop"
                reason = "ALREADY_STOPPED"
            else:
                resp = client.post(f"/containers/{container_id}/stop", params={"t": 15})
                if resp.status_code >= 400:
                    _raise_docker("docker stop ibwr", resp)
                applied_action = "stop"
                reason = "STOP_REQUESTED"

        after = _wait_for_state(client, container_id, action) if action in {"on", "off"} else _inspect_container(client, container_id)
        after_state, after_docker_status, after_health = _derive_service_state(after)

        if action == "on":
            if after_state in {"ON", "STARTING"}:
                reason = "RUNNING" if after_state == "ON" else "STARTING"
            else:
                after_state = "ERROR"
                reason = "START_FAILED"
        elif action == "off":
            if after_state == "OFF":
                reason = "STOPPED"
            elif after_state in {"ON", "STARTING"}:
                after_state = "STOPPING"
                reason = "STOPPING"
            else:
                after_state = "ERROR"
                reason = "STOP_FAILED"

        ts_now = _now_utc()
        out = {
            "ok": True,
            "requested_action": action,
            "applied_action": applied_action,
            "service_name": _IBWR_SERVICE,
            "service_state": after_state,
            "state_before": before_state,
            "state_after": after_state,
            "docker_status_before": before_docker_status,
            "docker_status_after": after_docker_status,
            "docker_health_before": before_health,
            "docker_health_after": after_health,
            "reason": reason,
            "container_id": container_id[:12],
            "backend": "docker",
            "pid": None,
            "open_ports": [],
            "ts_utc": ts_now,
            "source": source,
        }
        _append_event(out)
        _write_state(out)
        return out


def _ibwr_action(action: str, source: str) -> dict[str, Any]:
    if _BACKEND == "local_process":
        return _ibwr_action_local(action, source)
    return _ibwr_action_docker(action, source)


def _services_status() -> dict[str, dict[str, Any]]:
    if _BACKEND == "local_process":
        open_ports = _standard_open_ports()
        pid = _read_pid()
        alive = _pid_alive(pid or 0)
        state = "ON" if open_ports else ("STARTING" if alive else "OFF")
        return {
            _IBWR_SERVICE: {
                "present": True,
                "state": state,
                "running": state in {"ON", "STARTING"},
                "docker_status": None,
                "health": None,
                "container_id": None,
                "backend": "local_process",
                "pid": pid if alive else None,
                "open_ports": open_ports,
            }
        }
    names = ["api", "nginx", "tg-bot", _IBWR_SERVICE]
    out: dict[str, dict[str, Any]] = {}
    with _docker_client() as client:
        containers = _list_containers(client, all_containers=True)
        for name in names:
            item = _find_compose_service(containers, name)
            if not item:
                out[name] = {
                    "present": False,
                    "state": "MISSING",
                    "running": False,
                    "docker_status": "missing",
                    "health": None,
                }
                continue

            container_id = str(item.get("Id") or "")
            ins = _inspect_container(client, container_id)
            svc_state, docker_status, health = _derive_service_state(ins)
            running = svc_state in {"ON", "STARTING"}
            out[name] = {
                "present": True,
                "state": svc_state,
                "running": running,
                "docker_status": docker_status,
                "health": health,
                "container_id": container_id[:12],
                "backend": "docker",
            }
    return out


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "control-plane", "backend": _BACKEND, "ts_utc": _now_utc()}


@app.post("/control/ibwr")
def control_ibwr(req: IbwrControlRequest, x_control_token: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _require_token(x_control_token)
    action = _normalize_action(req.action)
    with _LOCK:
        return _ibwr_action(action, source=req.source or "api")


@app.get("/control/status")
def control_status(x_control_token: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _require_token(x_control_token)
    with _LOCK:
        ibwr = _ibwr_action("status", source="status")
        services = _services_status()
    return {
        "ok": True,
        "ts_utc": _now_utc(),
        "backend": _BACKEND,
        "ibwr": ibwr,
        "services": services,
    }
