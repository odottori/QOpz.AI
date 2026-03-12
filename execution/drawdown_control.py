from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DrawdownEvent:
    index: int
    equity: float
    drawdown: float
    level: str
    sizing_scalar: float
    allow_new_positions: bool
    hedge_on: bool
    kill_switch: bool


@dataclass(frozen=True)
class DrawdownPolicyState:
    max_drawdown: float
    sizing_scalar: float
    allow_new_positions: bool
    hedge_on: bool
    kill_switch: bool
    events: list[DrawdownEvent]


def evaluate_drawdown_policy(
    *,
    equity_series: Iterable[float],
    dd_alert: float = 0.10,
    dd_stop: float = 0.15,
    dd_kill: float = 0.20,
) -> DrawdownPolicyState:
    values = [float(x) for x in equity_series]
    if not values:
        return DrawdownPolicyState(
            max_drawdown=0.0,
            sizing_scalar=1.0,
            allow_new_positions=True,
            hedge_on=False,
            kill_switch=False,
            events=[],
        )

    peak = values[0]
    max_dd = 0.0
    events: list[DrawdownEvent] = []

    sizing = 1.0
    allow_new = True
    hedge = False
    kill = False

    severity_rank = {"NORMAL": 0, "ALERT": 1, "STOP": 2, "KILL": 3}
    current_level = "NORMAL"

    for i, eq in enumerate(values):
        if eq > peak:
            peak = eq
        dd = ((peak - eq) / peak) if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

        level = "NORMAL"
        if dd >= dd_kill:
            level = "KILL"
        elif dd >= dd_stop:
            level = "STOP"
        elif dd >= dd_alert:
            level = "ALERT"

        # Escalation-only: once DD level is reached, no auto-reset without manual operator action.
        if severity_rank[level] > severity_rank[current_level]:
            if level == "ALERT":
                sizing = min(sizing, 0.5)
                allow_new = True
                hedge = False
                kill = False
            elif level == "STOP":
                sizing = min(sizing, 0.5)
                allow_new = False
                hedge = True
                kill = False
            elif level == "KILL":
                sizing = 0.0
                allow_new = False
                hedge = True
                kill = True

            events.append(
                DrawdownEvent(
                    index=i,
                    equity=eq,
                    drawdown=dd,
                    level=level,
                    sizing_scalar=sizing,
                    allow_new_positions=allow_new,
                    hedge_on=hedge,
                    kill_switch=kill,
                )
            )
            current_level = level

    return DrawdownPolicyState(
        max_drawdown=max_dd,
        sizing_scalar=sizing,
        allow_new_positions=allow_new,
        hedge_on=hedge,
        kill_switch=kill,
        events=events,
    )
