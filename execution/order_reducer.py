from __future__ import annotations

"""
Domain 2.15 — State machine hardening (pure, deterministic)

This module provides a deterministic reducer from journal events -> final order state
and a small set of invariants to keep journal/state/outcome coherent.

Design constraints:
- Gate0-safe (no I/O, no broker deps)
- Does not change existing execution behavior unless explicitly called
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Sequence

from .state_machine import normalize_state, is_allowed, OrderState


@dataclass(frozen=True)
class OrderEvent:
    ts_utc: datetime | str
    event_type: str
    prev_state: Optional[str]
    new_state: Optional[str]
    details: Optional[Mapping[str, Any]] = None


def _parse_ts(ts: datetime | str) -> tuple[int, str]:
    """
    Return a deterministic sort key for timestamps.
    Primary: datetime -> epoch microseconds.
    Fallback: ISO-ish string -> lexical.
    """
    if isinstance(ts, datetime):
        # treat naive as UTC (consistent with storage.utc_now producing tz-aware)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return (int(ts.timestamp() * 1_000_000), "")
    s = str(ts or "")
    # Best-effort ISO parse without third-party deps
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (int(dt.timestamp() * 1_000_000), "")
    except Exception:
        return (0, s)


def reduce_events_to_state(
    events: Iterable[Mapping[str, Any]] | Iterable[OrderEvent],
    *,
    initial_state: str = "NEW",
    strict_prev_state: bool = True,
) -> str:
    """
    Deterministically reduce journal events to a final normalized state.

    Rules:
    - Events are processed ordered by ts_utc (stable).
    - If an event has new_state, it is applied to the reducer state.
    - If strict_prev_state=True and event.prev_state is present, it must match current state.
    - Transitions are validated using execution.state_machine.is_allowed().
    """
    cur = normalize_state(initial_state)

    # normalize events to OrderEvent list
    evs: list[OrderEvent] = []
    for e in events:
        if isinstance(e, OrderEvent):
            evs.append(e)
        else:
            evs.append(
                OrderEvent(
                    ts_utc=e.get("ts_utc"),
                    event_type=str(e.get("event_type") or ""),
                    prev_state=e.get("prev_state"),
                    new_state=e.get("new_state"),
                    details=e.get("details") or e.get("details_json"),
                )
            )

    evs.sort(key=lambda x: (_parse_ts(x.ts_utc), x.event_type))

    for ev in evs:
        if ev.new_state is None:
            continue
        nxt = normalize_state(ev.new_state)

        if strict_prev_state and ev.prev_state is not None:
            prev = normalize_state(ev.prev_state)
            if prev != cur:
                raise ValueError(f"Prev-state mismatch: cur={cur} event.prev_state={prev} event_type={ev.event_type}")

        if cur == nxt:
            continue

        if not is_allowed(cur, nxt):
            raise ValueError(f"Illegal transition: {cur}->{nxt} (event_type={ev.event_type})")

        cur = nxt

    return cur


def reconcile_invariants(
    events: Sequence[Mapping[str, Any]] | Sequence[OrderEvent],
    *,
    final_state: str,
    outcome: Optional[str] = None,
) -> list[str]:
    """
    Return a list of invariant violations between journal -> state -> outcome.

    This is a pure check helper used by tests and future reconcile hardening.
    """
    fs = normalize_state(final_state)
    etypes = []
    for e in events:
        if isinstance(e, OrderEvent):
            etypes.append((e.event_type or "").upper())
        else:
            etypes.append(str(e.get("event_type") or "").upper())

    violations: list[str] = []

    # dominance: broker unavailable
    if "REJECTED_BROKER_UNAVAILABLE" in etypes:
        if fs != "REJECTED":
            violations.append("BROKER_UNAVAILABLE_REQUIRES_REJECTED_STATE")
        if outcome is not None and outcome != "REJECTED_BROKER_UNAVAILABLE":
            violations.append("BROKER_UNAVAILABLE_REQUIRES_REJECTED_BROKER_UNAVAILABLE_OUTCOME")

    if fs == "FILLED":
        if not any("FILL" in t for t in etypes):
            violations.append("FILLED_REQUIRES_FILL_EVENT")

    if fs == "REJECTED":
        if not any("REJECT" in t for t in etypes):
            violations.append("REJECTED_REQUIRES_REJECT_EVENT")

    if fs == "CANCELLED":
        if not any("CANCEL" in t or "ABANDON" in t or "TIMEOUT" in t for t in etypes):
            # outcome classification may still label TIMEOUT/ABANDONED while state remains CANCELLED
            if outcome not in ("CANCELLED", "ABANDONED", "TIMEOUT"):
                violations.append("CANCELLED_REQUIRES_CANCEL_OR_TIMEOUT_OR_ABANDON")
    return violations
