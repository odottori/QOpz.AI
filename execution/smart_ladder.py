from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LadderStep:
    step_no: int
    limit_price: float
    timeout_sec: int


def build_smart_limit_ladder(*, bid: float, ask: float, tick: float = 0.01, timeout_sec: int = 120) -> list[LadderStep]:
    """Build Smart Limit Order Ladder.

    Canonical source: canonici/01_TECNICO.md §T6.2

    Steps (BUY side semantics):
      1) mid
      2) mid - 1 tick
      3) mid - 3 tick
      4) mid - 5 tick
      5) abandon (represented by returning only the 4 pricing steps; caller handles abandon)

    Notes
    -----
    - We keep the ladder price levels deterministic.
    - For SELL side, the caller can mirror if/when canonici specify. (Not invented here.)
    """
    mid = (float(bid) + float(ask)) / 2.0

    steps = [
        (1, mid),
        (2, mid - 1.0 * float(tick)),
        (3, mid - 3.0 * float(tick)),
        (4, mid - 5.0 * float(tick)),
    ]
    return [LadderStep(step_no=sno, limit_price=lp, timeout_sec=int(timeout_sec)) for sno, lp in steps]
