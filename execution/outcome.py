from __future__ import annotations

from enum import Enum


class ExecutionOutcome(str, Enum):
    """Normalized execution outcome codes for Domain 2 execution controls."""

    REJECTED = "REJECTED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    ABANDONED = "ABANDONED"
    TIMEOUT = "TIMEOUT"
    NO_ACK = "NO_ACK"
    ACKED = "ACKED"
