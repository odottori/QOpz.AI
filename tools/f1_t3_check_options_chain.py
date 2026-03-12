from __future__ import annotations

r"""
F1-T3 runner: options chain quality checks over a CSV (offline sample).

Usage:
  py tools\f1_t3_check_options_chain.py
  py tools\f1_t3_check_options_chain.py --csv samples\options_chain_sample_5d_100strikes.csv --outdir reports
"""

import argparse
from pathlib import Path
import sys

# When executed as "py tools\...", sys.path[0]="tools/"
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))

from options_chain_quality import load_chain_csv, run_quality_checks, write_report  # type: ignore


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="f1_t3_check_options_chain")
    p.add_argument("--csv", default="samples/options_chain_sample_5d_100strikes.csv")
    p.add_argument("--outdir", default="reports")
    p.add_argument("--days", type=int, default=5)
    p.add_argument("--strikes-per-day", type=int, default=100)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--parity-threshold", type=float, default=0.50)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    quotes = load_chain_csv(Path(args.csv))
    report = run_quality_checks(
        quotes,
        days=args.days,
        strikes_per_day=args.strikes_per_day,
        seed=args.seed,
        parity_threshold=args.parity_threshold,
    )
    write_report(report, outdir=Path(args.outdir))
    print(f"OK F1-T3 rows_sampled={report['rows_sampled']} excluded={report['rows_excluded']} parity_alerts={report['parity']['alerts_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
