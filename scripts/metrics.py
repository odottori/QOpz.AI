from __future__ import annotations

import math
from dataclasses import dataclass


def equity_curve(returns: list[float], start: float = 1.0) -> list[float]:
    eq: list[float] = [start]
    v = start
    for r in returns:
        v *= (1.0 + r)
        eq.append(v)
    return eq


def max_drawdown(equity: list[float]) -> float:
    peak = -math.inf
    mdd = 0.0
    for v in equity:
        peak = v if v > peak else peak
        if peak > 0:
            dd = (peak - v) / peak
            mdd = dd if dd > mdd else mdd
    return float(mdd)


def win_rate(returns: list[float]) -> float:
    if not returns:
        return 0.0
    wins = sum(1 for r in returns if r > 0)
    return wins / len(returns)


def annualized_sharpe(returns: list[float], periods_per_year: int = 252) -> float:
    if not returns:
        return 0.0
    mu = sum(returns) / len(returns)
    var = sum((r - mu) ** 2 for r in returns) / max(1, (len(returns) - 1))
    sd = math.sqrt(max(var, 1e-18))
    if sd <= 0:
        return 0.0
    return (mu / sd) * math.sqrt(periods_per_year)
