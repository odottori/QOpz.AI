from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path when invoked as: `py tools\f2_t4_wfa_bull_put.py`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.wfa_bull_put import load_returns_csv, run_wfa_bull_put


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def _write_md(path: Path, summary: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# F2-T4 — WFA Bull Put (DEV offline)\n")
    lines.append(f"- folds: **{summary['n_folds']}** (3y IS / 1y OOS, sliding by year)\n")
    lines.append("\n## Metrics (OOS)\n")
    lines.append(f"- median Sharpe: **{summary['median_sharpe_oos']:.3f}** (>= 0.60)\n")
    lines.append(f"- max drawdown: **{summary['max_dd_oos']:.3f}** (<= 0.15)\n")
    lines.append(f"- median win rate: **{summary['median_win_rate_oos']:.3f}** (>= 0.55)\n")
    lines.append(f"- IS/OOS deflation: **{summary['deflation']:.3f}** (>= 0.60)\n")
    lines.append("\n## Sharpe per fold\n")
    lines.append("| Fold | IS years | OOS year | Sharpe IS | Sharpe OOS | MaxDD OOS | WinRate OOS | scalar |\n")
    lines.append("|---:|:---:|---:|---:|---:|---:|---:|---:|\n")
    for f in summary["folds"]:
        lines.append(
            f"| {f['fold']} | {f['is_years']} | {f['oos_year']} | {f['sharpe_is']:.3f} | {f['sharpe_oos']:.3f} | {f['maxdd_oos']:.3f} | {f['winrate_oos']:.3f} | {f['chosen_scalar']:.2f} |\n"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="f2_t4_wfa_bull_put")
    p.add_argument(
        "--csv",
        default="samples/iwm_bull_put_synth_2010_2024.csv",
        help="Path to offline returns CSV (date,ret)",
    )
    p.add_argument("--outdir", default="reports", help="Output directory")
    p.add_argument("--folds", type=int, default=10)
    p.add_argument("--is-years", type=int, default=3)
    p.add_argument("--no-plots", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = load_returns_csv(Path(args.csv))
    summary, oos_points = run_wfa_bull_put(rows, n_folds=args.folds, is_years=args.is_years)

    outdir = Path(args.outdir)
    js = {
        "n_folds": summary.n_folds,
        "median_sharpe_oos": summary.median_sharpe_oos,
        "max_dd_oos": summary.max_dd_oos,
        "median_win_rate_oos": summary.median_win_rate_oos,
        "deflation": summary.deflation,
        "worst_oos_dd": summary.worst_oos_dd,
        "folds": [m.__dict__ for m in summary.folds],
    }
    _write_json(outdir / "f2_t4_wfa_summary.json", js)
    _write_md(outdir / "f2_t4_wfa_summary.md", js)

    # equity curve points (concatenated OOS)
    outdir.mkdir(parents=True, exist_ok=True)
    with (outdir / "f2_t4_equity_oos.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "equity"])
        for d, eq in oos_points:
            w.writerow([d.isoformat(), f"{eq:.8f}"])

    # sharpe by fold
    with (outdir / "f2_t4_sharpe_by_fold.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fold", "sharpe_is", "sharpe_oos", "maxdd_oos", "winrate_oos", "scalar"])
        for m in summary.folds:
            w.writerow([m.fold, f"{m.sharpe_is:.6f}", f"{m.sharpe_oos:.6f}", f"{m.maxdd_oos:.6f}", f"{m.winrate_oos:.6f}", f"{m.chosen_scalar:.2f}"])

    # drawdown series (derived from equity points)
    peak = 0.0
    with (outdir / "f2_t4_drawdown_oos.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "drawdown"])
        for d, eq in oos_points:
            peak = eq if eq > peak else peak
            dd = (peak - eq) / peak if peak > 0 else 0.0
            w.writerow([d.isoformat(), f"{dd:.8f}"])

    # Optional plots (only if matplotlib is available). Not required by unit tests.
    if not args.no_plots:
        try:
            import matplotlib.pyplot as plt  # type: ignore

            dates = [d for d, _ in oos_points]
            eqs = [eq for _, eq in oos_points]

            plt.figure()
            plt.plot(dates, eqs)
            plt.title("F2-T4 OOS equity (concatenated)")
            plt.tight_layout()
            plt.savefig(outdir / "f2_t4_equity_oos.png")
            plt.close()

        except Exception:
            pass

    # Pass criteria enforcement for DEV gate
    ok = (
        summary.median_sharpe_oos >= 0.60
        and summary.max_dd_oos <= 0.15
        and summary.median_win_rate_oos >= 0.55
        and summary.deflation >= 0.60
        and all(m.maxdd_oos <= 0.20 for m in summary.folds)
    )
    if not ok:
        raise SystemExit("FAIL F2-T4 thresholds not met")

    print(
        f"OK F2-T4 median_sharpe_oos={summary.median_sharpe_oos:.3f} maxdd_oos={summary.max_dd_oos:.3f} winrate_med={summary.median_win_rate_oos:.3f} deflation={summary.deflation:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
