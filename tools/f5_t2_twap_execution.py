from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.execution_plan import build_twap_slices, select_execution_plan


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="f5_t2_twap_execution")
    p.add_argument("--bid", type=float, required=True)
    p.add_argument("--ask", type=float, required=True)
    p.add_argument("--legs-count", type=int, default=4)
    p.add_argument("--quantity", type=int, default=3)
    p.add_argument("--twap-trigger-abs", type=float, default=0.50)
    p.add_argument("--twap-slices", type=int, default=3)
    p.add_argument("--twap-slice-interval-sec", type=int, default=300)
    p.add_argument("--outdir", default="reports")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    plan = select_execution_plan(
        bid=args.bid,
        ask=args.ask,
        enable_twap=True,
        twap_trigger_abs=args.twap_trigger_abs,
        twap_slices=args.twap_slices,
        twap_slice_interval_sec=args.twap_slice_interval_sec,
        legs_count=args.legs_count,
        order_quantity=args.quantity,
    )

    schedule = [s.__dict__ for s in build_twap_slices(total_quantity=args.quantity, twap_slices=args.twap_slices, twap_slice_interval_sec=args.twap_slice_interval_sec)]

    payload = {
        "inputs": {
            "bid": args.bid,
            "ask": args.ask,
            "legs_count": args.legs_count,
            "quantity": args.quantity,
            "twap_trigger_abs": args.twap_trigger_abs,
            "twap_slices": args.twap_slices,
            "twap_slice_interval_sec": args.twap_slice_interval_sec,
        },
        "plan": {
            "kind": plan.kind,
            "reason": plan.reason,
            "details": plan.details,
        },
        "schedule": schedule,
    }

    (outdir / "f5_t2_twap_execution.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md = []
    md.append("# F5-T2 TWAP Execution\n\n")
    md.append(f"- plan.kind: `{plan.kind}`\n")
    md.append(f"- plan.reason: `{plan.reason}`\n")
    md.append(f"- spread_abs: `{plan.details.get('spread_abs')}`\n")
    md.append("\n| slice | quantity | offset_sec |\n|---:|---:|---:|\n")
    for s in schedule:
        md.append(f"| {s['slice_no']} | {s['quantity']} | {s['offset_sec']} |\n")
    (outdir / "f5_t2_twap_execution.md").write_text("".join(md), encoding="utf-8")

    if plan.kind != "TWAP":
        print(f"FAIL F5-T2 expected=TWAP got={plan.kind} reason={plan.reason}")
        return 10

    print(
        "OK F5-T2"
        f" spread_abs={plan.details.get('spread_abs'):.4f}"
        f" slices={args.twap_slices}"
        f" interval_sec={args.twap_slice_interval_sec}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
