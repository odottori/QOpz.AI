from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PlanKind = Literal["REJECT", "LADDER", "TWAP"]


@dataclass(frozen=True)
class ExecutionPlan:
    kind: PlanKind
    reason: str
    details: dict


@dataclass(frozen=True)
class TwapSlice:
    slice_no: int
    quantity: int
    offset_sec: int


def build_twap_slices(*, total_quantity: int, twap_slices: int = 3, twap_slice_interval_sec: int = 300) -> list[TwapSlice]:
    """Build deterministic TWAP schedule (F5-T2): default 3 slices at 5-min steps."""
    q = int(total_quantity)
    n = int(twap_slices)
    if q <= 0 or n <= 0:
        return []

    base = q // n
    rem = q % n
    out: list[TwapSlice] = []
    for i in range(n):
        qty = base + (1 if i < rem else 0)
        out.append(TwapSlice(slice_no=i + 1, quantity=qty, offset_sec=i * int(twap_slice_interval_sec)))
    return out


def select_execution_plan(
    *,
    bid: float,
    ask: float,
    spread_reject_pct: float = 0.10,
    spread_reject_abs: float | None = None,
    enable_twap: bool = False,
    twap_trigger_abs: float = 0.50,
    twap_slices: int = 3,
    twap_slice_interval_sec: int = 300,
    legs_count: int = 4,
    order_quantity: int | None = None,
) -> ExecutionPlan:
    """Select execution plan based on canonici."""
    if bid <= 0 or ask <= 0 or ask < bid:
        return ExecutionPlan(kind="REJECT", reason="INVALID_QUOTE", details={"bid": bid, "ask": ask})

    mid = (bid + ask) / 2.0
    spread_abs = ask - bid
    spread_pct = (spread_abs / mid) if mid else 1.0

    if spread_reject_abs is not None and spread_abs > float(spread_reject_abs):
        return ExecutionPlan(
            kind="REJECT",
            reason="SPREAD_TOO_WIDE_ABS",
            details={"bid": bid, "ask": ask, "mid": mid, "spread_abs": spread_abs, "spread_pct": spread_pct, "spread_reject_abs": float(spread_reject_abs)},
        )

    if spread_pct > spread_reject_pct:
        return ExecutionPlan(
            kind="REJECT",
            reason="SPREAD_TOO_WIDE",
            details={"bid": bid, "ask": ask, "mid": mid, "spread_abs": spread_abs, "spread_pct": spread_pct},
        )

    if enable_twap and int(legs_count) >= 4 and spread_abs > twap_trigger_abs:
        duration_sec = twap_slices * twap_slice_interval_sec
        slices = (
            [
                s.__dict__
                for s in build_twap_slices(
                    total_quantity=int(order_quantity),
                    twap_slices=twap_slices,
                    twap_slice_interval_sec=twap_slice_interval_sec,
                )
            ]
            if order_quantity is not None
            else []
        )
        return ExecutionPlan(
            kind="TWAP",
            reason="WIDE_SPREAD_TWAP",
            details={
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "spread_abs": spread_abs,
                "spread_pct": spread_pct,
                "legs_count": int(legs_count),
                "twap_trigger_abs": float(twap_trigger_abs),
                "twap_slices": twap_slices,
                "twap_slice_interval_sec": twap_slice_interval_sec,
                "duration_sec": duration_sec,
                "slices": slices,
            },
        )

    return ExecutionPlan(kind="LADDER", reason="SMART_LADDER", details={"bid": bid, "ask": ask, "mid": mid, "spread_abs": spread_abs, "spread_pct": spread_pct})
