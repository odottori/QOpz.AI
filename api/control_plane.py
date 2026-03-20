from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="OPZ Control Plane", version="0.1.0")

_LOCK = threading.Lock()
_TOKEN = str(os.environ.get("CONTROL_API_TOKEN", "")).strip()
_SOCK_PATH = str(os.environ.get("DOCKER_SOCK_PATH", "/var/run/docker.sock")).strip() or "/var/run/docker.sock"
_PROJECT = str(os.environ.get("CONTROL_COMPOSE_PROJECT", "qopz")).strip() or "qopz"
_IBWR_SERVICE = str(os.environ.get("CONTROL_IBWR_SERVICE", "ibg")).strip() or "ibg"
_EVENTS_PATH = Path(
    str(os.environ.get("CONTROL_EVENTS_PATH", "/app/data/control/ibwr_events.jsonl")).strip()
    or "/app/data/control/ibwr_events.jsonl"
)
_STATE_PATH = Path(
    str(os.environ.get("CONTROL_STATE_PATH", "/app/data/control/ibwr_state.json")).strip()
    or "/app/data/control/ibwr_state.json"
)


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


def _ibwr_action(action: str, source: str) -> dict[str, Any]:
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
            "ts_utc": ts_now,
            "source": source,
        }
        _append_event(out)
        _write_state(out)
        return out


def _services_status() -> dict[str, dict[str, Any]]:
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
            }
    return out


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "control-plane", "ts_utc": _now_utc()}


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
        "ibwr": ibwr,
        "services": services,
    }
