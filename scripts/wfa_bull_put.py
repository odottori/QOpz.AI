from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from scripts.metrics import annualized_sharpe, equity_curve, max_drawdown, win_rate


@dataclass(frozen=True)
class FoldSpec:
    fold: int
    is_start_year: int
    is_end_year: int
    oos_year: int


@dataclass(frozen=True)
class FoldMetrics:
    fold: int
    is_years: str
    oos_year: int
    chosen_scalar: float
    sharpe_is: float
    sharpe_oos: float
    maxdd_oos: float
    winrate_oos: float


@dataclass(frozen=True)
class WFASummary:
    n_folds: int
    median_sharpe_oos: float
    max_dd_oos: float
    median_win_rate_oos: float
    deflation: float
    worst_oos_dd: float
    folds: list[FoldMetrics]


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    m = len(s) // 2
    return float(s[m]) if len(s) % 2 == 1 else float((s[m - 1] + s[m]) / 2)


def load_returns_csv(path: Path) -> list[tuple[date, float]]:
    rows: list[tuple[date, float]] = []
    with path.open("r", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            d = date.fromisoformat(row["date"])
            ret = float(row["ret"])
            rows.append((d, ret))
    return rows


def build_fold_specs(
    start_year: int = 2010,
    is_years: int = 3,
    oos_years: int = 1,
    n_folds: int = 10,
) -> list[FoldSpec]:
    # Sliding window by 1 year. With 3y IS + 1y OOS and start_year=2010,
    # fold0 IS=2010-2012, OOS=2013. n_folds=10 ends at OOS=2022.
    specs: list[FoldSpec] = []
    for i in range(n_folds):
        is_start = start_year + i
        is_end = is_start + is_years - 1
        oos_y = is_end + 1  # single OOS year
        specs.append(FoldSpec(fold=i + 1, is_start_year=is_start, is_end_year=is_end, oos_year=oos_y))
    return specs


def _slice_year(rows: list[tuple[date, float]], y0: int, y1: int) -> list[float]:
    return [ret for d, ret in rows if y0 <= d.year <= y1]


def _slice_single_year(rows: list[tuple[date, float]], y: int) -> list[float]:
    return [ret for d, ret in rows if d.year == y]


def _fit_scalar_is(is_rets: list[float], candidates: list[float]) -> float:
    # Choose scalar maximizing Sharpe on IS with a mild max-drawdown constraint.
    best_s = candidates[0]
    best_obj = -1e9
    for s in candidates:
        r = [s * x for x in is_rets]
        eq = equity_curve(r)
        mdd = max_drawdown(eq)
        if mdd > 0.15:
            continue
        sh = annualized_sharpe(r)
        obj = sh
        if obj > best_obj:
            best_obj = obj
            best_s = s
    return float(best_s)


def run_wfa_bull_put(
    rows: list[tuple[date, float]],
    n_folds: int = 10,
    is_years: int = 3,
    candidates: list[float] | None = None,
) -> tuple[WFASummary, list[tuple[date, float]]]:
    if candidates is None:
        candidates = [0.75, 1.0, 1.25]

    specs = build_fold_specs(start_year=2010, is_years=is_years, oos_years=1, n_folds=n_folds)
    fold_metrics: list[FoldMetrics] = []

    # Concatenated OOS equity curve (date, equity)
    oos_points: list[tuple[date, float]] = []
    eq = 1.0
    for spec in specs:
        is_rets = _slice_year(rows, spec.is_start_year, spec.is_end_year)
        oos_rets_raw = _slice_single_year(rows, spec.oos_year)
        if not is_rets or not oos_rets_raw:
            raise ValueError(f"insufficient data for fold {spec.fold}")

        s = _fit_scalar_is(is_rets, candidates)
        is_scaled = [s * x for x in is_rets]
        oos_scaled = [s * x for x in oos_rets_raw]

        sh_is = annualized_sharpe(is_scaled)
        sh_oos = annualized_sharpe(oos_scaled)
        eq_oos = equity_curve(oos_scaled, start=1.0)
        mdd_oos = max_drawdown(eq_oos)
        wr_oos = win_rate(oos_scaled)

        fold_metrics.append(
            FoldMetrics(
                fold=spec.fold,
                is_years=f"{spec.is_start_year}-{spec.is_end_year}",
                oos_year=spec.oos_year,
                chosen_scalar=s,
                sharpe_is=sh_is,
                sharpe_oos=sh_oos,
                maxdd_oos=mdd_oos,
                winrate_oos=wr_oos,
            )
        )

        # append equity points for this OOS year
        # use actual dates from rows for that year in order
        for d, r in [(d, ret) for d, ret in rows if d.year == spec.oos_year]:
            eq *= (1.0 + s * r)
            oos_points.append((d, eq))

    oos_sharpes = [m.sharpe_oos for m in fold_metrics]
    is_sharpes = [m.sharpe_is for m in fold_metrics]
    oos_win = [m.winrate_oos for m in fold_metrics]
    oos_dd = [m.maxdd_oos for m in fold_metrics]

    med_oos = _median(oos_sharpes)
    med_is = _median(is_sharpes)
    deflation = (med_oos / med_is) if abs(med_is) > 1e-12 else 0.0

    summary = WFASummary(
        n_folds=n_folds,
        median_sharpe_oos=med_oos,
        max_dd_oos=max(oos_dd) if oos_dd else 0.0,
        median_win_rate_oos=_median(oos_win),
        deflation=deflation,
        worst_oos_dd=max(oos_dd) if oos_dd else 0.0,
        folds=fold_metrics,
    )
    return summary, oos_points
