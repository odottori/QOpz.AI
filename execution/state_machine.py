from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OrderState = Literal[
    "NEW",
    "SUBMITTED",
    "ACKED",
    "DEDUPLICATED",
    "REJECTED",
    "CANCELLED",
    "FILLED",
]

# Domain 2 state machine (minimal). It must accept ACKED because upstream ACK
# classification emits it and D2.16 derives state from journal events.

_ALLOWED = {
    ("NEW", "SUBMITTED"),
    ("NEW", "REJECTED"),

    ("SUBMITTED", "ACKED"),
    ("SUBMITTED", "DEDUPLICATED"),
    ("SUBMITTED", "REJECTED"),
    ("SUBMITTED", "CANCELLED"),
    ("SUBMITTED", "FILLED"),

    ("ACKED", "REJECTED"),
    ("ACKED", "CANCELLED"),
    ("ACKED", "FILLED"),

    ("DEDUPLICATED", "FILLED"),
    ("DEDUPLICATED", "REJECTED"),
    ("DEDUPLICATED", "CANCELLED"),
}

_STATES = {"NEW", "SUBMITTED", "ACKED", "DEDUPLICATED", "REJECTED", "CANCELLED", "FILLED"}


def is_allowed(prev: str, nxt: str) -> bool:
    return (prev, nxt) in _ALLOWED


def normalize_state(state: str) -> str:
    if state is None:
        raise ValueError("normalize_state called with None — caller must handle missing state explicitly")
    s = state.upper()
    if s not in _STATES:
        raise ValueError(f"Unknown state: {state!r}")
    return s


@dataclass(frozen=True)
class StateTransition:
    prev: str
    nxt: str
