from __future__ import annotations

"""
F1-T4 - DB integrity checks (system).

Checks (canonici/02_TEST.md):
- Primary keys unique
- Foreign key integrity (manual check)
- Timestamp coherence (parseable and reasonable range)
- Basic join query performance (<100ms on small synthetic dataset)

Notes:
- DuckDB-only project policy.
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb  # type: ignore


def _backend_name(con: Any) -> str:
    return type(con).__module__.split(".")[0]


def connect_duckdb(path: Path | str) -> Any:
    if isinstance(path, Path):
        path = str(path)
    return duckdb.connect(path)  # type: ignore


def connect(path: Path | str, *, backend: str = "duckdb") -> Any:
    """Return a DB connection.

    backend:
      - auto: alias for duckdb
      - duckdb: always duckdb
    """
    if backend in {"duckdb", "auto"}:
        return connect_duckdb(path)
    raise ValueError(f"unsupported backend for project policy: {backend}")


def _fetchall(con: Any, sql: str, params: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
    if params is None:
        params = ()
    cur = con.execute(sql, params)
    # DuckDB returns relation-like objects that support fetchall().
    try:
        return cur.fetchall()
    except Exception:
        return list(cur)  # pragma: no cover


def _scalar(con: Any, sql: str, params: tuple[Any, ...] | None = None) -> Any:
    rows = _fetchall(con, sql, params)
    return rows[0][0] if rows else None


@dataclass(frozen=True)
class IntegrityResult:
    ok: bool
    errors: list[str]
    report: dict[str, Any]


def check_pk_unique(con: Any, table: str, pk_expr: str) -> tuple[bool, dict[str, Any]]:
    total = int(_scalar(con, f"SELECT COUNT(*) FROM {table}") or 0)
    distinct = int(_scalar(con, f"SELECT COUNT(DISTINCT {pk_expr}) FROM {table}") or 0)
    ok = total == distinct
    return ok, {"table": table, "total": total, "distinct": distinct, "pk_expr": pk_expr}


def check_fk_order_events(con: Any) -> tuple[bool, dict[str, Any]]:
    # Manual referential check: order_events.client_order_id must exist in orders.client_order_id (ignoring NULLs)
    violations = int(
        _scalar(
            con,
            """
            SELECT COUNT(*)
            FROM order_events e
            LEFT JOIN orders o
              ON o.client_order_id = e.client_order_id
            WHERE e.client_order_id IS NOT NULL
              AND o.client_order_id IS NULL
            """,
        )
        or 0
    )
    return violations == 0, {"violations": violations}


def _parse_iso_dt(s: str) -> datetime:
    # accepts 'YYYY-MM-DD' or ISO with Z
    s = s.strip()
    if len(s) == 10:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def check_ts_range(con: Any, table: str, col: str) -> tuple[bool, dict[str, Any]]:
    rows = _fetchall(con, f"SELECT MIN({col}), MAX({col}) FROM {table}")
    mn, mx = rows[0] if rows else (None, None)
    if mn is None or mx is None:
        return True, {"table": table, "col": col, "min": None, "max": None, "range_days": 0, "empty": True}
    try:
        dmn = _parse_iso_dt(str(mn))
        dmx = _parse_iso_dt(str(mx))
        delta_days = (dmx - dmn).total_seconds() / 86400.0
    except Exception as e:
        return False, {"table": table, "col": col, "error": f"parse failed: {e}"}
    # sanity: non-negative and not absurdly large
    ok = delta_days >= 0 and delta_days <= 3650  # <= 10y
    return ok, {"table": table, "col": col, "min": str(mn), "max": str(mx), "range_days": float(delta_days)}


def check_join_perf(con: Any, *, target_ms: float = 100.0) -> tuple[bool, dict[str, Any]]:
    # execute a tiny join and time it; should be comfortably <100ms on small datasets
    t0 = time.perf_counter()
    _fetchall(
        con,
        """
        SELECT o.client_order_id, e.event_type
        FROM orders o
        JOIN order_events e
          ON o.client_order_id = e.client_order_id
        LIMIT 10
        """,
    )
    dt_ms = (time.perf_counter() - t0) * 1000.0
    ok = dt_ms <= target_ms
    return ok, {"elapsed_ms": dt_ms, "target_ms": target_ms}


def run_execution_integrity_checks(con: Any) -> IntegrityResult:
    errors: list[str] = []
    report: dict[str, Any] = {"backend": _backend_name(con), "scope": "execution"}

    ok_pk_orders, pk_orders = check_pk_unique(con, "orders", "client_order_id")
    ok_pk_events, pk_events = check_pk_unique(con, "order_events", "event_id")
    report["pk"] = {"orders": pk_orders, "order_events": pk_events}
    if not ok_pk_orders:
        errors.append("PK not unique: orders.client_order_id")
    if not ok_pk_events:
        errors.append("PK not unique: order_events.event_id")

    ok_fk, fk = check_fk_order_events(con)
    report["fk"] = fk
    if not ok_fk:
        errors.append(f"FK violations: {fk.get('violations')} order_events without parent orders")

    ok_ts_e, ts_e = check_ts_range(con, "order_events", "ts_utc")
    report["timestamps"] = {"order_events.ts_utc": ts_e}
    if not ok_ts_e:
        errors.append("Timestamp range invalid: order_events.ts_utc")

    ok_perf, perf = check_join_perf(con, target_ms=100.0)
    report["performance"] = perf
    if not ok_perf:
        errors.append(f"Join perf too slow: {perf.get('elapsed_ms'):.1f}ms > {perf.get('target_ms')}ms")

    return IntegrityResult(ok=(len(errors) == 0), errors=errors, report=report)


def seed_execution_synthetic(con: Any, *, n_orders: int = 500, events_per_order: int = 2) -> None:
    # Create minimal schema compatible with execution/storage.py.
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            client_order_id TEXT PRIMARY KEY,
            run_id TEXT,
            profile TEXT,
            symbol TEXT,
            side TEXT,
            quantity INTEGER,
            limit_price REAL,
            fill_price REAL,
            slippage REAL,
            outcome TEXT,
            status TEXT,
            state TEXT,
            timestamp TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS order_events (
            event_id TEXT PRIMARY KEY,
            client_order_id TEXT,
            run_id TEXT,
            profile TEXT,
            event_type TEXT,
            prev_state TEXT,
            new_state TEXT,
            ts_utc TEXT,
            details_json TEXT
        )
        """
    )
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    # insert orders + events
    for i in range(n_orders):
        oid = f"o{i:06d}"
        con.execute(
            "INSERT OR REPLACE INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (oid, "run0", "dev", "SPY", "BUY", 1, 1.0, 1.0, 0.0, None, "NEW", "NEW", now, now, now),
        )
        for j in range(events_per_order):
            eid = f"e{i:06d}_{j}"
            con.execute(
                "INSERT OR REPLACE INTO order_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (eid, oid, "run0", "dev", "EV", "S0", "S1", now, "{}"),
            )
    try:
        con.commit()
    except Exception:
        pass


def write_reports(outdir: Path, *, stem: str, payload: dict[str, Any]) -> tuple[Path, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    jp = outdir / f"{stem}.json"
    mp = outdir / f"{stem}.md"
    jp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        f"# {stem}",
        "",
        f"ok: {bool(payload.get('ok'))}",
        "",
    ]
    errs = payload.get("errors") or []
    if errs:
        lines.append("## errors")
        for e in errs:
            lines.append(f"- {e}")
        lines.append("")
    lines.append("## report")
    lines.append("```json")
    lines.append(json.dumps(payload.get("report") or {}, indent=2, sort_keys=True))
    lines.append("```")
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return jp, mp
