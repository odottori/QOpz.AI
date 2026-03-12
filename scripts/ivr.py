from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

@dataclass(frozen=True)
class IvPoint:
    date: str  # ISO YYYY-MM-DD
    iv: float

def iv_rank(values: list[float]) -> float:
    """
    IV Rank (0..100) over the provided lookback window:
        (current_iv - min_iv) / (max_iv - min_iv) * 100
    Edge-case: constant IV -> 50.
    """
    if not values:
        raise ValueError("values is empty")
    mn = min(values)
    mx = max(values)
    cur = values[-1]
    if mx == mn:
        return 50.0
    # clamp defensively
    rank = (cur - mn) / (mx - mn) * 100.0
    if rank < 0.0:
        return 0.0
    if rank > 100.0:
        return 100.0
    return rank

def load_iv_history_csv(path: Path) -> dict[str, list[IvPoint]]:
    """
    Expected CSV columns: date,ticker,iv
    """
    out: dict[str, list[IvPoint]] = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if not row:
                continue
            t = (row.get("ticker") or "").strip().upper()
            d = (row.get("date") or "").strip()
            iv_s = (row.get("iv") or "").strip()
            if not t or not d or not iv_s:
                # ignore malformed rows
                continue
            try:
                iv_v = float(iv_s)
            except ValueError:
                continue
            out.setdefault(t, []).append(IvPoint(date=d, iv=iv_v))
    # sort by date to ensure "current" is last
    for t, pts in list(out.items()):
        out[t] = sorted(pts, key=lambda p: p.date)
    return out

def compute_iv_rank_from_history(history: dict[str, list[IvPoint]], ticker: str, *, lookback: int = 252) -> float | None:
    t = ticker.strip().upper()
    pts = history.get(t)
    if not pts:
        return None
    vals = [p.iv for p in pts[-lookback:]]
    return iv_rank(vals)
