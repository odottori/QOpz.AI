from __future__ import annotations

from typing import Dict, Iterable, List


def build_margin_efficiency_summary(*, trades: Iterable[Dict[str, float]], capital: float) -> Dict[str, float]:
    rows: List[Dict[str, float]] = [dict(t) for t in trades]
    cap = float(capital)
    if cap <= 0:
        raise ValueError("capital must be > 0")

    margins = [max(0.0, float(r.get("margin_used", 0.0))) for r in rows]
    pnls = [float(r.get("pnl", 0.0)) for r in rows]

    avg_margin_used = (sum(margins) / len(margins)) if margins else 0.0
    total_pnl = sum(pnls)

    margin_efficiency = (total_pnl / avg_margin_used) if avg_margin_used > 0 else 0.0
    avg_margin_used_pct = (avg_margin_used / cap) if cap > 0 else 0.0

    return {
        "avg_margin_used": avg_margin_used,
        "avg_margin_used_pct": avg_margin_used_pct,
        "total_pnl": total_pnl,
        "margin_efficiency": margin_efficiency,
    }
