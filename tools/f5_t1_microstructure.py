from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow execution as `py tools\f5_t1_microstructure.py`.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.microstructure_features import compute_microstructure_features


def _parse_float_list(raw: str) -> list[float]:
    out: list[float] = []
    for token in (raw or "").split(","):
        t = token.strip()
        if not t:
            continue
        out.append(float(t))
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="f5_t1_microstructure")
    p.add_argument("--bid-volume", type=float, required=True)
    p.add_argument("--ask-volume", type=float, required=True)
    p.add_argument("--oi-t", type=float, required=True)
    p.add_argument("--oi-t-3", type=float, required=True)
    p.add_argument("--oi-velocity-history", required=True, help="comma-separated velocities")
    p.add_argument("--skew-5d", required=True, help="comma-separated skew series")
    p.add_argument("--outdir", default="reports")
    p.add_argument("--format", choices=["json", "md"], default="json")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    oi_hist = _parse_float_list(args.oi_velocity_history)
    skew = _parse_float_list(args.skew_5d)

    features = compute_microstructure_features(
        bid_volume=args.bid_volume,
        ask_volume=args.ask_volume,
        oi_t=args.oi_t,
        oi_t_minus_n=args.oi_t_3,
        oi_velocity_history=oi_hist,
        skew_5d_series=skew,
    )

    payload = {
        "inputs": {
            "bid_volume": args.bid_volume,
            "ask_volume": args.ask_volume,
            "oi_t": args.oi_t,
            "oi_t_3": args.oi_t_3,
            "oi_velocity_history": oi_hist,
            "skew_5d": skew,
        },
        "features": {
            "volume_profile_delta": features.volume_profile_delta,
            "oi_change_velocity": features.oi_change_velocity,
            "oi_velocity_spike": features.oi_velocity_spike,
            "iv_curvature_accel": features.iv_curvature_accel,
        },
    }

    op_json = outdir / "f5_t1_microstructure.json"
    op_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    op_md = outdir / "f5_t1_microstructure.md"
    md = []
    md.append("# F5-T1 Microstructure Features\n\n")
    md.append("| Feature | Value |\n|---|---:|\n")
    md.append(f"| volume_profile_delta | {features.volume_profile_delta:.6f} |\n")
    md.append(f"| oi_change_velocity | {features.oi_change_velocity:.6f} |\n")
    md.append(f"| oi_velocity_spike | {str(features.oi_velocity_spike)} |\n")
    md.append(f"| iv_curvature_accel | {features.iv_curvature_accel:.6f} |\n")
    op_md.write_text("".join(md), encoding="utf-8")

    print(
        "OK F5-T1"
        f" volume_profile_delta={features.volume_profile_delta:.4f}"
        f" oi_change_velocity={features.oi_change_velocity:.4f}"
        f" oi_velocity_spike={features.oi_velocity_spike}"
        f" iv_curvature_accel={features.iv_curvature_accel:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
