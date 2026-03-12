from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

try:
    import tomllib  # py3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore

from scripts import market_data_ingest


def _utc_ts_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _load_duckdb_path_from_config(config_path: Path) -> Path | None:
    if tomllib is None or not config_path.exists():
        return None
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8", errors="replace"))
        p = data.get("storage", {}).get("duckdb_path")
        if isinstance(p, str) and p.strip():
            return Path(p.strip())
    except Exception:
        return None
    return None


def _report_ok(report: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []
    nulls = report.get("null_counts") or {}
    if any(int(v or 0) != 0 for v in nulls.values()):
        errors.append(f"null_counts not zero: {nulls}")
    gaps = (report.get("gap_check") or {}).get("missing")
    if int(gaps or 0) != 0:
        errors.append(f"gap_check missing={gaps} (see missing_dates)")
    split = report.get("split_check") or {}
    if split and not bool(split.get("ok")):
        errors.append(f"split_check failed: {split}")
    return (len(errors) == 0), errors


def _to_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append("# F1-T1 — Market Data Ingestion Report (SPY)")
    lines.append("")
    lines.append(f"- rows: `{report.get('rows')}`")
    lines.append(f"- range: `{report.get('date_min')}` → `{report.get('date_max')}`")
    lines.append("")
    lines.append("## Null counts")
    for k, v in (report.get("null_counts") or {}).items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Gap check")
    gc = report.get("gap_check") or {}
    lines.append(f"- missing: `{gc.get('missing')}`")
    md = gc.get("missing_dates") or []
    if md:
        lines.append(f"- missing_dates(sample): `{md[:10]}`")
    lines.append("")
    lines.append("## Split check (SPY 4:1 2022-06-06)")
    sc = report.get("split_check") or {}
    if sc:
        lines.append(f"- ok: `{sc.get('ok')}`")
        lines.append(f"- close_ratio: `{sc.get('close_ratio')}` (expected `{sc.get('expected_ratio')}`)")
        lines.append(f"- adj_close_ratio: `{sc.get('adj_close_ratio')}` (expected `~1.0`)")
    else:
        lines.append("- n/a")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="f1_t1_ingest_spy")
    p.add_argument("--csv", default="samples/spy_daily_sample_2020_2022.csv")
    p.add_argument("--db", default="", help="DuckDB path; if empty, tries config/dev.toml storage.duckdb_path")
    p.add_argument("--config", default="config/dev.toml")
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--outdir", default="reports")
    p.add_argument("--json-only", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    csv_path = Path(args.csv)
    cfg_path = Path(args.config)

    db_path = Path(args.db) if args.db.strip() else (_load_duckdb_path_from_config(cfg_path) or Path("db/quantoptionai.duckdb"))
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"F1-T1 ingest symbol={args.symbol} csv={csv_path.as_posix()} db={db_path.as_posix()}")
    report = market_data_ingest.ingest_csv_to_duckdb(csv_path=csv_path, duckdb_path=db_path, symbol=args.symbol, source="sample_csv")

    ok, errors = _report_ok(report)
    report["ok"] = ok
    report["errors"] = errors

    ts = _utc_ts_compact()
    out_json = outdir / f"f1_t1_ingest_{args.symbol.lower()}_{ts}.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {out_json.as_posix()}")

    if not args.json_only:
        out_md = outdir / f"f1_t1_ingest_{args.symbol.lower()}_{ts}.md"
        out_md.write_text(_to_markdown(report), encoding="utf-8")
        print(f"WROTE {out_md.as_posix()}")

    if ok:
        print("F1-T1 OK")
        return 0

    print("F1-T1 FAIL")
    for e in errors:
        print(f"- {e}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
