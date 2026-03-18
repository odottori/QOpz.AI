"""Tests for Walk-Forward Analysis — Iron Condor."""
import pytest
from datetime import date

from scripts.wfa_iron_condor import (
    ICFoldSpec,
    ICFoldMetrics,
    ICWFASummary,
    build_ic_fold_specs,
    load_ic_returns_csv,
    run_wfa_iron_condor,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_rows(start_year: int = 2010, n_years: int = 14) -> list[tuple[date, float]]:
    """Synthetic daily returns: slightly positive with noise."""
    import math
    rows = []
    for yr in range(start_year, start_year + n_years):
        for day in range(252):
            d = date(yr, 1, 1)
            # deterministic small positive return
            ret = 0.002 * math.sin(day * 0.1) + 0.0005
            rows.append((d.replace(month=min(12, day // 21 + 1), day=max(1, (day % 21) + 1)), ret))
    return rows


def _make_simple_rows(years: list[int], ret_per_year: dict[int, float] | None = None) -> list[tuple[date, float]]:
    """Make exactly 12 rows per year (one per month)."""
    if ret_per_year is None:
        ret_per_year = {}
    rows = []
    for yr in years:
        r = ret_per_year.get(yr, 0.005)
        for month in range(1, 13):
            rows.append((date(yr, month, 1), r))
    return rows


# ── ICFoldSpec builder ────────────────────────────────────────────────────────

class TestBuildICFoldSpecs:
    def test_returns_correct_count(self):
        specs = build_ic_fold_specs(start_year=2010, is_years=3, n_folds=5)
        assert len(specs) == 5

    def test_fold_numbering(self):
        specs = build_ic_fold_specs(start_year=2010, is_years=3, n_folds=3)
        assert [s.fold for s in specs] == [1, 2, 3]

    def test_is_window(self):
        specs = build_ic_fold_specs(start_year=2010, is_years=3, n_folds=1)
        s = specs[0]
        assert s.is_start_year == 2010
        assert s.is_end_year == 2012

    def test_oos_year_is_after_is(self):
        specs = build_ic_fold_specs(start_year=2010, is_years=3, n_folds=3)
        for s in specs:
            assert s.oos_year == s.is_end_year + 1

    def test_sliding_window(self):
        specs = build_ic_fold_specs(start_year=2010, is_years=3, n_folds=3)
        assert specs[0].is_start_year == 2010
        assert specs[1].is_start_year == 2011
        assert specs[2].is_start_year == 2012

    def test_frozen_dataclass(self):
        specs = build_ic_fold_specs()
        with pytest.raises(Exception):
            specs[0].fold = 99


# ── run_wfa_iron_condor ───────────────────────────────────────────────────────

class TestRunWFAIronCondor:
    def test_returns_summary_and_curve(self):
        rows = _make_simple_rows(list(range(2010, 2024)))
        summary, curve = run_wfa_iron_condor(rows, n_folds=5, is_years=3)
        assert isinstance(summary, ICWFASummary)
        assert isinstance(curve, list)

    def test_n_folds_matches(self):
        rows = _make_simple_rows(list(range(2010, 2024)))
        summary, _ = run_wfa_iron_condor(rows, n_folds=5, is_years=3)
        assert summary.n_folds == 5
        assert len(summary.folds) == 5

    def test_oos_curve_non_empty(self):
        rows = _make_simple_rows(list(range(2010, 2024)))
        _, curve = run_wfa_iron_condor(rows, n_folds=5, is_years=3)
        assert len(curve) > 0

    def test_oos_curve_starts_near_one(self):
        rows = _make_simple_rows(list(range(2010, 2024)))
        _, curve = run_wfa_iron_condor(rows, n_folds=5, is_years=3)
        # first equity value should be close to 1.0 (small drift from first trade)
        assert 0.5 < curve[0][1] < 2.0

    def test_median_sharpe_oos_is_finite(self):
        import math
        rows = _make_rows(start_year=2010, n_years=14)
        summary, _ = run_wfa_iron_condor(rows, n_folds=5, is_years=3)
        assert math.isfinite(summary.median_sharpe_oos)

    def test_deflation_is_ratio(self):
        rows = _make_simple_rows(list(range(2010, 2024)))
        summary, _ = run_wfa_iron_condor(rows, n_folds=5, is_years=3)
        # deflation = oos_sharpe / is_sharpe — finite float
        assert isinstance(summary.deflation, float)

    def test_max_dd_oos_non_negative(self):
        rows = _make_simple_rows(list(range(2010, 2024)))
        summary, _ = run_wfa_iron_condor(rows, n_folds=5, is_years=3)
        assert summary.max_dd_oos >= 0.0

    def test_median_win_rate_in_range(self):
        rows = _make_simple_rows(list(range(2010, 2024)))
        summary, _ = run_wfa_iron_condor(rows, n_folds=5, is_years=3)
        assert 0.0 <= summary.median_win_rate_oos <= 1.0

    def test_custom_candidates(self):
        rows = _make_simple_rows(list(range(2010, 2024)))
        summary, _ = run_wfa_iron_condor(
            rows,
            n_folds=3,
            is_years=3,
            delta_wing_candidates=[0.16],
            wing_width_candidates=[5.0],
        )
        for fold in summary.folds:
            assert fold.chosen_delta_wing == pytest.approx(0.16)
            assert fold.chosen_wing_width == pytest.approx(5.0)

    def test_insufficient_data_raises(self):
        # Only 2 years of data → can't satisfy 3 IS + 1 OOS
        rows = _make_simple_rows([2020, 2021])
        with pytest.raises(ValueError, match="insufficient data"):
            run_wfa_iron_condor(rows, n_folds=1, is_years=3)

    def test_fold_metrics_fields(self):
        rows = _make_simple_rows(list(range(2010, 2024)))
        summary, _ = run_wfa_iron_condor(rows, n_folds=3, is_years=3)
        m = summary.folds[0]
        assert isinstance(m.fold, int)
        assert isinstance(m.is_years, str)
        assert isinstance(m.oos_year, int)
        assert isinstance(m.chosen_delta_wing, float)
        assert isinstance(m.chosen_wing_width, float)
        assert isinstance(m.sharpe_is, float)
        assert isinstance(m.sharpe_oos, float)
        assert isinstance(m.maxdd_oos, float)
        assert isinstance(m.winrate_oos, float)

    def test_oos_curve_dates_ordered(self):
        rows = _make_simple_rows(list(range(2010, 2024)))
        _, curve = run_wfa_iron_condor(rows, n_folds=5, is_years=3)
        dates = [d for d, _ in curve]
        assert dates == sorted(dates)

    def test_worst_oos_dd_equals_max_dd_oos(self):
        rows = _make_simple_rows(list(range(2010, 2024)))
        summary, _ = run_wfa_iron_condor(rows, n_folds=5, is_years=3)
        assert summary.worst_oos_dd == pytest.approx(summary.max_dd_oos)
