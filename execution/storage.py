from __future__ import annotations

import importlib
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .state_machine import normalize_state

EXEC_DB_PATH = Path("db/execution.duckdb")
_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()


def _duckdb():
    """Return duckdb module or raise if unavailable (DuckDB-only project policy)."""
    try:
        return importlib.import_module("duckdb")
    except ModuleNotFoundError as exc:
        raise RuntimeError("duckdb is required by project policy") from exc


def _connect():
    """Return a DuckDB connection (DuckDB-only)."""
    EXEC_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    duckdb = _duckdb()
    return duckdb.connect(str(EXEC_DB_PATH))


def init_execution_schema() -> None:
    global _SCHEMA_READY
    with _SCHEMA_LOCK:
        if _SCHEMA_READY and EXEC_DB_PATH.exists():
            return
        con = _connect()

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                client_order_id VARCHAR PRIMARY KEY,
                run_id VARCHAR,
                profile VARCHAR,
                symbol VARCHAR,
                side VARCHAR,
                quantity INTEGER,
                limit_price DOUBLE,
                fill_price DOUBLE,
                slippage DOUBLE,
                outcome VARCHAR,
                status VARCHAR,
                state VARCHAR,
                timestamp TIMESTAMP,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
            """
        )

        try:
            con.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS outcome VARCHAR")
        except Exception:
            pass

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS order_events (
                event_id VARCHAR PRIMARY KEY,
                client_order_id VARCHAR,
                run_id VARCHAR,
                profile VARCHAR,
                event_type VARCHAR,
                prev_state VARCHAR,
                new_state VARCHAR,
                ts_utc TIMESTAMP,
                details_json VARCHAR
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_equity_snapshots (
                snapshot_id VARCHAR PRIMARY KEY,
                profile VARCHAR,
                asof_date DATE,
                equity DOUBLE,
                note VARCHAR,
                created_at TIMESTAMP
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_trades (
                trade_id VARCHAR PRIMARY KEY,
                profile VARCHAR,
                symbol VARCHAR,
                strategy VARCHAR,
                entry_ts_utc TIMESTAMP,
                exit_ts_utc TIMESTAMP,
                strikes_json VARCHAR,
                regime_at_entry VARCHAR,
                score_at_entry DOUBLE,
                kelly_fraction DOUBLE,
                exit_reason VARCHAR,
                pnl DOUBLE,
                pnl_pct DOUBLE,
                slippage_ticks DOUBLE,
                violations INTEGER,
                note VARCHAR,
                created_at TIMESTAMP
            )
            """
        )
        try:
            con.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS strikes_json VARCHAR")
            con.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS regime_at_entry VARCHAR")
            con.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS score_at_entry DOUBLE")
            con.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS kelly_fraction DOUBLE")
            con.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS exit_reason VARCHAR")
        except Exception:
            pass

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS compliance_events (
                event_id VARCHAR PRIMARY KEY,
                profile VARCHAR,
                ts_utc TIMESTAMP,
                code VARCHAR,
                severity VARCHAR,
                details_json VARCHAR
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS operator_opportunity_decisions (
                decision_id VARCHAR PRIMARY KEY,
                profile VARCHAR,
                batch_id VARCHAR,
                symbol VARCHAR,
                strategy VARCHAR,
                score DOUBLE,
                regime VARCHAR,
                scanner_name VARCHAR,
                source VARCHAR,
                decision VARCHAR,
                confidence INTEGER,
                note VARCHAR,
                created_at TIMESTAMP
            )
            """
        )

        con.close()
        _SCHEMA_READY = True

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def record_event(
    *,
    client_order_id: str,
    run_id: str,
    profile: str,
    event_type: str,
    prev_state: str | None,
    new_state: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    import json

    con = _connect()
    ts = utc_now()
    try:
        con.execute(
            "INSERT INTO order_events (event_id, client_order_id, run_id, profile, event_type, prev_state, new_state, ts_utc, details_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                client_order_id,
                run_id,
                profile,
                event_type,
                prev_state,
                new_state,
                ts,
                None if details is None else json.dumps(details, ensure_ascii=False),
            ),
        )
        if hasattr(con, "commit"):
            con.commit()
    finally:
        con.close()

    # Best-effort JSONL event trail (runtime-only, gitignored via logs/)
    try:
        log_path = Path("logs") / "execution_events.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts_utc": ts.isoformat(),
            "client_order_id": client_order_id,
            "run_id": run_id,
            "profile": profile,
            "event_type": event_type,
            "prev_state": prev_state,
            "new_state": new_state,
            "details": details,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def upsert_order(
    *,
    client_order_id: str,
    run_id: str,
    profile: str,
    symbol: str,
    side: str,
    quantity: int,
    state: str,
    limit_price: float | None = None,
    fill_price: float | None = None,
    slippage: float | None = None,
    outcome: str | None = None,
) -> None:
    state = normalize_state(state)
    con = _connect()
    try:
        now = utc_now()
        status = state
        con.execute(
            """
            INSERT INTO orders (client_order_id, run_id, profile, symbol, side, quantity, limit_price, fill_price, slippage, outcome, status, state, timestamp, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (client_order_id) DO UPDATE SET
              run_id=excluded.run_id,
              profile=excluded.profile,
              symbol=excluded.symbol,
              side=excluded.side,
              quantity=excluded.quantity,
              limit_price=COALESCE(excluded.limit_price, orders.limit_price),
              fill_price=COALESCE(excluded.fill_price, orders.fill_price),
              slippage=COALESCE(excluded.slippage, orders.slippage),
              outcome=COALESCE(excluded.outcome, orders.outcome),
              status=excluded.status,
              state=excluded.state,
              timestamp=excluded.timestamp,
              updated_at=excluded.updated_at
            """,
            (
                client_order_id,
                run_id,
                profile,
                symbol,
                side,
                quantity,
                limit_price,
                fill_price,
                slippage,
                outcome,
                status,
                state,
                now,
                now,
                now,
            ),
        )
        if hasattr(con, "commit"):
            con.commit()
    finally:
        con.close()


def get_order_state(client_order_id: str) -> str | None:
    con = _connect()
    try:
        row = con.execute("SELECT state FROM orders WHERE client_order_id = ?", (client_order_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return None
    return row[0]


def order_exists(client_order_id: str) -> bool:
    return get_order_state(client_order_id) is not None

