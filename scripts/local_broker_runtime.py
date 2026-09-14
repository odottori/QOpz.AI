from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "logs" / "local_broker"
CP_PID_PATH = STATE_DIR / "control_plane.pid"
CONTROL_BASE = "http://127.0.0.1:8770"
CONTROL_HEALTH = f"{CONTROL_BASE}/health"
CONTROL_STATUS = f"{CONTROL_BASE}/control/status"
CONTROL_IBWR = f"{CONTROL_BASE}/control/ibwr"
STANDARD_PORTS = [4004, 4002, 7497, 7496, 4001]


def _probe_port(port: int, host: str = "127.0.0.1", timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _open_ports() -> list[int]:
    return [p for p in STANDARD_PORTS if _probe_port(p)]


def _candidate_commands() -> list[list[str]]:
    out: list[list[str]] = []
    env_cmd = str(os.environ.get("IBG_COMMAND", "")).strip()
    if env_cmd:
        out.append([env_cmd])
    env_exe = str(os.environ.get("IBG_EXE", "")).strip()
    if env_exe:
        out.append([env_exe])
    patterns = [
        Path("C:/Jts").glob("**/ibgateway.exe"),
        Path("C:/Jts").glob("**/ibgateway.bat"),
        Path("C:/Jts").glob("**/ibgateway.cmd"),
        Path("C:/Program Files").glob("**/ibgateway.exe"),
        Path("C:/Program Files").glob("**/ibgateway.bat"),
        Path("C:/Program Files (x86)").glob("**/ibgateway.exe"),
    ]
    seen: set[str] = set()
    for group in patterns:
        for path in group:
            if not path.exists():
                continue
            sp = str(path)
            if sp.lower() in seen:
                continue
            seen.add(sp.lower())
            if path.suffix.lower() in {".bat", ".cmd"}:
                out.append(["cmd.exe", "/c", sp])
            else:
                out.append([sp])
    return out


def _discover_command() -> Optional[list[str]]:
    for cmd in _candidate_commands():
        target = cmd[-1] if cmd else ""
        if target and Path(target).exists():
            return cmd
    return None


def _cp_running() -> bool:
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get(CONTROL_HEALTH)
            return r.status_code < 400
    except Exception:
        return False


def _read_pid(path: Path) -> Optional[int]:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(int(pid)), encoding='utf-8')


def _kill_pid(pid: int) -> None:
    if pid <= 0:
        return
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_http(url: str, timeout_sec: float = 15.0) -> bool:
    deadline = time.time() + max(1.0, timeout_sec)
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=2.0) as client:
                r = client.get(url)
                if r.status_code < 400:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _start_control_plane() -> dict:
    if _cp_running():
        return {"ok": True, "started": False, "reason": "already_running"}
    cmd = _discover_command()
    if not cmd:
        return {"ok": False, "reason": "ibg_command_not_found", "candidates_checked": len(_candidate_commands())}
    env = os.environ.copy()
    env.update({
        "CONTROL_BACKEND": "local_process",
        "CONTROL_LOCAL_IBG_CMD": json.dumps(cmd),
        "CONTROL_EVENTS_PATH": str(ROOT / "logs" / "control" / "ibwr_events.jsonl"),
        "CONTROL_STATE_PATH": str(ROOT / "logs" / "control" / "ibwr_state.json"),
        "CONTROL_LOCAL_IBG_PID_PATH": str(ROOT / "logs" / "control" / "ibg_local.pid"),
        "CONTROL_LOCAL_IBG_AUTO_LAUNCH": "0",
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.control_plane:app", "--host", "127.0.0.1", "--port", "8770"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS if os.name == 'nt' else 0,
    )
    _write_pid(CP_PID_PATH, proc.pid)
    healthy = _wait_http(CONTROL_HEALTH, 20.0)
    return {"ok": healthy, "started": True, "pid": proc.pid, "reason": "started" if healthy else "health_timeout", "command": cmd}


def _post_ibwr(action: str) -> dict:
    with httpx.Client(timeout=20.0) as client:
        r = client.post(CONTROL_IBWR, json={"action": action, "source": "local_broker_runtime"})
        r.raise_for_status()
        return r.json()


def cmd_up(_: argparse.Namespace) -> int:
    started = _start_control_plane()
    print(json.dumps({"control_plane": started, "ports_before": _open_ports()}, ensure_ascii=False, indent=2))
    if not started.get("ok"):
        return 10
    try:
        out = _post_ibwr("on")
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"ibwr_on_failed: {type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        return 11
    print(json.dumps({"ibwr": out, "ports_after": _open_ports()}, ensure_ascii=False, indent=2))
    return 0 if out.get("service_state") in {"ON", "STARTING"} else 12


def cmd_down(_: argparse.Namespace) -> int:
    payload: dict = {"control_plane_running": _cp_running()}
    if _cp_running():
        try:
            payload["ibwr"] = _post_ibwr("off")
        except Exception as exc:
            payload["ibwr_error"] = f"{type(exc).__name__}: {exc}"
    pid = _read_pid(CP_PID_PATH)
    if pid:
        _kill_pid(pid)
        try:
            CP_PID_PATH.unlink()
        except FileNotFoundError:
            pass
    payload["ports_after"] = _open_ports()
    payload["ok"] = not payload["ports_after"]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 13


def cmd_status(_: argparse.Namespace) -> int:
    payload = {
        "control_plane_running": _cp_running(),
        "control_plane_pid": _read_pid(CP_PID_PATH),
        "ports_open": _open_ports(),
        "ibg_command": _discover_command(),
        "launch_mode": "attach_first",
    }
    if payload["control_plane_running"]:
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(CONTROL_STATUS)
                payload["control_status"] = r.json()
        except Exception as exc:
            payload["control_status_error"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage local IBG + control-plane runtime")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_up = sub.add_parser("up")
    p_up.set_defaults(func=cmd_up)
    p_down = sub.add_parser("down")
    p_down.set_defaults(func=cmd_down)
    p_status = sub.add_parser("status")
    p_status.set_defaults(func=cmd_status)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
