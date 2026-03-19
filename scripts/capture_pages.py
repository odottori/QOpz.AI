from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from scripts import demo_pipeline_lib as dpl
except ModuleNotFoundError:  # support direct execution: py scripts\capture_pages.py
    import demo_pipeline_lib as dpl


FILENAME_RE = re.compile(
    r"^(?P<symbol>[A-Za-z0-9_.-]+?)__(?P<page_type>[A-Za-z0-9_.-]+?)(?:__[^.]*)?\.(?P<ext>json|html|txt)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Candidate:
    path: Path
    symbol: str
    page_type: str
    ext: str


def _parse_csv_set(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    out = {x.strip().upper() for x in raw.split(",") if x.strip()}
    return out or None


def _iter_candidates(source_dir: Path) -> list[Candidate]:
    out: list[Candidate] = []
    for p in sorted(source_dir.glob("*")):
        if not p.is_file():
            continue
        m = FILENAME_RE.match(p.name)
        if not m:
            continue
        out.append(
            Candidate(
                path=p,
                symbol=m.group("symbol").upper(),
                page_type=m.group("page_type").lower(),
                ext=m.group("ext").lower(),
            )
        )
    return out


def _latest_capture_ts(conn: Any, *, source: str, symbol: str, page_type: str) -> datetime | None:
    row = dpl.fetchone_dict(
        conn,
        """
        SELECT captured_ts_utc
        FROM captures
        WHERE source = ? AND symbol = ? AND page_type = ? AND status = 'CAPTURED'
        ORDER BY captured_ts_utc DESC
        LIMIT 1
        """,
        (source, symbol, page_type),
    )
    if not row:
        return None
    raw = str(row["captured_ts_utc"]).replace("Z", "+00:00")
    return datetime.fromisoformat(raw)


def _fingerprint_exists(conn: Any, *, source: str, symbol: str, page_type: str, fingerprint: str) -> bool:
    row = dpl.fetchone_dict(
        conn,
        """
        SELECT 1 AS x
        FROM captures
        WHERE source = ? AND symbol = ? AND page_type = ? AND fingerprint_sha256 = ?
        LIMIT 1
        """,
        (source, symbol, page_type, fingerprint),
    )
    return row is not None


def _persist_capture(
    conn: Any,
    *,
    source: str,
    symbol: str,
    page_type: str,
    payload_format: str,
    payload_bytes: int,
    fingerprint: str,
    raw_path: Path,
) -> None:
    conn.execute(
        """
        INSERT INTO captures (
            captured_ts_utc, source, symbol, page_type, fingerprint_sha256,
            raw_path, payload_format, payload_bytes, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CAPTURED')
        """,
        (
            dpl.utc_now_iso(),
            source,
            symbol,
            page_type,
            fingerprint,
            raw_path.as_posix(),
            payload_format,
            payload_bytes,
        ),
    )


def _log_event(log_path: Path, payload: dict[str, Any]) -> None:
    dpl.append_jsonl(log_path, {"ts_utc": dpl.utc_now_iso(), **payload})


def _capture_row_by_raw_path(conn: Any, raw_path: Path) -> dict[str, Any] | None:
    return dpl.fetchone_dict(
        conn,
        """
        SELECT id, source, symbol, page_type, fingerprint_sha256, payload_bytes, status
        FROM captures
        WHERE raw_path = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (raw_path.as_posix(),),
    )


def _prune_raw_file(conn: Any, raw_path: Path, *, reason: str, log_path: Path) -> int:
    row = _capture_row_by_raw_path(conn, raw_path)
    size = raw_path.stat().st_size if raw_path.exists() else 0
    raw_path.unlink(missing_ok=True)
    conn.execute("UPDATE captures SET status='PRUNED' WHERE raw_path=?", (raw_path.as_posix(),))
    _log_event(
        log_path,
        {
            "event": "pruned_file",
            "reason": reason,
            "raw_path": raw_path.as_posix(),
            "bytes": int(size),
            "capture_id": int(row["id"]) if row and row.get("id") is not None else None,
            "source": str(row["source"]) if row and row.get("source") is not None else None,
            "symbol": str(row["symbol"]) if row and row.get("symbol") is not None else None,
            "page_type": str(row["page_type"]) if row and row.get("page_type") is not None else None,
            "fingerprint": str(row["fingerprint_sha256"]) if row and row.get("fingerprint_sha256") is not None else None,
        },
    )
    return int(size)


def _apply_retention(conn: Any, raw_dir: Path, *, retention_days: int, max_store_mb: int, log_path: Path) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    ttl_cutoff = now - timedelta(days=max(0, retention_days))

    pruned_ttl = 0
    pruned_cap = 0
    pruned_bytes = 0

    files = [p for p in raw_dir.rglob("*") if p.is_file()]

    if retention_days > 0:
        for p in files:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            if mtime < ttl_cutoff:
                size = _prune_raw_file(conn, p, reason="ttl", log_path=log_path)
                pruned_ttl += 1
                pruned_bytes += int(size)

    files = [p for p in raw_dir.rglob("*") if p.is_file()]
    if max_store_mb > 0:
        max_bytes = int(max_store_mb * 1024 * 1024)
        total = sum(p.stat().st_size for p in files)
        if total > max_bytes:
            oldest = sorted(files, key=lambda x: x.stat().st_mtime)
            for p in oldest:
                if total <= max_bytes:
                    break
                size = _prune_raw_file(conn, p, reason="disk_cap", log_path=log_path)
                pruned_cap += 1
                pruned_bytes += int(size)
                total -= size

    return {
        "pruned_ttl": pruned_ttl,
        "pruned_cap": pruned_cap,
        "pruned_bytes": pruned_bytes,
    }


def run_capture(args: argparse.Namespace) -> dict[str, Any]:
    source_dir = Path(args.source_dir)
    raw_dir = Path(args.store_dir)
    db_path = Path(args.db)

    conn = dpl.connect_db(db_path)
    dpl.init_db(conn)

    symbols_filter = _parse_csv_set(args.symbols)
    pages_filter = _parse_csv_set(args.page_types)

    counters = {
        "total": 0,
        "captured": 0,
        "filtered": 0,
        "duplicates": 0,
        "skipped_fresh": 0,
    }
    log_path = Path(args.log_path)

    source_dir.mkdir(parents=True, exist_ok=True)
    candidates = _iter_candidates(source_dir)
    if args.limit and args.limit > 0:
        candidates = candidates[: args.limit]

    for c in candidates:
        counters["total"] += 1

        if symbols_filter and c.symbol.upper() not in symbols_filter:
            counters["filtered"] += 1
            continue
        if pages_filter and c.page_type.upper() not in pages_filter:
            counters["filtered"] += 1
            continue

        content = dpl.read_bytes(c.path)
        fingerprint = dpl.sha256_bytes(content)

        if _fingerprint_exists(
            conn,
            source=args.source,
            symbol=c.symbol,
            page_type=c.page_type,
            fingerprint=fingerprint,
        ):
            counters["duplicates"] += 1
            _log_event(
                log_path,
                {
                    "event": "duplicate",
                    "source": args.source,
                    "symbol": c.symbol,
                    "page_type": c.page_type,
                    "fingerprint": fingerprint,
                    "candidate_path": c.path.as_posix(),
                },
            )
            continue

        latest_ts = _latest_capture_ts(conn, source=args.source, symbol=c.symbol, page_type=c.page_type)
        if latest_ts and args.freshness_minutes > 0:
            age = datetime.now(timezone.utc) - latest_ts
            if age < timedelta(minutes=args.freshness_minutes):
                counters["skipped_fresh"] += 1
                _log_event(
                    log_path,
                    {
                        "event": "skipped_fresh",
                        "source": args.source,
                        "symbol": c.symbol,
                        "page_type": c.page_type,
                        "fingerprint": fingerprint,
                        "candidate_path": c.path.as_posix(),
                        "latest_capture_ts_utc": latest_ts.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                        "freshness_minutes": int(args.freshness_minutes),
                    },
                )
                continue

        ts = datetime.now(timezone.utc)
        day = ts.strftime("%Y%m%d")
        raw_rel = Path(c.symbol) / c.page_type / day / f"{ts.strftime('%H%M%S')}_{fingerprint[:8]}.{c.ext}"
        raw_path = raw_dir / raw_rel

        if not args.dry_run:
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(c.path, raw_path)
            _persist_capture(
                conn,
                source=args.source,
                symbol=c.symbol,
                page_type=c.page_type,
                payload_format=c.ext,
                payload_bytes=len(content),
                fingerprint=fingerprint,
                raw_path=raw_path,
            )

        counters["captured"] += 1
        _log_event(
            log_path,
            {
                "event": "captured",
                "source": args.source,
                "symbol": c.symbol,
                "page_type": c.page_type,
                "fingerprint": fingerprint,
                "raw_path": raw_path.as_posix(),
            },
        )

    retention = _apply_retention(
        conn,
        raw_dir,
        retention_days=args.retention_days,
        max_store_mb=args.max_store_mb,
        log_path=log_path,
    )
    if retention["pruned_ttl"] or retention["pruned_cap"]:
        _log_event(
            log_path,
            {
                "event": "pruned",
                "source": args.source,
                "pruned_ttl": retention["pruned_ttl"],
                "pruned_cap": retention["pruned_cap"],
                "pruned_bytes": retention["pruned_bytes"],
            },
        )

    bytes_on_disk = sum(p.stat().st_size for p in raw_dir.rglob('*') if p.is_file()) if raw_dir.exists() else 0

    summary = {
        **counters,
        **retention,
        "source": args.source,
        "db": db_path.as_posix(),
        "raw_dir": raw_dir.as_posix(),
        "bytes_on_disk": int(bytes_on_disk),
    }
    conn.close()
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="capture_pages")
    p.add_argument("--source", default="ibkr_demo")
    p.add_argument("--source-dir", default=str(dpl.DATA_ROOT / "inbox"))
    p.add_argument("--store-dir", default=str(dpl.DEFAULT_RAW_DIR))
    p.add_argument("--db", default=str(dpl.DEFAULT_DB))
    p.add_argument("--symbols", default="")
    p.add_argument("--page-types", default="")
    p.add_argument("--freshness-minutes", type=int, default=60)
    p.add_argument("--retention-days", type=int, default=30)
    p.add_argument("--max-store-mb", type=int, default=2048)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-path", default=str(dpl.DEFAULT_LOG_DIR / "capture.jsonl"))
    p.add_argument("--format", choices=["line", "json"], default="line")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_capture(args)
    except RuntimeError as exc:
        print(f"CAPTURE_PAGES FAIL reason={exc}")
        return 2

    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            "CAPTURE_PAGES "
            f"total={summary['total']} captured={summary['captured']} filtered={summary['filtered']} "
            f"duplicates={summary['duplicates']} skipped_fresh={summary['skipped_fresh']} "
            f"pruned_ttl={summary['pruned_ttl']} pruned_cap={summary['pruned_cap']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())




