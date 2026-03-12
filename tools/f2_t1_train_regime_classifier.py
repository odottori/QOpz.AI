from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

# Ensure repo root is importable when running as "py tools\..."
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import regime_classifier as rc  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="F2-T1 — Regime classifier (offline, deterministic)")
    p.add_argument("--csv", type=str, default=str(ROOT / "samples" / "regime_features_2010_2014.csv"))
    p.add_argument("--model-out", type=str, default=str(ROOT / "data" / "regime_model_f2_t1.json"))
    p.add_argument("--outdir", type=str, default=str(ROOT / "reports"))
    p.add_argument("--oos-year", type=int, default=2014)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = rc.load_dataset_csv(args.csv)

    features = ["vix", "vix3m", "ret_5d"]
    train_rows, oos_rows = rc.split_by_year(rows, train_years=range(2010, 2014), oos_year=args.oos_year)

    # calibration: last training year (2013)
    cal_rows = [r for r in train_rows if r["date"].year == 2013]
    base_rows = [r for r in train_rows if r["date"].year != 2013]

    X_train = rc.featurize(base_rows, features)
    y_train = rc.labels(base_rows)

    model = rc.train_gaussian_nb(X_train, y_train, features)

    # Fit Platt scaling on 2013 slice
    X_cal = rc.featurize(cal_rows, features)
    y_cal = rc.labels(cal_rows)
    if X_cal:
        model = rc.fit_platt_scaling(model, X_cal, y_cal)

    # Evaluate OOS
    X_oos = rc.featurize(oos_rows, features)
    y_oos = rc.labels(oos_rows)
    proba = rc.predict_proba(model, X_oos)
    y_pred = rc.predict(model, X_oos)

    acc = rc.accuracy(y_oos, y_pred)
    brier = rc.brier_score(y_oos, proba)
    cm = rc.confusion_matrix(y_oos, y_pred)
    importance = rc.fisher_feature_importance(X_train + X_cal, y_train + y_cal, features)

    # outputs
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "f2_t1_confusion_matrix.json").write_text(json.dumps(cm, indent=2, sort_keys=True), encoding="utf-8")
    (outdir / "f2_t1_metrics.json").write_text(json.dumps({"accuracy": acc, "brier": brier}, indent=2), encoding="utf-8")
    (outdir / "f2_t1_feature_importance.json").write_text(json.dumps(importance, indent=2), encoding="utf-8")

    rc.save_model(model, args.model_out)

    top3 = [f for f, _ in importance[:3]]
    print(f"OK F2-T1 accuracy={acc:.3f} brier={brier:.3f} top3={top3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
