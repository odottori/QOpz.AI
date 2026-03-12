from __future__ import annotations

from pathlib import Path

from scripts import progress_report


def test_phase_plan_parsing_counts() -> None:
    # Canonical plan lives in canonici/02_TEST.md
    plan = progress_report._load_phase_plan_tasks(Path(".canonici/02_TEST.md"))
    assert plan["F1"]
    assert plan["F2"]
    assert plan["F3"]
    assert plan["F4"]
    assert plan["F5"]
    assert plan["F6"]
    # Ensure expected minimum task counts are stable
    assert len(plan["F5"]) >= 3
    assert len(plan["F6"]) >= 3
