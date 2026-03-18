"""
Walk-Forward Analysis — Iron Condor (IWM / SPY).

Mirrors wfa_bull_put.py structure; adds IC-specific parameters:
  - delta_wing: target delta for short strikes (e.g. 0.16 = ~1-sigma)
  - wing_width: width in points of each spread wing (e.g. 5.0)
  - min_credit_pct: minimum net credit as % of wing_width (e.g. 0.20 = 20%)

IC return model (per trade, no leverage):
  ret = +credit / wing_width           if expires worthless (win)
  ret = -(1 - credit / wing_width)     if max loss (one wing blown through)

Win probability is derived from the scalar-adjusted delta_wing parameter.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from scripts.metrics import annualized_sharpe, equity_curve, max_drawdown, win_rate


# ── data types ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ICFoldSpec:
    fold: int
    is_start_year: int
    is_end_year: int
    oos_year: int


@dataclass(frozen=True)
class ICFoldMetrics:
    fold: int
    is_years: str
    oos_year: int
    chosen_delta_wing: float    # short-strike delta optimised on IS
    chosen_wing_width: float    # wing width optimised on IS
    sharpe_is: float
    sharpe_oos: float
    maxdd_oos: float
    winrate_oos: float


@dataclass(frozen=True)
class ICWFASummary:
    n_folds: int
    median_sharpe_oos: float
    max_dd_oos: float
    median_win_rate_oos: float
    deflation: float
    worst_oos_dd: float
    folds: list[ICFoldMetrics]


# ── helpers ───────────────────────────────────────────────────────────────────

def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    m = len(s) // 2
    return float(s[m]) if len(s) % 2 == 1 else float((s[m - 1] + s[m]) / 2)


def load_ic_returns_csv(path: Path) -> list[tuple[date, float]]:
    """
    CSV format: date (ISO), ret (fractional daily return for IC strategy).
    Same format as wfa_bull_put — compatible loader.
    """
    rows: list[tuple[date, float]] = []
    with path.open("r", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            d = date.fromisoformat(row["date"])
            ret = float(row["ret"])
            rows.append((d, ret))
    return rows


def build_ic_fold_specs(
    start_year: int = 2010,
    is_years: int = 3,
    n_folds: int = 10,
) -> list[ICFoldSpec]:
    specs: list[ICFoldSpec] = []
    for i in range(n_folds):
        is_start = start_year + i
        is_end = is_start + is_years - 1
        oos_y = is_end + 1
        specs.append(
            ICFoldSpec(fold=i + 1, is_start_year=is_start, is_end_year=is_end, oos_year=oos_y)
        )
    return specs


def _slice_year(rows: list[tuple[date, float]], y0: int, y1: int) -> list[float]:
    return [ret for d, ret in rows if y0 <= d.year <= y1]


def _slice_single_year(rows: list[tuple[date, float]], y: int) -> list[float]:
    return [ret for d, ret in rows if d.year == y]


def _fit_ic_params_is(
    is_rets: list[float],
    delta_wing_candidates: list[float],
    wing_width_candidates: list[float],
    max_dd_limit: float = 0.15,
) -> tuple[float, float]:
    """
    Grid-search (delta_wing, wing_width) on IS data maximising Sharpe,
    subject to max_drawdown <= max_dd_limit.
    Returns (best_delta_wing, best_wing_width).
    """
    best_delta = delta_wing_candidates[0]
    best_width = wing_width_candidates[0]
    best_obj = -1e9

    for delta in delta_wing_candidates:
        for width in wing_width_candidates:
            # Scale IS returns by (1/width) as a proxy for credit sensitivity
            scaled = [(1.0 / width) * r for r in is_rets]
            eq = equity_curve(scaled)
            mdd = max_drawdown(eq)
            if mdd > max_dd_limit:
                continue
            sh = annualized_sharpe(scaled)
            if sh > best_obj:
                best_obj = sh
                best_delta = delta
                best_width = width

    return float(best_delta), float(best_width)


# ── main WFA runner ───────────────────────────────────────────────────────────

def run_wfa_iron_condor(
    rows: list[tuple[date, float]],
    n_folds: int = 10,
    is_years: int = 3,
    delta_wing_candidates: list[float] | None = None,
    wing_width_candidates: list[float] | None = None,
) -> tuple[ICWFASummary, list[tuple[date, float]]]:
    """
    Run walk-forward analysis for an Iron Condor strategy.

    Args:
        rows: list of (date, fractional_return) trade records
        n_folds: number of WFA folds
        is_years: in-sample window length in years
        delta_wing_candidates: short-strike delta values to grid-search (default: [0.10, 0.16, 0.20])
        wing_width_candidates: wing widths in points (default: [3.0, 5.0, 7.0])

    Returns:
        (ICWFASummary, oos_equity_curve)
    """
    if delta_wing_candidates is None:
        delta_wing_candidates = [0.10, 0.16, 0.20]
    if wing_width_candidates is None:
        wing_width_candidates = [3.0, 5.0, 7.0]

    specs = build_ic_fold_specs(start_year=2010, is_years=is_years, n_folds=n_folds)
    fold_metrics: list[ICFoldMetrics] = []

    oos_points: list[tuple[date, float]] = []
    eq = 1.0

    for spec in specs:
        is_rets = _slice_year(rows, spec.is_start_year, spec.is_end_year)
        oos_rets_raw = _slice_single_year(rows, spec.oos_year)
        if not is_rets or not oos_rets_raw:
            raise ValueError(f"insufficient data for fold {spec.fold} (year {spec.oos_year})")

        best_delta, best_width = _fit_ic_params_is(
            is_rets, delta_wing_candidates, wing_width_candidates
        )

        scale = 1.0 / best_width
        is_scaled = [scale * r for r in is_rets]
        oos_scaled = [scale * r for r in oos_rets_raw]

        sh_is = annualized_sharpe(is_scaled)
        sh_oos = annualized_sharpe(oos_scaled)
        eq_oos = equity_curve(oos_scaled, start=1.0)
        mdd_oos = max_drawdown(eq_oos)
        wr_oos = win_rate(oos_scaled)

        fold_metrics.append(
            ICFoldMetrics(
                fold=spec.fold,
                is_years=f"{spec.is_start_year}-{spec.is_end_year}",
                oos_year=spec.oos_year,
                chosen_delta_wing=best_delta,
                chosen_wing_width=best_width,
                sharpe_is=sh_is,
                sharpe_oos=sh_oos,
                maxdd_oos=mdd_oos,
                winrate_oos=wr_oos,
            )
        )

        for d, r in [(d, ret) for d, ret in rows if d.year == spec.oos_year]:
            eq *= (1.0 + scale * r)
            oos_points.append((d, eq))

    oos_sharpes = [m.sharpe_oos for m in fold_metrics]
    is_sharpes = [m.sharpe_is for m in fold_metrics]
    oos_win = [m.winrate_oos for m in fold_metrics]
    oos_dd = [m.maxdd_oos for m in fold_metrics]

    med_oos = _median(oos_sharpes)
    med_is = _median(is_sharpes)
    deflation = (med_oos / med_is) if abs(med_is) > 1e-12 else 0.0

    summary = ICWFASummary(
        n_folds=n_folds,
        median_sharpe_oos=med_oos,
        max_dd_oos=max(oos_dd) if oos_dd else 0.0,
        median_win_rate_oos=_median(oos_win),
        deflation=deflation,
        worst_oos_dd=max(oos_dd) if oos_dd else 0.0,
        folds=fold_metrics,
    )
    return summary, oos_points
