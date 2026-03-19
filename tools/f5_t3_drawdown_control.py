from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.drawdown_control import evaluate_drawdown_policy


def _parse_float_list(raw: str) -> list[float]:
    out: list[float] = []
    for token in (raw or "").split(","):
        t = token.strip()
        if not t:
            continue
        out.append(float(t))
    return out


def _parse_levels(raw: str) -> list[str]:
    out: list[str] = []
    for token in (raw or "").split(","):
        t = token.strip().upper()
        if not t:
            continue
        out.append(t)
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="f5_t3_drawdown_control")
    p.add_argument("--equity-series", required=True, help="comma-separated equity values")
    p.add_argument("--dd-alert", type=float, default=0.10)
    p.add_argument("--dd-stop", type=float, default=0.15)
    p.add_argument("--dd-kill", type=float, default=0.20)
    p.add_argument("--require-levels", default="ALERT,STOP,KILL")
    p.add_argument("--outdir", default="reports")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    equity = _parse_float_list(args.equity_series)
    required_levels = _parse_levels(args.require_levels)

    state = evaluate_drawdown_policy(
        equity_series=equity,
        dd_alert=args.dd_alert,
        dd_stop=args.dd_stop,
        dd_kill=args.dd_kill,
    )

    events = [
        {
            "index": e.index,
            "equity": e.equity,
            "drawdown": e.drawdown,
            "level": e.level,
            "sizing_scalar": e.sizing_scalar,
            "allow_new_positions": e.allow_new_positions,
            "hedge_on": e.hedge_on,
            "kill_switch": e.kill_switch,
        }
        for e in state.events
    ]

    seen_levels = [e["level"] for e in events]
    missing_levels = [lvl for lvl in required_levels if lvl not in seen_levels]

    payload = {
        "inputs": {
            "equity_series": equity,
            "dd_alert": args.dd_alert,
            "dd_stop": args.dd_stop,
            "dd_kill": args.dd_kill,
            "require_levels": required_levels,
        },
        "result": {
            "max_drawdown": state.max_drawdown,
            "sizing_scalar": state.sizing_scalar,
            "allow_new_positions": state.allow_new_positions,
            "hedge_on": state.hedge_on,
            "kill_switch": state.kill_switch,
            "seen_levels": seen_levels,
            "missing_levels": missing_levels,
        },
        "events": events,
    }

    (outdir / "f5_t3_drawdown_control.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md = []
    md.append("# F5-T3 Drawdown Control\n\n")
    md.append("| Metric | Value |\n|---|---:|\n")
    md.append(f"| max_drawdown | {state.max_drawdown:.6f} |\n")
    md.append(f"| sizing_scalar | {state.sizing_scalar:.6f} |\n")
    md.append(f"| allow_new_positions | {state.allow_new_positions} |\n")
    md.append(f"| hedge_on | {state.hedge_on} |\n")
    md.append(f"| kill_switch | {state.kill_switch} |\n")
    md.append("\n| idx | equity | dd | level | sizing | allow_new | hedge_on | kill_switch |\n")
    md.append("|---:|---:|---:|---|---:|---|---|---|\n")
    for e in events:
        md.append(
            f"| {e['index']} | {e['equity']:.2f} | {e['drawdown']:.4f} | {e['level']} | "
            f"{e['sizing_scalar']:.2f} | {e['allow_new_positions']} | {e['hedge_on']} | {e['kill_switch']} |\n"
        )
    (outdir / "f5_t3_drawdown_control.md").write_text("".join(md), encoding="utf-8")

    if missing_levels:
        print(
            "FAIL F5-T3"
            f" missing_levels={','.join(missing_levels)}"
            f" seen_levels={','.join(seen_levels)}"
            f" max_drawdown={state.max_drawdown:.4f}"
        )
        return 10

    print(
        "OK F5-T3"
        f" max_drawdown={state.max_drawdown:.4f}"
        f" levels={','.join(seen_levels)}"
        f" kill_switch={state.kill_switch}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
