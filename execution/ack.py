"""Ack/timeout classification utilities.

Domain 2 intent:
- Provide a broker-agnostic taxonomy for whether a submission was acknowledged.
- Keep this purely about *acknowledgement*, not about fills.

This is used by boundary adapters (paper/live) and by dev simulations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Any, Optional


class AckStatus(str, Enum):
    ACKED = "ACKED"
    NO_ACK = "NO_ACK"  # definitively not acknowledged (e.g., broker reject w/o ack)
    TIMEOUT = "TIMEOUT"  # no ack observed within deadline
    BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"  # broker connectivity failure dominates ACK taxonomy


@dataclass(frozen=True)
class AckResult:
    status: AckStatus
    ack_event_ts_utc: Optional[str] = None
    ack_latency_ms: Optional[int] = None


def classify_ack(
    events: Iterable[Mapping[str, Any]],
    *,
    ack_deadline_ms: int,
    submit_event_type: str = "SUBMIT",
    ack_event_type: str = "ACK",
) -> AckResult:
    """Classify whether an order submission was acknowledged.

    Assumptions:
    - Events include `event_type` and `ts_utc`.
    - When both SUBMIT and ACK exist, we compute latency in ms if timestamps are ISO.
      (Latency best-effort; if parsing fails we still return ACKED.)
    """
    submit_ts = None
    ack_ts = None
    for ev in events:
        et = ev.get("event_type")
        if et == submit_event_type and submit_ts is None:
            submit_ts = ev.get("ts_utc")
        if et == ack_event_type:
            ack_ts = ev.get("ts_utc")

    if ack_ts is not None:
        latency_ms = _best_effort_latency_ms(submit_ts, ack_ts)
        return AckResult(status=AckStatus.ACKED, ack_event_ts_utc=ack_ts, ack_latency_ms=latency_ms)

    # No ACK observed; if we can't compute elapsed, treat as TIMEOUT.
    elapsed_ms = _best_effort_latency_ms(submit_ts, None)
    if elapsed_ms is None:
        return AckResult(status=AckStatus.TIMEOUT)
    if elapsed_ms >= ack_deadline_ms:
        return AckResult(status=AckStatus.TIMEOUT)
    return AckResult(status=AckStatus.NO_ACK)


def _best_effort_latency_ms(submit_ts_utc: Optional[str], ack_ts_utc: Optional[str]) -> Optional[int]:
    """Compute latency in milliseconds.

    If ack_ts_utc is None, computes elapsed from submit_ts_utc to "now".
    This helper is best-effort and may return None if parsing fails.
    """
    if submit_ts_utc is None:
        return None
    try:
        from datetime import datetime, timezone

        def parse(ts: str) -> datetime:
            # Accept 'Z' or offset; Python 3.11+ supports fromisoformat with '+00:00'
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)

        t0 = parse(submit_ts_utc)
        t1 = parse(ack_ts_utc) if ack_ts_utc is not None else datetime.now(timezone.utc)
        return int((t1 - t0).total_seconds() * 1000)
    except Exception:
        return None
