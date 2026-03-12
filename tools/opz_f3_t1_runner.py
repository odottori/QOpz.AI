from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

COMMON_PORTS = [7497, 7496, 4002, 4001]


def _load_profile(profile: str) -> dict[str, Any]:
    p = ROOT / "config" / f"{profile}.toml"
    if not p.exists():
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8", errors="replace")
    in_broker = False
    out: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_broker = (line == "[broker]")
            continue
        if not in_broker or "=" not in line:
            continue
        k, v = [x.strip() for x in line.split("=", 1)]
        if k in {"host", "account"}:
            out[k] = v.strip().strip('"').strip("'")
        elif k in {"port", "clientId"}:
            try:
                out[k] = int(v.split("#", 1)[0].strip())
            except Exception:
                pass
    return out


def _tcp_probe(host: str, port: int) -> bool:
    try:
        import socket
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def _scan_ports(host: str, ports: list[int]) -> list[int]:
    return [p for p in ports if _tcp_probe(host, p)]


def _print_exact_start_instructions() -> None:
    print("F3-T1 PREREQ: serve TWS o IB Gateway (socket API) in ascolto su localhost.")
    print("OPZ: scegli UNA delle due opzioni e segui i passaggi ESATTI qui sotto.")
    print("")
    print("OPZ-OPZIONE A) TWS (Paper) su porta 7497")
    print("  1) Avvia Trader Workstation (Paper) e fai login.")
    print("  2) Menu: File -> Global Configuration -> API -> Settings")
    print("  3) Abilita: Enable ActiveX and Socket Clients")
    print("  4) Verifica: Socket port = 7497 (paper)")
    print("  5) Verifica firewall/AV: deve permettere listening locale su 127.0.0.1:7497")
    print("")
    print("OPZ-OPZIONE B) IB Gateway (Paper) su porta 4002")
    print("  1) Avvia IB Gateway (Paper) e fai login.")
    print("  2) Impostazioni API: abilita Socket/ActiveX clients (equivalente).")
    print("  3) Verifica: porta paper = 4002")
    print("")
    print("CHECK (Windows):")
    print("  Test-NetConnection -ComputerName 127.0.0.1 -Port 7497")
    print("  Test-NetConnection -ComputerName 127.0.0.1 -Port 4002")


def _run_py_file(rel: str, args: list[str]) -> int:
    cmd = [sys.executable, str((ROOT / rel).resolve())] + args
    p = subprocess.run(cmd, cwd=str(ROOT))
    return int(p.returncode)


def _run_py_module(module: str, args: list[str]) -> int:
    cmd = [sys.executable, "-m", module] + args
    p = subprocess.run(cmd, cwd=str(ROOT))
    return int(p.returncode)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="opz_f3_t1_runner")
    ap.add_argument("--profile", default="paper")
    ap.add_argument(
        "--wait-seconds",
        type=int,
        default=0,
        help="Se >0: attende che una porta IBKR comune diventi disponibile.",
    )
    ap.add_argument(
        "--wait-print-every",
        type=int,
        default=5,
        help="Ogni quanti secondi stampare progresso durante l'attesa (default: 5).",
    )
    ap.add_argument(
        "--auto-fix-port",
        action="store_true",
        help="Se trova una porta aperta diversa da config, aggiorna config/<profile>.toml via tool.",
    )
    ap.add_argument(
        "--advance-state",
        action="store_true",
        help="Se PASS: aggiorna .qoaistate.json, reconcile_step_index, rebuild_manifest, verify_manifest, certify_steps.",
    )
    ap.add_argument("--run-gates", action="store_true", help="Esegue unittest+verify_manifest+certify_steps dopo il probe.")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = _load_profile(args.profile)
    host = str(cfg.get("host") or "127.0.0.1")
    cfg_port = int(cfg.get("port") or 7497)

    print("OPZ_F3_T1_RUNNER: START")
    print(f"- profile={args.profile} host={host} configured_port={cfg_port} common_ports={COMMON_PORTS}")
    sys.stdout.flush()

    # 1) Detect open ports (optionally wait)
    try:
        open_ports = _scan_ports(host, COMMON_PORTS)
        if not open_ports and args.wait_seconds > 0:
            wait_total = max(1, args.wait_seconds)
            end = time.time() + wait_total
            print(f"OPZ_F3_T1_RUNNER: WAITING up to {wait_total}s for a listener (Ctrl+C to abort)...")
            sys.stdout.flush()
            last_print = 0.0
            while True:
                now = time.time()
                if now >= end:
                    break
                open_ports = _scan_ports(host, COMMON_PORTS)
                if open_ports:
                    break
                remaining = int(end - now)
                if args.wait_print_every > 0 and (last_print == 0.0 or (now - last_print) >= args.wait_print_every):
                    print(f"OPZ_F3_T1_RUNNER: waiting... remaining={remaining}s open_ports=[]")
                    sys.stdout.flush()
                    last_print = now
                time.sleep(1)
    except KeyboardInterrupt:
        print("OPZ_F3_T1_RUNNER: ABORTED_BY_USER (exit=130)")
        return 130

    if not open_ports:
        print("OPZ_F3_T1_RUNNER: NO_LISTENER (exit=10)")
        print(f"- host={host} configured_port={cfg_port} open_ports=[]")
        _print_exact_start_instructions()
        return 10

    # Prefer configured port if open; else first open.
    chosen = cfg_port if cfg_port in open_ports else open_ports[0]
    print("OPZ_F3_T1_RUNNER: PORT_READY")
    print(f"- host={host} configured_port={cfg_port} open_ports={open_ports} chosen_port={chosen}")

    if args.auto_fix_port and chosen != cfg_port:
        rc = _run_py_file("tools/set_broker_port.py", ["--profile", args.profile, "--port", str(chosen)])
        if rc != 0:
            print("OPZ_F3_T1_RUNNER: AUTO_FIX_PORT_FAIL (exit=11)")
            return 11

    # 2) Run connectivity tool (this prints PASS/FAIL)
    tool_args = ["--profile", args.profile, "--scan-common-ports"]
    if args.advance_state:
        tool_args.append("--advance-state")
    rc = _run_py_file("tools/f3_t1_ibkr_connectivity.py", tool_args)
    if rc != 0:
        return rc

    # 3) Optional gates
    if args.run_gates:
        if _run_py_module("unittest", ["-q"]) != 0:
            return 20
        # If state changed, rebuild manifest before verifying (tool-based, idempotent).
        if args.advance_state:
            if _run_py_file("tools/reconcile_step_index.py", []) != 0:
                return 23
            if _run_py_file("tools/rebuild_manifest.py", []) != 0:
                return 24
        if _run_py_file("tools/verify_manifest.py", []) != 0:
            return 21
        if _run_py_file("tools/certify_steps.py", []) != 0:
            return 22

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
