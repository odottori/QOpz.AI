"""Compatibility module: ACK taxonomy (Domain 2).

This module provides the *canonical* InternalEvent contract used by higher-level
execution controls. It is intentionally self-contained and does not alter the
behavior of existing code paths (e.g., execution.ack.classify_ack).

Contract (stable):
- InternalEvent(ts_utc: float, event_type: str, payload: dict)

Classification intent:
- Given a list of internal events (submit + optional ACK), determine ACK status
  w.r.t. a deadline. Time is evaluated in epoch-seconds (UTC).

NOTE:
This file is added as a normalization patch to preserve the post-incident API
described in canonical requirements, without refactoring existing modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Mapping, Any

from execution.ack import AckStatus


@dataclass(frozen=True)
class InternalEvent:
    ts_utc: float
    event_type: str
    payload: dict


def _looks_broker_unavailable(ev: InternalEvent) -> bool:
    """Heuristic detection for broker-unavailable events.

    We keep this permissive to remain compatible across paper/live adapters and
    broker normalization layers. It should not affect dev flows unless such an
    event is explicitly present.
    """
    et = (ev.event_type or "").upper()
    if et in {"BROKER_UNAVAILABLE", "REJECTED_BROKER_UNAVAILABLE", "BROKER_DOWN", "BROKER_OFFLINE"}:
        return True
    payload = ev.payload or {}
    if isinstance(payload, dict):
        for k in ("status", "reason", "code", "error"):
            v = payload.get(k)
            if isinstance(v, str) and "BROKER_UNAVAILABLE" in v.upper():
                return True
    return False

def classify_ack_status(
    events: Iterable[InternalEvent],
    *,
    ack_event_type: str = "ACK",
    submit_event_type: str = "SUBMIT",
    ack_deadline_ts_utc: float | None = None,
    ack_deadline_s: float = 5.0,
    submit_ts_utc: float | None = None,
    now_ts_utc: float | None = None,
) -> AckStatus:
    """Classify ACK status from a sequence of InternalEvent.

    - If an ACK event exists -> ACKED.
    - Otherwise, compute `effective_now_ts_utc`:
        * use `now_ts_utc` if provided
        * else use max(event.ts_utc) over provided events
        * else fall back to `submit_ts_utc` (if provided)
    - Determine submit time:
        * first SUBMIT event ts_utc if present
        * else `submit_ts_utc` if provided
    - If we cannot determine a submit time -> NO_ACK (can't time out reliably).
    - Deadline = ack_deadline_ts_utc if provided, else submit_ts + ack_deadline_s
    - If effective_now_ts_utc >= deadline -> TIMEOUT
      else -> NO_ACK
    """
    # Materialize once; events can be generators.
    evs = list(events)

    # Dominance: broker unavailable overrides all other states
    for ev in evs:
        if _looks_broker_unavailable(ev):
            return AckStatus.BROKER_UNAVAILABLE

    # Fast-path: any ACK => ACKED
    for ev in evs:
        if ev.event_type == ack_event_type:
            return AckStatus.ACKED

    # Determine submit timestamp
    submit_ts = None
    for ev in evs:
        if ev.event_type == submit_event_type:
            submit_ts = ev.ts_utc
            break
    if submit_ts is None:
        submit_ts = submit_ts_utc

    if submit_ts is None:
        # No submit anchor -> cannot evaluate deadline. Keep conservative.
        return AckStatus.NO_ACK

    # Determine effective "now"
    if now_ts_utc is not None:
        effective_now = now_ts_utc
    else:
        effective_now = max((ev.ts_utc for ev in evs), default=None)
        if effective_now is None:
            effective_now = submit_ts_utc

    if effective_now is None:
        # Still can't evaluate deadline.
        return AckStatus.NO_ACK

    deadline = float(ack_deadline_ts_utc) if ack_deadline_ts_utc is not None else (submit_ts + float(ack_deadline_s))
    if effective_now >= deadline:
        return AckStatus.TIMEOUT
    return AckStatus.NO_ACK


def normalize_internal_event(
    event: Mapping[str, Any],
    *,
    ts_key: str = "ts_utc",
    type_key: str = "event_type",
    payload_key: str = "payload",
) -> InternalEvent:
    """Best-effort normalizer for dict-like events into InternalEvent."""
    ts = float(event.get(ts_key))
    et = str(event.get(type_key))
    payload = event.get(payload_key) or {}
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return InternalEvent(ts_utc=ts, event_type=et, payload=payload)
