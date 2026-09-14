from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = REPO_ROOT / "logs" / "opz_launcher_state.json"
WINDOW_NAME = "qopz-ai"
API_PORT = 8765
UI_PORT = 8173
API_URL = f"http://127.0.0.1:{API_PORT}/health"
UI_URL = f"http://127.0.0.1:{UI_PORT}/"
PANE_SCRIPT = REPO_ROOT / "scripts" / "opz_terminal_pane.ps1"


def _json_dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _iter_listening_pids(port: int) -> list[int]:
    proc = subprocess.run(["netstat", "-ano", "-p", "tcp"], text=True, capture_output=True, check=False)
    pids: set[int] = set()
    needle = f":{port}"
    for raw in (proc.stdout or "").splitlines():
        line = raw.strip()
        if not line or "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        if not parts[1].endswith(needle) or parts[3].upper() != "LISTENING":
            continue
        try:
            pids.add(int(parts[4]))
        except ValueError:
            continue
    return sorted(pids)


def _kill_pids(pids: Iterable[int]) -> int:
    killed = 0
    for pid in sorted({int(p) for p in pids if int(p) > 0}):
        proc = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], text=True, capture_output=True, check=False)
        if proc.returncode == 0:
            killed += 1
    return killed


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_port_closed(port: int, timeout_sec: float) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not _port_open(port):
            return True
        time.sleep(0.25)
    return not _port_open(port)


def _wait_for_http(url: str, timeout_sec: float) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2.0) as response:
                if 200 <= int(getattr(response, "status", 0)) < 400:
                    return True
        except URLError:
            pass
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _wt_path() -> str | None:
    return shutil.which("wt.exe") or shutil.which("wt")


def _ps_path() -> str:
    return shutil.which("powershell.exe") or "powershell.exe"


def _build_wt_command() -> list[str]:
    wt = _wt_path() or "wt.exe"
    ps = _ps_path()
    return [
        wt,
        "-w",
        WINDOW_NAME,
        "new-tab",
        "--title",
        "QOPZ API",
        "--startingDirectory",
        str(REPO_ROOT),
        ps,
        "-NoLogo",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(PANE_SCRIPT),
        "-Role",
        "api",
        ";",
        "split-pane",
        "-H",
        "--title",
        "QOPZ UI",
        "--startingDirectory",
        str(REPO_ROOT / "ui"),
        ps,
        "-NoLogo",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(PANE_SCRIPT),
        "-Role",
        "ui",
    ]


def cmd_stop(args: argparse.Namespace) -> int:
    total_killed = 0
    for port in (API_PORT, UI_PORT):
        total_killed += _kill_pids(_iter_listening_pids(port))
        _wait_for_port_closed(port, timeout_sec=5.0)
    payload = {
        "window_name": WINDOW_NAME,
        "last_stop_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ports": {"api": API_PORT, "ui": UI_PORT},
        "last_stop_result": {
            "killed_count": total_killed,
            "api_open": _port_open(API_PORT),
            "ui_open": _port_open(UI_PORT),
        },
    }
    _json_dump(STATE_PATH, payload)
    print(f"LAUNCHER_STOP killed_count={total_killed} api_open={_port_open(API_PORT)} ui_open={_port_open(UI_PORT)}")
    if _port_open(API_PORT) or _port_open(UI_PORT):
        return 3
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    stop_rc = cmd_stop(args)
    if stop_rc not in (0, 3):
        return stop_rc

    if not PANE_SCRIPT.exists():
        print(f"LAUNCHER_FAIL pane script missing path={PANE_SCRIPT}")
        return 12
    if _wt_path() is None:
        print("LAUNCHER_FAIL wt.exe not found in PATH")
        return 20

    subprocess.Popen(_build_wt_command(), cwd=str(REPO_ROOT))
    print(f"LAUNCHER_START mode=wt window={WINDOW_NAME}")

    api_ok = _wait_for_http(API_URL, timeout_sec=float(args.api_timeout))
    if not api_ok:
        print(f"LAUNCHER_FAIL api health timeout url={API_URL}")
        return 10
    print(f"LAUNCHER_OK api url={API_URL}")

    ui_ok = _wait_for_http(UI_URL, timeout_sec=float(args.ui_timeout))
    if not ui_ok:
        print(f"LAUNCHER_FAIL ui readiness timeout url={UI_URL}")
        return 11
    print(f"LAUNCHER_OK ui url={UI_URL}")

    payload = {
        "window_name": WINDOW_NAME,
        "last_start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ports": {"api": API_PORT, "ui": UI_PORT},
        "wt_command": _build_wt_command(),
    }
    _json_dump(STATE_PATH, payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opz_launcher_reset")
    sub = parser.add_subparsers(dest="cmd", required=True)
    start = sub.add_parser("start")
    start.add_argument("--api-timeout", type=float, default=20.0)
    start.add_argument("--ui-timeout", type=float, default=30.0)
    start.set_defaults(func=cmd_start)
    stop = sub.add_parser("stop")
    stop.set_defaults(func=cmd_stop)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
