from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "canonical" / "operational_contract.toml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract(pattern: str, text: str, label: str, errors: list[str], cast=float):
    m = re.search(pattern, text, flags=re.MULTILINE)
    if not m:
        errors.append(f"missing pattern for {label}: {pattern}")
        return None
    try:
        return cast(m.group(1))
    except Exception as exc:  # pragma: no cover
        errors.append(f"invalid value for {label}: {exc}")
        return None


def _must_contain(path: Path, pattern: str, errors: list[str]) -> None:
    text = _read(path)
    if re.search(pattern, text, flags=re.MULTILINE) is None:
        errors.append(f"{path.as_posix()} missing required pattern: {pattern}")


def _must_not_contain(path: Path, pattern: str, errors: list[str]) -> None:
    text = _read(path)
    if re.search(pattern, text, flags=re.MULTILINE):
        errors.append(f"{path.as_posix()} contains forbidden pattern: {pattern}")


def validate_contract() -> list[str]:
    errors: list[str] = []
    if not CONTRACT_PATH.exists():
        return [f"missing contract file: {CONTRACT_PATH.as_posix()}"]

    contract = tomllib.loads(_read(CONTRACT_PATH))
    score = contract["score"]
    filters = contract["filters"]

    scoring_py = _read(ROOT / "strategy" / "scoring.py")
    scanner_py = _read(ROOT / "strategy" / "opportunity_scanner.py")
    models_py = _read(ROOT / "api" / "models.py")

    runtime_spread = _extract(r"if bid_ask_spread_pct > ([0-9.]+):", scoring_py, "spread_pct_max", errors)
    runtime_oi = _extract(r"if open_interest < ([0-9]+):", scoring_py, "oi_hard_min", errors, cast=int)
    runtime_ivr = _extract(r"if ivr < ([0-9.]+):", scoring_py, "ivr_min", errors)
    runtime_score_min = _extract(r"if score < ([0-9.]+):", scoring_py, "presentation_min", errors)

    hard_min_dte = _extract(r"HARD_MIN_DTE:\s*int\s*=\s*([0-9]+)", scanner_py, "dte_hard_min", errors, cast=int)
    hard_max_dte = _extract(r"HARD_MAX_DTE:\s*int\s*=\s*([0-9]+)", scanner_py, "dte_hard_max", errors, cast=int)
    pref_min_dte = _extract(r"DEFAULT_MIN_DTE:\s*int\s*=\s*([0-9]+)", scanner_py, "dte_preferred_min", errors, cast=int)
    pref_max_dte = _extract(r"DEFAULT_MAX_DTE:\s*int\s*=\s*([0-9]+)", scanner_py, "dte_preferred_max", errors, cast=int)
    scanner_oi_min = _extract(r"DEFAULT_MIN_OI:\s*int\s*=\s*([0-9]+)", scanner_py, "oi_hard_min", errors, cast=int)
    scanner_oi_strict = _extract(r"PAPER_LIVE_MIN_OI:\s*int\s*=\s*([0-9]+)", scanner_py, "oi_strict_min_paper_live", errors, cast=int)

    model_min_score = _extract(
        r"min_score:\s*float\s*=\s*Field\(default=([0-9.]+)",
        models_py,
        "api_models.min_score",
        errors,
    )

    checks = [
        ("filters.spread_pct_max", runtime_spread, filters["spread_pct_max"]),
        ("filters.oi_hard_min", runtime_oi, filters["oi_hard_min"]),
        ("filters.ivr_min", runtime_ivr, filters["ivr_min"]),
        ("score.presentation_min", runtime_score_min, score["presentation_min"]),
        ("filters.dte_hard_min", hard_min_dte, filters["dte_hard_min"]),
        ("filters.dte_hard_max", hard_max_dte, filters["dte_hard_max"]),
        ("filters.dte_preferred_min", pref_min_dte, filters["dte_preferred_min"]),
        ("filters.dte_preferred_max", pref_max_dte, filters["dte_preferred_max"]),
        ("filters.oi_hard_min(scanner)", scanner_oi_min, filters["oi_hard_min"]),
        ("filters.oi_strict_min_paper_live", scanner_oi_strict, filters["oi_strict_min_paper_live"]),
        ("score.presentation_min(api_models)", model_min_score, score["presentation_min"]),
    ]
    for label, actual, expected in checks:
        if actual is None:
            continue
        if float(actual) != float(expected):
            errors.append(f"contract mismatch {label}: runtime={actual} expected={expected}")

    project_doc = ROOT / "docs" / "PROJECT_OPZ_COMPLETE_V2.md"
    tutorial_doc = ROOT / "docs" / "guide" / "tutorial_operativo.md"
    lifecycle_doc = ROOT / "docs" / "guide" / "trade_lifecycle.html"
    lineage_doc = ROOT / "docs" / "data_lineage.md"

    _must_contain(project_doc, r"docs/canonical/operational_contract\.toml", errors)
    _must_contain(tutorial_doc, r"Score\*\*.*0 a 100", errors)
    _must_contain(tutorial_doc, r"Score\*\*.*(?:>=|≥|almeno)\s*60", errors)
    _must_not_contain(tutorial_doc, r"da 0 a 1(?:[^0-9]|$)", errors)
    _must_not_contain(tutorial_doc, r"sopra 0\.6", errors)

    _must_contain(lifecycle_doc, r"Score &#x2265; 60", errors)
    _must_not_contain(lifecycle_doc, r"soglia score 6\.5", errors)
    _must_not_contain(lifecycle_doc, r"soglia 6\.5", errors)
    _must_not_contain(lifecycle_doc, r"Score &#x2265; 6\.5", errors)

    _must_contain(lineage_doc, r"docs/canonical/operational_contract\.toml", errors)

    return errors


def main() -> int:
    errs = validate_contract()
    if errs:
        print("DOCS_CONTRACT_CHECK FAIL")
        enc = sys.stdout.encoding or "utf-8"
        for err in errs:
            safe = err.encode(enc, errors="backslashreplace").decode(enc, errors="replace")
            print(f"- {safe}")
        return 1
    print("DOCS_CONTRACT_CHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
