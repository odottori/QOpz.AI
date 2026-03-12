"""IBKR TWS / IB Gateway connectivity utilities (F3-T1).

This module is intentionally Windows-first and test-friendly:
- performs a fast TCP pre-check before touching ib_insync (avoids long timeouts and event-loop warnings)
- imports ib_insync lazily
"""

from __future__ import annotations

from dataclasses import dataclass
import socket
import time
from typing import Any, Dict, List, Optional


class IbkrConnectivityError(RuntimeError):
    """Raised when the broker endpoint is not reachable or the handshake fails."""


class IbkrDependencyError(RuntimeError):
    """Raised when required optional dependencies (ib_insync) are missing."""


@dataclass(frozen=True)
class IbkrProbeResult:
    ok: bool
    host: str
    port: int
    client_id: int
    duration_sec: float
    note: str = ""
    account: Optional[str] = None
    positions_count: Optional[int] = None
    summary_kv: Optional[Dict[str, str]] = None


def _tcp_precheck(host: str, port: int, timeout_sec: float) -> None:
    """Fast check: ensure something is listening on host:port (TCP)."""
    try:
        with socket.create_connection((host, int(port)), timeout=float(timeout_sec)):
            return
    except OSError as e:
        errno = getattr(e, "errno", None)
        raise IbkrConnectivityError(
            f"TCP_CONNECT_FAIL host={host} port={port} errno={errno} msg={e}"
        ) from e


def run_f3_t1_probe(
    *,
    host: str,
    port: int,
    client_id: int,
    timeout_sec: float = 2.0,
    tcp_precheck: bool = True,
    readonly: bool = True,
    account: Optional[str] = None,
) -> IbkrProbeResult:
    """Run an IBKR connectivity probe.

    Returns IbkrProbeResult on success.
    Raises:
      - IbkrConnectivityError on TCP/connect/handshake problems
      - IbkrDependencyError if ib_insync is not installed
    """
    t0 = time.time()

    if tcp_precheck:
        _tcp_precheck(host, port, timeout_sec=max(0.2, float(timeout_sec)))

    # Lazy import AFTER TCP pre-check
    try:
        from ib_insync import IB  # type: ignore
    except Exception as e:  # ImportError or other import-time issues
        raise IbkrDependencyError("MISSING_DEPENDENCY ib_insync") from e

    ib = IB()
    try:
        ok = ib.connect(host, int(port), clientId=int(client_id), timeout=float(timeout_sec), readonly=readonly, account=account)
        if not ok:
            raise IbkrConnectivityError("IB_CONNECT_FALSE")

        # Minimal, stable probes (do not place orders)
        acct = None
        summary_kv: Dict[str, str] = {}
        try:
            summary = ib.accountSummary()
            # summary is a list of AccountValue(tag, value, currency, account)
            for av in summary:
                if getattr(av, "tag", None) and getattr(av, "value", None) is not None:
                    summary_kv[str(av.tag)] = str(av.value)
                if acct is None and getattr(av, "account", None):
                    acct = str(av.account)
        except Exception:
            # keep probe robust; summary is useful but not mandatory
            pass

        positions_count = None
        try:
            positions = ib.positions()
            positions_count = len(positions) if positions is not None else 0
        except Exception:
            pass

        return IbkrProbeResult(
            ok=True,
            host=host,
            port=int(port),
            client_id=int(client_id),
            duration_sec=round(time.time() - t0, 3),
            note="OK",
            account=acct,
            positions_count=positions_count,
            summary_kv=summary_kv or None,
        )
    except IbkrDependencyError:
        raise
    except IbkrConnectivityError:
        raise
    except Exception as e:
        # Normalize all other errors as connectivity failures
        raise IbkrConnectivityError(str(e)) from e
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass
