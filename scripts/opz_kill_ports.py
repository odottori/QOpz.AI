from __future__ import annotations

import argparse
import platform
import socket
import subprocess
import sys
import time
from typing import Iterable


def is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", int(port))) == 0


def iter_windows_listening_pids(port: int) -> list[int]:
    proc = subprocess.run(["netstat", "-ano", "-p", "tcp"], text=True, capture_output=True, check=False)
    pids: set[int] = set()
    needle = f":{int(port)}"
    for raw in (proc.stdout or "").splitlines():
        line = raw.strip()
        if not line or "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_addr, state, pid_text = parts[1], parts[3], parts[4]
        if not local_addr.endswith(needle) or state.upper() != "LISTENING":
            continue
        try:
            pids.add(int(pid_text))
        except ValueError:
            continue
    return sorted(pids)


def kill_windows_pid(pid: int) -> bool:
    proc = subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], text=True, capture_output=True, check=False)
    return proc.returncode == 0


def wait_closed(port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_port_open(port):
            return True
        time.sleep(0.25)
    return not is_port_open(port)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ports", nargs="+", type=int, required=True)
    parser.add_argument("--wait", type=float, default=6.0)
    args = parser.parse_args()

    if platform.system().lower() != "windows":
        print("LAUNCHER_STOP unsupported_platform")
        return 0

    killed = 0
    for port in args.ports:
        for pid in iter_windows_listening_pids(port):
            if kill_windows_pid(pid):
                killed += 1
        wait_closed(port, args.wait)

    api_open = is_port_open(8765)
    ui_open = is_port_open(8173)
    print(f"LAUNCHER_STOP killed_count={killed} api_open={api_open} ui_open={ui_open}")
    return 0 if not api_open and not ui_open else 3


if __name__ == "__main__":
    raise SystemExit(main())
