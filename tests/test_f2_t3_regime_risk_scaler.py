import csv
from pathlib import Path

from scripts.regime_risk_scaler import RiskScalarConfig, compute_risk_scalar_series


def _load_rows():
    ip = Path("samples/regime_score_synth_200d.csv")
    rows = []
    with ip.open("r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({
                "date": row["date"],
                "p_shock_hmm": float(row["p_shock_hmm"]),
                "p_shock_clf": float(row["p_shock_clf"]),
            })
    return rows


def test_f2_t3_risk_scalar_behaves():
    rows = _load_rows()
    out = compute_risk_scalar_series(rows, cfg=RiskScalarConfig())

    # normal segment: first 80
    normal = out[:80]
    shock = out[110:130]  # inside shock window
    normal2 = out[170:190]

    avg_normal = sum(r["risk_scalar"] for r in normal) / len(normal)
    avg_shock = sum(r["risk_scalar"] for r in shock) / len(shock)
    avg_normal2 = sum(r["risk_scalar"] for r in normal2) / len(normal2)

    assert avg_normal > 0.80
    assert avg_shock < 0.50
    assert avg_normal2 > 0.80

    # bounds respected
    assert min(r["risk_scalar"] for r in out) >= 0.25
    assert max(r["risk_scalar"] for r in out) <= 1.0
