"""QuantOptionAI — Domain 2 (D2.14)
Broker event schema (minimal) + normalization to internal event types.

Design goals:
- Gate0-safe: no broker SDK dependency.
- Deterministic mapping from "raw" adapter/broker payloads to internal event trail.
- Small surface area so paper/live adapters can plug in later without refactors.

This module is intentionally pure (no I/O).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class BrokerVenue(str, Enum):
    UNKNOWN = "UNKNOWN"
    IBKR = "IBKR"
    SIM = "SIM"


class InternalEventType(str, Enum):
    # boundary / submission
    SUBMIT_ATTEMPT = "SUBMIT_ATTEMPT"
    ACCEPTED_BOUNDARY = "ACCEPTED_BOUNDARY"
    REJECTED_SCHEMA = "REJECTED_SCHEMA"
    REJECTED_WIDE_SPREAD = "REJECTED_WIDE_SPREAD"
    REJECTED_BROKER_UNAVAILABLE = "REJECTED_BROKER_UNAVAILABLE"
    REJECTED_BY_BROKER = "REJECTED_BY_BROKER"

    # lifecycle
    ACK = "ACK"
    FILL = "FILL"
    CANCEL = "CANCEL"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class BrokerEvent:
    """Minimal raw event emitted by a paper/live adapter.

    The adapter should populate:
      - venue: broker venue (e.g. IBKR)
      - ts_utc: timezone-aware UTC datetime (preferred) or naive interpreted as UTC
      - event_type: adapter/broker event type string (free-form)
      - payload: arbitrary dict-like payload
    """
    venue: BrokerVenue
    ts_utc: datetime
    event_type: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class InternalEvent:
    """Canonical internal event for order_event trail."""
    ts_utc: datetime
    type: InternalEventType
    message: str | None
    payload: Mapping[str, Any]


def normalize_broker_event(be: BrokerEvent) -> InternalEvent:
    """Normalize BrokerEvent to InternalEventType.

    Mapping rules (minimal, extensible):
      - event_type contains 'ack' => ACK
      - contains 'fill' => FILL
      - contains 'cancel' => CANCEL
      - contains 'reject' => REJECTED_BY_BROKER
      - otherwise => ERROR (unknown)
    """
    et = (be.event_type or "").strip().lower()

    if "ack" in et or et in {"accepted", "submitted"}:
        t = InternalEventType.ACK
    elif "fill" in et or "filled" in et or et in {"execution", "trade"}:
        t = InternalEventType.FILL
    elif "cancel" in et or "canceled" in et:
        t = InternalEventType.CANCEL
    elif "reject" in et or "rejected" in et:
        t = InternalEventType.REJECTED_BY_BROKER
    else:
        t = InternalEventType.ERROR

    msg = None
    if isinstance(be.payload, Mapping):
        msg = str(be.payload.get("message") or be.payload.get("msg") or "") or None

    return InternalEvent(ts_utc=be.ts_utc, type=t, message=msg, payload=be.payload)
