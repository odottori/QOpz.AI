from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.paper_metrics import compute_paper_summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="f6_t2_go_nogo_pack")
    p.add_argument("--profile", default="paper")
    p.add_argument("--window-days", type=int, default=60)
    p.add_argument("--asof-date", default=None, help="Override as-of date (YYYY-MM-DD). Default: today UTC.")
    p.add_argument("--outdir", default="reports")
    p.add_argument("--strict", action="store_true", help="Return rc=10 when GO/NO-GO or F6-T2 journal gate fail")
    p.add_argument("--format", choices=["md", "json"], default="md")
    return p.parse_args(argv)


def _as_dict(s) -> Dict[str, Any]:
    return {
        "profile": s.profile,
        "window_days": s.window_days,
        "as_of_date": s.as_of_date.isoformat(),
        "equity_points": s.equity_points,
        "trades": s.trades,
        "sharpe_annualized": s.sharpe_annualized,
        "max_drawdown": s.max_drawdown,
        "win_rate": s.win_rate,
        "profit_factor": s.profit_factor,
        "avg_slippage_ticks": s.avg_slippage_ticks,
        "compliance_violations": s.compliance_violations,
        "gates": s.gates,
    }


def _fmt_md(d: Dict[str, Any]) -> str:
    g = d.get("gates", {})
    go = g.get("go_nogo", {})
    f6 = g.get("f6_t1_acceptance", {})
    j = g.get("f6_t2_journal_complete", {})
    w = g.get("window", {})

    lines: list[str] = []
    lines.append("## F6-T2 - GO/NO-GO PACK")
    lines.append("")
    lines.append(f"- Profile: `{d.get('profile')}`")
    lines.append(f"- Window: {w.get('start_date')} -> {w.get('end_date')} (days={d.get('window_days')})")
    lines.append(f"- Equity snapshots: {d.get('equity_points')}")
    lines.append(f"- Trades (metrics-valid): {d.get('trades')}")
    lines.append("")
    lines.append("### Metrics")
    lines.append(f"- Sharpe (ann.): {d.get('sharpe_annualized')}")
    lines.append(f"- MaxDD: {d.get('max_drawdown')}")
    lines.append(f"- Win rate: {d.get('win_rate')}")
    lines.append(f"- Profit factor: {d.get('profit_factor')}")
    lines.append(f"- Avg slippage ticks: {d.get('avg_slippage_ticks')}")
    lines.append(f"- Compliance violations: {d.get('compliance_violations')}")
    lines.append("")
    lines.append("### Gates")
    lines.append(f"- GO/NO-GO: **{'PASS' if go.get('pass') else 'FAIL'}**")
    for r in go.get("reasons", []) or []:
        lines.append(f"  - {r}")

    lines.append(f"- F6-T1 acceptance: **{'PASS' if f6.get('pass') else 'FAIL'}**")
    for r in f6.get("reasons", []) or []:
        lines.append(f"  - {r}")

    cr = j.get("completeness_ratio")
    cr_s = f"{(float(cr) * 100):.2f}%" if isinstance(cr, (int, float)) else "n/a"
    lines.append(f"- F6-T2 journal complete: **{'PASS' if j.get('pass') else 'FAIL'}** (completeness={cr_s})")
    for r in j.get("reasons", []) or []:
        lines.append(f"  - {r}")

    missing = j.get("required_missing", {}) if isinstance(j.get("required_missing"), dict) else {}
    if missing:
        lines.append("")
        lines.append("### Journal Missing Map")
        lines.append("| Field | Missing |")
        lines.append("|---|---:|")
        for k in sorted(missing.keys()):
            lines.append(f"| {k} | {missing.get(k)} |")

    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    d = None
    if args.asof_date:
        try:
            d = _date.fromisoformat(args.asof_date)
        except Exception:
            print("ERROR: invalid --asof-date (expected YYYY-MM-DD)")
            return 2

    s = compute_paper_summary(profile=args.profile, window_days=args.window_days, as_of_date=d)
    out = _as_dict(s)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / "f6_t2_go_nogo_pack.json"
    md_path = outdir / "f6_t2_go_nogo_pack.md"

    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_fmt_md(out), encoding="utf-8")

    if args.format == "json":
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(_fmt_md(out).rstrip())

    if not args.strict:
        return 0

    go_ok = bool(out.get("gates", {}).get("go_nogo", {}).get("pass"))
    journal_ok = bool(out.get("gates", {}).get("f6_t2_journal_complete", {}).get("pass"))
    return 0 if (go_ok and journal_ok) else 10


if __name__ == "__main__":
    raise SystemExit(main())
