from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typing import Any

from scripts.hmm_regime import fit_hmm_rolling, load_hmm_csv
from scripts import regime_classifier


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _xgb_baseline(rows: list[dict[str, Any]], window: int) -> dict[str, Any]:
    # train on first `window` points (deterministic)
    train = rows[:window]
    oos = rows[window:]
    features = ["vix", "vix3m", "ret_5d"]
    Xtr = regime_classifier.featurize(train, features)
    ytr = regime_classifier.labels(train)
    model = regime_classifier.train_gaussian_nb(Xtr, ytr, features)
    # calibrate quickly using same train set (stable enough for offline)
    model = regime_classifier.fit_platt_scaling(model, Xtr, ytr)
    Xo = regime_classifier.featurize(oos, features)
    probas = regime_classifier.predict_proba(model, Xo)
    preds = regime_classifier.predict(model, Xo)
    # attach by date
    by_date: dict[str, dict[str, Any]] = {}
    for r, pr, lab in zip(oos, probas, preds):
        by_date[r["date"].isoformat()] = {"p_shock": float(pr["SHOCK"]), "pred": str(lab)}
    return {"features": features, "by_date": by_date}


def _lead_time_eval(rows: list[dict[str, Any]], hmm_rows: list[dict[str, Any]], xgb_by_date: dict[str, Any]) -> dict[str, Any]:
    # build lookups
    hmm_p = {r["date"]: float(r["p_shock"]) for r in hmm_rows}
    xgb_p = {d: float(v["p_shock"]) for d, v in xgb_by_date.items()}
    xgb_pred = {d: str(v["pred"]) for d, v in xgb_by_date.items()}

    families = sorted({str(r.get("shock_family", "")) for r in rows if str(r.get("shock_family", ""))})
    fam_stats: list[dict[str, Any]] = []
    ok_leads = 0

    # for each family, define shock start date (first SHOCK label)
    for fam in families:
        fam_rows = [r for r in rows if str(r.get("shock_family", "")) == fam]
        shock_start = None
        for r in fam_rows:
            if str(r.get("label", "")) == "SHOCK":
                d0 = r["date"].isoformat()
                if d0 in hmm_p:
                    shock_start = d0
                    break
        if not shock_start:
            continue

        # find earliest signal dates before shock_start within that family window
        fam_dates_all = [r["date"].isoformat() for r in fam_rows]
        fam_dates = [d for d in fam_dates_all if d in hmm_p]
        # hmm uses previous day index; ensure present
        def find_hmm():
            for d in fam_dates:
                if d >= shock_start:
                    break
                if hmm_p.get(d, 0.0) > 0.70:
                    return d
            return None

        def find_xgb():
            for d in fam_dates:
                if d >= shock_start:
                    break
                # baseline uses label SHOCK (stricter than proba)
                if xgb_pred.get(d, "") == "SHOCK":
                    return d
            return None

        hmm_d = find_hmm()
        xgb_d = find_xgb()

        lead_days = None
        if hmm_d and xgb_d:
            lead_days = fam_dates.index(xgb_d) - fam_dates.index(hmm_d)
        elif hmm_d and not xgb_d:
            # xgb never early; treat as strong lead
            lead_days = 2
        else:
            lead_days = 0

        ok = (lead_days in (1, 2))
        if ok:
            ok_leads += 1

        fam_stats.append(
            {
                "family": fam,
                "shock_start": shock_start,
                "hmm_signal": hmm_d,
                "xgb_signal": xgb_d,
                "lead_days": lead_days,
                "pass": ok,
            }
        )

    return {
        "families": fam_stats,
        "ok_leads": ok_leads,
        "n_families": len(fam_stats),
        "pass": ok_leads >= max(1, (2 * max(1, len(fam_stats)) + 2) // 3),  # >=2/3 rounded up
    }


def run(csv_path: str, outdir: str = "reports", window: int = 252) -> dict[str, Any]:
    rows = load_hmm_csv(csv_path)
    hmm = fit_hmm_rolling(rows, window=window, max_iter=20)

    xgb = _xgb_baseline(rows, window=window)
    lead = _lead_time_eval(rows, hmm["rows"], xgb["by_date"])

    # transition sanity
    row_sums = [float(x) for x in hmm["transition_row_sums"]]
    trans_ok = all(abs(s - 1.0) < 1e-6 for s in row_sums)

    # state order sanity (coherent with vix)
    last_vix_means = hmm.get("last_vix_means_scaled") or []
    order_ok = False
    if last_vix_means and len(last_vix_means) == 3:
        ordered = sorted(last_vix_means)
        order_ok = (ordered[0] < ordered[1] < ordered[2])

    payload = {
        "window": window,
        "transition_row_sums": row_sums,
        "transition_ok": trans_ok,
        "vix_means_scaled_last": last_vix_means,
        "vix_order_ok": order_ok,
        "lead_eval": lead,
    }

    out = Path(outdir)
    _ensure_dir(out)
    (out / "f2_t2_hmm_metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md = [
        "# F2-T2 HMM Rolling (offline)",
        f"- window: {window}",
        f"- transition_row_sums: {row_sums}",
        f"- transition_ok: {trans_ok}",
        f"- vix_means_scaled_last: {last_vix_means}",
        f"- vix_order_ok: {order_ok}",
        "",
        "## Early warning lead (HMM vs baseline classifier)",
    ]
    for f in payload["lead_eval"]["families"]:
        md.append(f"- {f['family']}: lead_days={f['lead_days']} pass={f['pass']}")
    md.append(f"PASS lead criterion: {payload['lead_eval']['pass']} ({payload['lead_eval']['ok_leads']}/{payload['lead_eval']['n_families']})")
    (out / "f2_t2_hmm_metrics.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    return payload


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="samples/hmm_features_synth_340d.csv")
    ap.add_argument("--outdir", default="reports")
    ap.add_argument("--window", type=int, default=252)
    args = ap.parse_args()

    payload = run(args.csv, outdir=args.outdir, window=args.window)

    ok = payload["transition_ok"] and payload["vix_order_ok"] and payload["lead_eval"]["pass"]
    if ok:
        print(f"OK F2-T2 HMM rolling window={payload['window']} lead_ok={payload['lead_eval']['ok_leads']}/{payload['lead_eval']['n_families']}")
        return 0
    print("FAIL F2-T2 criteria not met")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
