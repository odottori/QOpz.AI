from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts import demo_pipeline_lib as dpl
    from scripts.metrics import annualized_sharpe, equity_curve, max_drawdown, win_rate
except ModuleNotFoundError:  # support direct execution: py scripts\\run_backtest.py
    import demo_pipeline_lib as dpl
    from metrics import annualized_sharpe, equity_curve, max_drawdown, win_rate


def _to_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _pick_price(row: dict[str, Any]) -> float | None:
    last = _to_float(row.get("last"))
    bid = _to_float(row.get("bid"))
    ask = _to_float(row.get("ask"))

    if last is not None and last > 0:
        return last
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    if bid is not None and bid > 0:
        return bid
    if ask is not None and ask > 0:
        return ask
    return None


def _resolve_dataset_path(args: argparse.Namespace) -> Path:
    if args.dataset_csv:
        return Path(args.dataset_csv)

    by_name = Path(args.dataset_dir) / f"{args.dataset_name}.csv"
    if by_name.exists():
        return by_name

    candidates = sorted(Path(args.dataset_dir).glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    return by_name


def _load_dataset_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return [dict(x) for x in r]


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str, int]:
    symbol = str(row.get("symbol") or "")
    ts = str(row.get("observed_ts_utc") or row.get("captured_ts_utc") or "")
    capture_id = int(row.get("capture_id") or 0)
    return symbol, ts, capture_id


def _build_returns(rows: list[dict[str, Any]]) -> tuple[list[float], dict[str, int]]:
    ordered = sorted(rows, key=_row_sort_key)
    prev_by_symbol: dict[str, float] = {}
    returns: list[float] = []
    per_symbol_counts: dict[str, int] = defaultdict(int)

    for row in ordered:
        symbol = str(row.get("symbol") or "")
        px = _pick_price(row)
        if not symbol or px is None:
            continue

        per_symbol_counts[symbol] += 1
        prev = prev_by_symbol.get(symbol)
        if prev is not None and prev > 0:
            returns.append((px / prev) - 1.0)
        prev_by_symbol[symbol] = px

    return returns, dict(per_symbol_counts)


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Demo Pipeline Backtest",
        "",
        f"- Dataset: `{payload['dataset_csv']}`",
        f"- Rows: `{payload['n_rows']}`",
        f"- Returns: `{payload['n_returns']}`",
        f"- Sharpe: `{payload['sharpe']:.4f}`",
        f"- MaxDD: `{payload['max_drawdown']:.4f}`",
        f"- WinRate: `{payload['win_rate']:.4f}`",
        f"- Equity End: `{payload['equity_end']:.6f}`",
        f"- Gate (min_returns): `{payload['gates']['min_returns']['pass']}`",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_backtest(args: argparse.Namespace) -> dict[str, Any]:
    dataset = _resolve_dataset_path(args)
    if not dataset.exists():
        return {
            "ok": False,
            "reason": f"dataset not found: {dataset.as_posix()}",
            "dataset_csv": dataset.as_posix(),
            "n_rows": 0,
            "n_returns": 0,
        }

    rows = _load_dataset_rows(dataset)
    returns, per_symbol = _build_returns(rows)

    eq = equity_curve(returns, start=1.0)
    sharpe = annualized_sharpe(returns)
    mdd = max_drawdown(eq)
    wr = win_rate(returns)

    payload = {
        "generated_ts_utc": dpl.utc_now_iso(),
        "dataset_csv": dataset.as_posix(),
        "n_rows": len(rows),
        "n_returns": len(returns),
        "per_symbol_observations": per_symbol,
        "sharpe": float(sharpe),
        "max_drawdown": float(mdd),
        "win_rate": float(wr),
        "equity_start": float(eq[0] if eq else 1.0),
        "equity_end": float(eq[-1] if eq else 1.0),
        "gates": {
            "min_returns": {
                "required": int(args.min_returns),
                "actual": len(returns),
                "pass": len(returns) >= int(args.min_returns),
            }
        },
    }
    payload["ok"] = bool(payload["gates"]["min_returns"]["pass"])

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"{args.run_name}.json"
    out_md = out_dir / f"{args.run_name}.md"

    dpl.write_json(out_json, payload)
    _write_markdown(out_md, payload)

    dpl.append_jsonl(
        Path(args.log_path),
        {
            "ts_utc": dpl.utc_now_iso(),
            "event": "backtest_done",
            "ok": payload["ok"],
            "dataset_csv": dataset.as_posix(),
            "n_rows": payload["n_rows"],
            "n_returns": payload["n_returns"],
            "report_json": out_json.as_posix(),
        },
    )

    payload["report_json"] = out_json.as_posix()
    payload["report_md"] = out_md.as_posix()
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="run_backtest")
    p.add_argument("--dataset-csv", default="")
    p.add_argument("--dataset-dir", default=str(dpl.DEFAULT_DATASET_DIR))
    p.add_argument("--dataset-name", default="demo_dataset")
    p.add_argument("--out-dir", default="reports/demo_pipeline_backtest")
    p.add_argument("--run-name", default="demo_backtest")
    p.add_argument("--min-returns", type=int, default=5)
    p.add_argument("--log-path", default=str(dpl.DEFAULT_LOG_DIR / "backtest.jsonl"))
    p.add_argument("--format", choices=["line", "json"], default="line")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_backtest(args)

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if payload.get("ok"):
            print(
                "RUN_BACKTEST "
                f"ok=1 rows={payload['n_rows']} returns={payload['n_returns']} "
                f"sharpe={payload['sharpe']:.4f} maxdd={payload['max_drawdown']:.4f}"
            )
        else:
            print(
                "RUN_BACKTEST "
                f"ok=0 rows={payload.get('n_rows', 0)} returns={payload.get('n_returns', 0)} "
                f"reason={payload.get('reason', 'min_returns gate failed')}"
            )
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())

