#!/usr/bin/env python
"""F3-T1 — IBKR connectivity check via TWS/IB Gateway socket.

This tool is safe to import (no ib_insync import at module import time).
It performs:
- TCP listener check
- Optional ib_insync connect + basic queries (positions)

Exit codes:
  0 PASS
  10 FAIL (connectivity / missing deps / no listener)
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class BrokerCfg:
    host: str
    port: int
    client_id: int


def _load_profile_cfg(profile: str) -> BrokerCfg:
    # Prefer execution.config_loader if available.
    try:
        from execution.config_loader import load_profile_config  # type: ignore
        cfg: Dict[str, Any] = load_profile_config(profile)
        b = cfg.get("broker", {}) or {}
        host = str(b.get("host", "127.0.0.1"))
        port = int(b.get("port", 7497))
        client_id = int(b.get("client_id", b.get("clientId", 7)))
        return BrokerCfg(host=host, port=port, client_id=client_id)
    except Exception:
        # Fallback: minimal parse for host/port only
        p = ROOT / "config" / f"{profile}.toml"
        host = "127.0.0.1"
        port = 7497
        client_id = 7
        if p.exists():
            txt = p.read_text(encoding="utf-8", errors="ignore")
            for line in txt.splitlines():
                s = line.strip()
                if s.startswith("host"):
                    host = s.split("=", 1)[1].strip().strip('"').strip("'")
                if s.startswith("port"):
                    try:
                        port = int(s.split("=", 1)[1].strip())
                    except Exception:
                        pass
                if s.startswith("clientId") or s.startswith("client_id"):
                    try:
                        client_id = int(s.split("=", 1)[1].strip())
                    except Exception:
                        pass
        return BrokerCfg(host=host, port=port, client_id=client_id)


def _tcp_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _require_ib_insync() -> None:
    try:
        import ib_insync  # noqa: F401
    except Exception as e:
        raise RuntimeError("MISSING_DEP: ib_insync not installed. Run: py -m pip install -r requirements-broker-ib.txt") from e


def _connect_and_probe(cfg: BrokerCfg, timeout_sec: int) -> Dict[str, Any]:
    from ib_insync import IB

    ib = IB()
    # ib_insync uses RequestTimeout for awaitables (seconds)
    ib.RequestTimeout = float(timeout_sec)
    ib.connect(cfg.host, cfg.port, clientId=cfg.client_id, timeout=timeout_sec)
    try:
        sv = int(getattr(ib.client, "serverVersion", lambda: -1)())
        positions = ib.positions()
        return {
            "server_version": sv,
            "positions_count": len(positions),
        }
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="paper")
    ap.add_argument("--timeout", type=int, default=3)
    ap.add_argument("--scan-common-ports", action="store_true")
    ap.add_argument("--advance-state", action="store_true")
    return ap.parse_args(argv)


def _advance_state(step_id: str, next_step: str) -> None:
    # Tool-based: mark complete + unfreeze + set next.
    # Do NOT touch manifest here; outer runner handles reconcile/rebuild.
    from tools.opz_step_ctl import main as step_ctl_main  # type: ignore
    # unfreeze (idempotent)
    step_ctl_main(["--unfreeze", step_id])
    step_ctl_main(["--complete", step_id, "--advance-to", next_step])
    step_ctl_main(["--set-next", next_step])


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    cfg = _load_profile_cfg(args.profile)
    common_ports = [cfg.port, 7497, 7496, 4002, 4001] if args.scan_common_ports else [cfg.port]

    open_ports = [p for p in dict.fromkeys(common_ports) if _tcp_open(cfg.host, p)]
    if not open_ports:
        print("F3-T1 IBKR CHECK: CRITICAL_FAIL (exit=10)")
        print(f"- NO_TCP_LISTENER host={cfg.host} ports_tested={common_ports}")
        return 10

    chosen_port = open_ports[0]
    cfg2 = BrokerCfg(host=cfg.host, port=chosen_port, client_id=cfg.client_id)

    try:
        _require_ib_insync()
        info = _connect_and_probe(cfg2, timeout_sec=args.timeout)
    except Exception as e:
        print("F3-T1 IBKR CHECK: CRITICAL_FAIL (exit=10)")
        print(f"- CONNECT_FAIL err={type(e).__name__} msg={e}")
        print(f"- TCP_OK host={cfg2.host} port={cfg2.port}")
        return 10

    print("F3-T1 IBKR CHECK: PASS (exit=0)")
    print(f"- CONNECTED host={cfg2.host} port={cfg2.port} clientId={cfg2.client_id}")
    print(f"- SERVER_VERSION {info.get('server_version')}")
    print(f"- POSITIONS count={info.get('positions_count')}")
    if args.scan_common_ports:
        print(f"- PORT_SCAN configured_port={cfg.port} open_ports={open_ports}")

    if args.advance_state:
        _advance_state("F3-T1", "F3-T2")
        print("- STATE advanced next_step=F3-T2 (F3-T1 completed; any blocked marker removed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
