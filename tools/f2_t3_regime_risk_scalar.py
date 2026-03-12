from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from scripts.regime_risk_scaler import RiskScalarConfig, compute_risk_scalar_series


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="f2_t3_regime_risk_scalar")
    p.add_argument("--csv", default="samples/regime_score_synth_200d.csv")
    p.add_argument("--outdir", default="reports")
    p.add_argument("--format", choices=["json", "md"], default="json")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ip = Path(args.csv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    with ip.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            r["p_shock_hmm"] = float(r["p_shock_hmm"])
            r["p_shock_clf"] = float(r["p_shock_clf"])
            rows.append(r)

    cfg = RiskScalarConfig()
    out = compute_risk_scalar_series(rows, cfg=cfg)

    payload = {
        "rows": out,
        "config": cfg.__dict__,
    }

    op_json = outdir / "f2_t3_regime_risk_scalar.json"
    op_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # compact md
    op_md = outdir / "f2_t3_regime_risk_scalar.md"
    lines = []
    lines.append("# F2-T3 Regime Risk Scalar\n")
    lines.append(f"- rows: {len(out)}\n")
    lines.append("\n|date|p_shock_hmm|p_shock_clf|score|risk|\n|---|---:|---:|---:|---:|\n")
    for r in out[:15]:
        lines.append(f"|{r.get('date','')}|{r['p_shock_hmm']:.2f}|{r['p_shock_clf']:.2f}|{r['regime_score']:.2f}|{r['risk_scalar']:.2f}|\n")
    op_md.write_text("".join(lines), encoding="utf-8")

    print(f"OK F2-T3 rows={len(out)} risk_min={min(r['risk_scalar'] for r in out):.3f} risk_max={max(r['risk_scalar'] for r in out):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
