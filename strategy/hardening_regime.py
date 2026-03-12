from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List


def leakage_guard_ok(*, feature_ts: Iterable[int], label_ts: Iterable[int], train_end_ts: int) -> bool:
    features = [int(x) for x in feature_ts]
    labels = [int(x) for x in label_ts]

    if any(ts > int(train_end_ts) for ts in features):
        return False
    if any(ts <= int(train_end_ts) for ts in labels):
        return False
    return True


def hmm_event_oos_qualification(events: Iterable[Dict[str, float]]) -> Dict[str, object]:
    """Event-based qualification for HMM (F2 addendum).

    Expected input rows contain:
      - family: str (e.g. vix, correlation, credit)
      - hmm_lead_days: float
      - xgb_lead_days: float
      - hmm_false_positive: 0/1 (optional)
      - xgb_false_positive: 0/1 (optional)

    Pass condition: HMM adds value in >=2/3 families and does not worsen FP in those families.
    """
    grouped: Dict[str, List[Dict[str, float]]] = defaultdict(list)
    for row in events:
        fam = str(row.get("family", "")).strip().lower() or "unknown"
        grouped[fam].append(row)

    family_scores: Dict[str, bool] = {}
    for fam, rows in grouped.items():
        hmm_lead = sum(float(r.get("hmm_lead_days", 0.0)) for r in rows) / len(rows)
        xgb_lead = sum(float(r.get("xgb_lead_days", 0.0)) for r in rows) / len(rows)

        hmm_fp = sum(float(r.get("hmm_false_positive", 0.0)) for r in rows)
        xgb_fp = sum(float(r.get("xgb_false_positive", 0.0)) for r in rows)

        adds_value = hmm_lead >= xgb_lead
        no_fp_worse = hmm_fp <= xgb_fp
        family_scores[fam] = bool(adds_value and no_fp_worse)

    families_total = len(family_scores)
    families_pass = sum(1 for ok in family_scores.values() if ok)
    required = 2 if families_total >= 3 else max(1, families_total)
    qualified = families_pass >= required

    return {
        "qualified": qualified,
        "families_total": families_total,
        "families_pass": families_pass,
        "required_min": required,
        "family_scores": family_scores,
    }


def correlation_breakdown_flag(*, corr_zscore: float, threshold: float = -2.0) -> bool:
    return float(corr_zscore) <= float(threshold)
