from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.ivr import load_iv_history_csv, compute_iv_rank_from_history


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="f1_t2_compute_ivr")
    p.add_argument("--iv-history", default="samples/iv_history_sample_252d.csv")
    p.add_argument("--tickers", default="SPY,IWM,QQQ")
    p.add_argument("--lookback", type=int, default=252)
    p.add_argument("--outdir", default="reports")
    p.add_argument("--format", choices=["json", "md", "both"], default="both")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    iv_path = Path(args.iv_history)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    history = load_iv_history_csv(iv_path)
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    results = []
    for t in tickers:
        ivr = compute_iv_rank_from_history(history, t, lookback=args.lookback)
        results.append({"ticker": t, "iv_rank": ivr})

    payload = {
        "task": "F1-T2",
        "lookback": args.lookback,
        "iv_history": str(iv_path).replace("\\", "/"),
        "results": results,
    }

    if args.format in ("json", "both"):
        (outdir / "f1_t2_ivr.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.format in ("md", "both"):
        lines = ["# F1-T2 — IV Rank (252d)", "", f"Lookback: {args.lookback}", ""]
        for r in results:
            v = r["iv_rank"]
            if v is None:
                lines.append(f"- {r['ticker']}: MISSING")
            else:
                lines.append(f"- {r['ticker']}: {v:.2f}")
        (outdir / "f1_t2_ivr.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("OK F1-T2 IVR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
