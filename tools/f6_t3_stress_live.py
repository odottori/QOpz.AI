from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.stress_live import run_f6_t3_stress_suite


def _parse_floats_csv(text: str) -> List[float]:
    out: List[float] = []
    for raw in str(text).split(","):
        s = raw.strip()
        if not s:
            continue
        out.append(float(s))
    return out


def _parse_bools_csv(text: str) -> List[bool]:
    out: List[bool] = []
    for raw in str(text).split(","):
        s = raw.strip().lower()
        if s in {"1", "true", "t", "yes", "y", "ok"}:
            out.append(True)
        elif s in {"0", "false", "f", "no", "n", "fail"}:
            out.append(False)
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="f6_t3_stress_live")
    p.add_argument("--vix-prev", type=float, default=20.0)
    p.add_argument("--vix-now", type=float, default=24.0)
    p.add_argument("--equity-series", default="100000,98000,95000,90000,85000,80000")
    p.add_argument("--reconnect-attempts", default="0,1")
    p.add_argument("--format", choices=["md", "json"], default="md")
    p.add_argument("--strict", action="store_true", help="Return rc=10 when suite fails")
    return p.parse_args(argv)


def _fmt_md(out: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("## F6-T3 - STRESS TEST LIVE")
    lines.append("")
    lines.append(f"- Overall: **{'PASS' if out.get('overall_pass') else 'FAIL'}**")
    lines.append("")
    lines.append("| Scenario | Pass | Key output |")
    lines.append("|---|---|---|")

    for row in out.get("checks", []):
        sc = row.get("scenario", "-")
        ok = "PASS" if row.get("pass") else "FAIL"
        if sc == "VIX_SPIKE_20PCT":
            key = f"regime_after={row.get('regime_after')} hedge_on={row.get('hedge_on')} change={row.get('change_pct'):.2%}"
        elif sc == "GAP_DOWN_5PCT_OVERNIGHT":
            key = f"max_dd={row.get('max_drawdown'):.2%} kill={row.get('kill_switch')} hedge={row.get('hedge_on')}"
        else:
            key = f"reconnect_ok={row.get('reconnect_ok')} at={row.get('reconnect_at_attempt')} alert={row.get('alert_sent')}"
        lines.append(f"| {sc} | {ok} | {key} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    eq = _parse_floats_csv(args.equity_series)
    reconnect = _parse_bools_csv(args.reconnect_attempts)

    out = run_f6_t3_stress_suite(
        vix_prev=args.vix_prev,
        vix_now=args.vix_now,
        equity_series=eq,
        reconnect_attempts=reconnect,
    )

    if args.format == "json":
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(_fmt_md(out).rstrip())

    if args.strict and not out.get("overall_pass"):
        return 10
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
