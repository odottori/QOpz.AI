from __future__ import annotations

"""
F1-T3 — Options chain data quality checks (integration).

Checks (per canonici/02_TEST.md):
- bid <= ask (always) -> exclude row, record issue
- delta put in [-1, 0] (always) -> exclude, warning
- delta call in [0, 1] (always) -> exclude, warning
- IV in (0, 5) (always) -> exclude, warning
- Put-call parity alert: |C - P - (S - K*exp(-rT))| < threshold (alert only)

Sampling:
- 100 strikes random per 5 days (deterministic via seed)

This module is stdlib-only and is suitable for dev + unittest. It does not require
network access or external data sources.
"""

import csv
import json
import math
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class OptionQuote:
    asof: date
    symbol: str
    expiry: date
    strike: float
    right: str  # "C" or "P"
    bid: float
    ask: float
    delta: float
    iv: float
    underlying: float
    r: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0


def _parse_date(s: str) -> date:
    return date.fromisoformat(s.strip())


def load_chain_csv(path: Path) -> list[OptionQuote]:
    if not path.exists():
        raise FileNotFoundError(f"missing CSV: {path}")
    out: list[OptionQuote] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        required = ["asof","symbol","expiry","strike","right","bid","ask","delta","iv","underlying","r"]
        missing = [k for k in required if k not in (r.fieldnames or [])]
        if missing:
            raise ValueError(f"options chain CSV missing columns: {missing}")
        for row in r:
            out.append(
                OptionQuote(
                    asof=_parse_date(row["asof"]),
                    symbol=row["symbol"].strip(),
                    expiry=_parse_date(row["expiry"]),
                    strike=float(row["strike"]),
                    right=row["right"].strip().upper(),
                    bid=float(row["bid"]),
                    ask=float(row["ask"]),
                    delta=float(row["delta"]),
                    iv=float(row["iv"]),
                    underlying=float(row["underlying"]),
                    r=float(row["r"]),
                )
            )
    return out


def _row_issues(q: OptionQuote) -> list[str]:
    issues: list[str] = []
    if q.bid > q.ask:
        issues.append("bid_gt_ask")
    if q.right == "P":
        if not (-1.0 <= q.delta <= 0.0):
            issues.append("delta_put_out_of_range")
    elif q.right == "C":
        if not (0.0 <= q.delta <= 1.0):
            issues.append("delta_call_out_of_range")
    else:
        issues.append("right_invalid")
    # strict (0,5)
    if not (0.0 < q.iv < 5.0):
        issues.append("iv_out_of_range")
    return issues


def _sample_quotes(quotes: list[OptionQuote], *, days: int = 5, strikes_per_day: int = 100, seed: int = 42) -> list[OptionQuote]:
    # Deterministic: pick earliest N unique days.
    uniq_days = sorted({q.asof for q in quotes})
    pick_days = uniq_days[:days]
    out: list[OptionQuote] = []
    for d in pick_days:
        day_quotes = [q for q in quotes if q.asof == d]
        strikes = sorted({q.strike for q in day_quotes})
        rng = random.Random(seed + d.toordinal())
        if len(strikes) > strikes_per_day:
            chosen = set(rng.sample(strikes, strikes_per_day))
        else:
            chosen = set(strikes)
        out.extend([q for q in day_quotes if q.strike in chosen])
    return out


def _parity_error(call_mid: float, put_mid: float, S: float, K: float, r: float, T_years: float) -> float:
    return abs((call_mid - put_mid) - (S - K * math.exp(-r * T_years)))


def run_quality_checks(
    quotes: list[OptionQuote],
    *,
    days: int = 5,
    strikes_per_day: int = 100,
    seed: int = 42,
    parity_threshold: float = 0.50,
) -> dict[str, Any]:
    sampled = _sample_quotes(quotes, days=days, strikes_per_day=strikes_per_day, seed=seed)

    excluded: list[tuple[OptionQuote, list[str]]] = []
    kept: list[OptionQuote] = []
    for q in sampled:
        issues = _row_issues(q)
        if issues:
            excluded.append((q, issues))
        else:
            kept.append(q)

    excluded_by_reason: dict[str, int] = {}
    for _, issues in excluded:
        for code in issues:
            excluded_by_reason[code] = excluded_by_reason.get(code, 0) + 1

    # Put-call parity alerts (do not exclude; alert-only per canon)
    # Build lookup on kept quotes only (after exclusions)
    by_key: dict[tuple[date, str, date, float], dict[str, OptionQuote]] = {}
    for q in kept:
        key = (q.asof, q.symbol, q.expiry, q.strike)
        by_key.setdefault(key, {})[q.right] = q

    parity_alerts: list[dict[str, Any]] = []
    max_err = 0.0
    for (asof, sym, exp, strike), legs in by_key.items():
        c = legs.get("C")
        p = legs.get("P")
        if c is None or p is None:
            continue
        T = max((exp - asof).days, 0) / 365.0
        err = _parity_error(c.mid, p.mid, c.underlying, strike, c.r, T)
        max_err = max(max_err, err)
        if err > parity_threshold:
            parity_alerts.append({
                "asof": asof.isoformat(),
                "symbol": sym,
                "expiry": exp.isoformat(),
                "strike": strike,
                "error": round(err, 6),
            })

    return {
        "sample": {"days": days, "strikes_per_day": strikes_per_day, "seed": seed},
        "total_rows_in": len(quotes),
        "rows_sampled": len(sampled),
        "rows_kept": len(kept),
        "rows_excluded": len(excluded),
        "excluded_by_reason": dict(sorted(excluded_by_reason.items())),
        "parity": {
            "threshold": parity_threshold,
            "alerts": parity_alerts,
            "alerts_count": len(parity_alerts),
            "max_error": round(max_err, 6),
        },
    }


def write_report(report: dict[str, Any], *, outdir: Path) -> tuple[Path, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    js = outdir / "options_chain_quality_report.json"
    md = outdir / "options_chain_quality_report.md"
    js.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines: list[str] = []
    lines.append("# F1-T3 Options Chain Quality Report\n")
    s = report["sample"]
    lines.append(f"- sample: days={s['days']} strikes_per_day={s['strikes_per_day']} seed={s['seed']}\n")
    lines.append(f"- rows: in={report['total_rows_in']} sampled={report['rows_sampled']} kept={report['rows_kept']} excluded={report['rows_excluded']}\n")
    lines.append("\n## Exclusions (row-level)\n")
    if report["excluded_by_reason"]:
        for k,v in report["excluded_by_reason"].items():
            lines.append(f"- {k}: {v}\n")
    else:
        lines.append("- none\n")
    lines.append("\n## Put-Call Parity Alerts (alert-only)\n")
    parity = report["parity"]
    lines.append(f"- threshold: {parity['threshold']}\n")
    lines.append(f"- alerts_count: {parity['alerts_count']}\n")
    lines.append(f"- max_error: {parity['max_error']}\n")
    md.write_text("".join(lines), encoding="utf-8")
    return js, md
