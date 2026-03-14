from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from scripts import demo_pipeline_lib as dpl
except ModuleNotFoundError:  # support direct execution: py scripts\build_test_dataset.py
    import demo_pipeline_lib as dpl


FIELDS = [
    "capture_id",
    "captured_ts_utc",
    "source",
    "symbol",
    "page_type",
    "observed_ts_utc",
    "bid",
    "ask",
    "last",
    "iv",
    "delta",
    "underlying_price",
    "fingerprint_sha256",
    "model",
    "prompt_version",
    "backend",
    "validator_version",
    "raw_path",
    "output_path",
]


def _to_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def _load_output_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("extraction output must be a JSON object")
    return payload


def _collect_rows(
    db_path: Path,
    *,
    model: str | None,
    prompt_version: str | None,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    conn = dpl.connect_db(db_path)
    dpl.init_db(conn)

    where: list[str] = ["e.status = 'VALID'"]
    params: list[Any] = []
    if model:
        where.append("e.model = ?")
        params.append(model)
    if prompt_version:
        where.append("e.prompt_version = ?")
        params.append(prompt_version)

    sql = (
        """
        SELECT
            c.id AS capture_id,
            c.captured_ts_utc,
            c.source,
            c.symbol,
            c.page_type,
            c.fingerprint_sha256,
            c.raw_path,
            e.model,
            e.prompt_version,
            e.backend,
            e.output_path
        FROM captures c
        JOIN extractions e ON e.capture_id = c.id
        WHERE
        """
        + " AND ".join(where)
        + """
        ORDER BY c.id ASC
        LIMIT ?
        """
    )
    params.append(limit)
    rows = dpl.fetchall_dicts(conn, sql, params)

    out: list[dict[str, Any]] = []
    dedup_keys: set[tuple[str, str, str, str]] = set()
    skipped_duplicates = 0

    skipped_missing = 0
    for row in rows:
        output_path = Path(str(row["output_path"]))
        if not output_path.exists():
            skipped_missing += 1
            dpl.append_jsonl(
                Path(str(dpl.DEFAULT_LOG_DIR / "build_dataset.jsonl")),
                {"event": "skipped_missing_output", "output_path": output_path.as_posix(),
                 "capture_id": row.get("capture_id")},
            )
            continue

        payload = _load_output_payload(output_path)
        rec = payload.get("record", {})
        if not isinstance(rec, dict):
            rec = {}

        symbol = str(row["symbol"])
        page_type = str(row["page_type"])
        observed_ts = str(rec.get("observed_ts_utc") or "")
        fingerprint = str(row["fingerprint_sha256"])
        dedup_key = (symbol, page_type, observed_ts, fingerprint)
        if dedup_key in dedup_keys:
            skipped_duplicates += 1
            continue
        dedup_keys.add(dedup_key)

        out.append(
            {
                "capture_id": int(row["capture_id"]),
                "captured_ts_utc": str(row["captured_ts_utc"]),
                "source": str(row["source"]),
                "symbol": symbol,
                "page_type": page_type,
                "observed_ts_utc": observed_ts or None,
                "bid": _to_float(rec.get("bid")),
                "ask": _to_float(rec.get("ask")),
                "last": _to_float(rec.get("last")),
                "iv": _to_float(rec.get("iv")),
                "delta": _to_float(rec.get("delta")),
                "underlying_price": _to_float(rec.get("underlying_price")),
                "fingerprint_sha256": fingerprint,
                "model": str(row["model"]),
                "prompt_version": str(row["prompt_version"]),
                "backend": str(row["backend"]),
                "validator_version": str(payload.get("validator_version") or "unknown"),
                "raw_path": str(row["raw_path"]),
                "output_path": output_path.as_posix(),
            }
        )

    conn.close()
    return out, skipped_duplicates, skipped_missing


def _csv_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def _write_parquet_if_requested(csv_path: Path, parquet_path: Path, *, write_parquet: bool) -> tuple[bool, str]:
    if not write_parquet:
        return False, "disabled"
    try:
        import pandas as pd  # type: ignore
    except ModuleNotFoundError:
        return False, "pandas not available"

    try:
        df = pd.read_csv(csv_path)
        df.to_parquet(parquet_path, index=False)
        return True, "ok"
    except Exception as exc:
        return False, f"parquet write failed: {exc}"


def run_build(args: argparse.Namespace) -> dict[str, Any]:
    db_path = Path(args.db)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, skipped_duplicates, skipped_missing = _collect_rows(
        db_path,
        model=args.model if args.model else None,
        prompt_version=args.prompt_version if args.prompt_version else None,
        limit=max(1, args.limit),
    )

    csv_path = out_dir / f"{args.dataset_name}.csv"
    parquet_path = out_dir / f"{args.dataset_name}.parquet"
    prov_path = out_dir / f"{args.dataset_name}.provenance.json"

    _write_csv(csv_path, rows)
    csv_hash = _csv_sha256(csv_path)

    parquet_written, parquet_note = _write_parquet_if_requested(
        csv_path,
        parquet_path,
        write_parquet=bool(args.write_parquet),
    )

    provenance = {
        "generated_ts_utc": dpl.utc_now_iso(),
        "dataset_name": args.dataset_name,
        "record_count": len(rows),
        "dedup_skipped": skipped_duplicates,
        "missing_output_skipped": skipped_missing,
        "db_path": db_path.as_posix(),
        "dataset_csv": csv_path.as_posix(),
        "dataset_csv_sha256": csv_hash,
        "dataset_parquet": parquet_path.as_posix() if parquet_written else None,
        "model_filter": args.model or None,
        "prompt_version_filter": args.prompt_version or None,
        "parquet_status": parquet_note,
        "symbols": sorted({str(row["symbol"]) for row in rows}),
        "page_types": sorted({str(row["page_type"]) for row in rows}),
        "models": sorted({str(row["model"]) for row in rows}),
        "prompt_versions": sorted({str(row["prompt_version"]) for row in rows}),
        "validator_versions": sorted({str(row["validator_version"]) for row in rows}),
        "records": [
            {
                "capture_id": int(row["capture_id"]),
                "symbol": str(row["symbol"]),
                "page_type": str(row["page_type"]),
                "fingerprint_sha256": str(row["fingerprint_sha256"]),
                "model": str(row["model"]),
                "prompt_version": str(row["prompt_version"]),
                "validator_version": str(row["validator_version"]),
                "raw_path": str(row["raw_path"]),
                "output_path": str(row["output_path"]),
            }
            for row in rows
        ],
    }
    dpl.write_json(prov_path, provenance)

    dpl.append_jsonl(
        Path(args.log_path),
        {
            "ts_utc": dpl.utc_now_iso(),
            "event": "dataset_built",
            "dataset_name": args.dataset_name,
            "records": len(rows),
            "dedup_skipped": skipped_duplicates,
            "csv_path": csv_path.as_posix(),
            "provenance_path": prov_path.as_posix(),
            "dataset_csv_sha256": csv_hash,
            "parquet_written": parquet_written,
        },
    )

    return {
        "dataset_name": args.dataset_name,
        "records": len(rows),
        "dedup_skipped": skipped_duplicates,
        "csv_path": csv_path.as_posix(),
        "provenance_path": prov_path.as_posix(),
        "parquet_written": parquet_written,
        "parquet_status": parquet_note,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="build_test_dataset")
    p.add_argument("--db", default=str(dpl.DEFAULT_DB))
    p.add_argument("--out-dir", default=str(dpl.DEFAULT_DATASET_DIR))
    p.add_argument("--dataset-name", default="demo_dataset")
    p.add_argument("--model", default="qwen2.5")
    p.add_argument("--prompt-version", default="v1")
    p.add_argument("--limit", type=int, default=20000)
    p.add_argument("--write-parquet", action="store_true")
    p.add_argument("--log-path", default=str(dpl.DEFAULT_LOG_DIR / "dataset.jsonl"))
    p.add_argument("--format", choices=["line", "json"], default="line")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_build(args)
    except RuntimeError as exc:
        print(f"BUILD_TEST_DATASET FAIL reason={exc}")
        return 2

    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            "BUILD_TEST_DATASET "
            f"name={summary['dataset_name']} records={summary['records']} "
            f"dedup_skipped={summary['dedup_skipped']} parquet={summary['parquet_written']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


