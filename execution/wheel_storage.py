"""
Wheel strategy persistence — DuckDB storage.

Tables:
  wheel_positions        current state of every WheelPosition (upsert by position_id)
  wheel_position_events  append-only event trail per position (invariant: every
                         state transition produces one row)

Follows storage.py conventions:
  - _prov() provenance tuple on every INSERT
  - init_wheel_schema() idempotent (CREATE TABLE IF NOT EXISTS)
  - no auto-execution; callers own the WheelPosition lifecycle
"""
from __future__ import annotations

import importlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from execution.storage import _connect, _prov, init_execution_schema, utc_now
from strategy.wheel import WheelPosition, WheelState

logger = logging.getLogger(__name__)


# ── schema ───────────────────────────────────────────────────────────────────

_WHEEL_SCHEMA_READY = False


def init_wheel_schema() -> None:
    """Create wheel tables if they do not exist (idempotent)."""
    global _WHEEL_SCHEMA_READY
    if _WHEEL_SCHEMA_READY:
        return
    init_execution_schema()  # ensure base schema is present
    con = _connect()

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS wheel_positions (
            position_id             VARCHAR PRIMARY KEY,
            run_id                  VARCHAR,
            profile                 VARCHAR,
            symbol                  VARCHAR NOT NULL,
            state                   VARCHAR NOT NULL,
            csp_strike              DOUBLE,
            csp_expiry              VARCHAR,
            csp_premium_received    DOUBLE,
            shares                  INTEGER,
            cost_basis              DOUBLE,
            cc_strike               DOUBLE,
            cc_expiry               VARCHAR,
            cc_premium_received     DOUBLE,
            total_premium_collected DOUBLE,
            cycle_count             INTEGER,
            created_at              VARCHAR,
            updated_at              VARCHAR,
            source_system           VARCHAR,
            source_mode             VARCHAR,
            source_quality          VARCHAR,
            asof_ts                 VARCHAR,
            received_ts             VARCHAR
        )
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS wheel_position_events (
            event_id    VARCHAR PRIMARY KEY,
            position_id VARCHAR NOT NULL,
            run_id      VARCHAR,
            profile     VARCHAR,
            symbol      VARCHAR,
            prev_state  VARCHAR,
            new_state   VARCHAR NOT NULL,
            event_type  VARCHAR NOT NULL,
            ts_utc      VARCHAR,
            details_json VARCHAR,
            source_system  VARCHAR,
            source_mode    VARCHAR,
            source_quality VARCHAR,
            asof_ts        VARCHAR,
            received_ts    VARCHAR
        )
        """
    )

    con.close()
    _WHEEL_SCHEMA_READY = True


# ── save / load ───────────────────────────────────────────────────────────────

def save_wheel_position(
    pos: WheelPosition,
    *,
    position_id: str,
    profile: str,
    run_id: str,
    prev_state: Optional[WheelState] = None,
    event_type: str = "state_transition",
    details: Optional[str] = None,
) -> None:
    """
    Upsert WheelPosition into wheel_positions and append an event row.

    Args:
        pos:          the WheelPosition to persist
        position_id:  stable UUID identifying this position (caller owns it)
        profile:      config profile (dev / paper / live)
        run_id:       current run UUID
        prev_state:   state before transition (None for initial save)
        event_type:   label for the event row (e.g. "open_csp", "assign")
        details:      optional JSON string with extra context
    """
    init_wheel_schema()
    now = utc_now()
    prov = _prov(profile, now)  # (source_system, source_mode, source_quality, asof_ts, received_ts)
    ts = now.isoformat().replace("+00:00", "Z")

    con = _connect()
    try:
        con.execute("BEGIN")
        # Upsert wheel_positions (INSERT OR REPLACE semantics via DELETE+INSERT)
        con.execute("DELETE FROM wheel_positions WHERE position_id = ?", (position_id,))
        con.execute(
            """
            INSERT INTO wheel_positions (
                position_id, run_id, profile, symbol, state,
                csp_strike, csp_expiry, csp_premium_received,
                shares, cost_basis,
                cc_strike, cc_expiry, cc_premium_received,
                total_premium_collected, cycle_count,
                created_at, updated_at,
                source_system, source_mode, source_quality, asof_ts, received_ts
            ) VALUES (?,?,?,?,?, ?,?,?, ?,?, ?,?,?, ?,?, ?,?, ?,?,?,?,?)
            """,
            (
                position_id, run_id, profile, pos.symbol, pos.state.value,
                pos.csp_strike, pos.csp_expiry, pos.csp_premium_received,
                pos.shares, pos.cost_basis,
                pos.cc_strike, pos.cc_expiry, pos.cc_premium_received,
                pos.total_premium_collected, pos.cycle_count,
                ts, ts,
                *prov,
            ),
        )

        # Append event row
        con.execute(
            """
            INSERT INTO wheel_position_events (
                event_id, position_id, run_id, profile, symbol,
                prev_state, new_state, event_type, ts_utc, details_json,
                source_system, source_mode, source_quality, asof_ts, received_ts
            ) VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?)
            """,
            (
                str(uuid.uuid4()), position_id, run_id, profile, pos.symbol,
                prev_state.value if prev_state else None,
                pos.state.value, event_type, ts, details,
                *prov,
            ),
        )
        con.execute("COMMIT")
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        try:
            con.close()
        except Exception:
            pass


def load_wheel_position(
    position_id: str,
    *,
    profile: str,
) -> Optional[WheelPosition]:
    """
    Load a WheelPosition from DB by position_id.
    Returns None if not found or if DB is temporarily unavailable.
    """
    global _WHEEL_SCHEMA_READY
    try:
        init_wheel_schema()
    except Exception as exc:
        logger.warning("wheel_storage: init failed in load_wheel_position (%s) — returning None", exc)
        return None
    try:
        con = _connect()
        rows = con.execute(
            "SELECT * FROM wheel_positions WHERE position_id = ? AND profile = ?",
            (position_id, profile),
        ).fetchall()
        cols = [d[0] for d in con.description]
        con.close()
    except Exception as exc:
        logger.warning("wheel_storage: load_wheel_position query failed (%s) — returning None", exc)
        _WHEEL_SCHEMA_READY = False
        return None

    if not rows:
        return None

    row = dict(zip(cols, rows[0]))
    return _row_to_wheel_position(row)


def list_wheel_positions(
    *,
    profile: str,
    symbol: Optional[str] = None,
    state: Optional[WheelState] = None,
) -> list[tuple[str, WheelPosition]]:
    """
    Return list of (position_id, WheelPosition) matching filters.
    Excludes CLOSED positions by default unless state=WheelState.CLOSED is passed.
    Returns empty list if DB is locked or schema not yet ready (graceful degradation).
    """
    global _WHEEL_SCHEMA_READY

    # Ensure schema is ready; if a previous attempt failed (e.g. DB was locked),
    # _WHEEL_SCHEMA_READY stays False and we retry here.
    try:
        init_wheel_schema()
    except Exception as exc:
        logger.warning("wheel_storage: init_wheel_schema failed (%s) — returning empty list", exc)
        return []

    where = ["profile = ?"]
    params: list = [profile]

    if symbol is not None:
        where.append("symbol = ?")
        params.append(symbol)

    if state is not None:
        where.append("state = ?")
        params.append(state.value)
    else:
        where.append("state != 'CLOSED'")

    sql = f"SELECT * FROM wheel_positions WHERE {' AND '.join(where)} ORDER BY updated_at DESC"
    try:
        con = _connect()
        rows = con.execute(sql, params).fetchall()
        cols = [d[0] for d in con.description]
        con.close()
    except Exception as exc:
        # Table may not exist yet if schema init ran on a locked DB — reset flag so next
        # call retries CREATE TABLE, and return empty for now.
        logger.warning("wheel_storage: list_wheel_positions query failed (%s) — resetting schema flag", exc)
        _WHEEL_SCHEMA_READY = False
        return []

    result = []
    for row in rows:
        d = dict(zip(cols, row))
        pos = _row_to_wheel_position(d)
        result.append((d["position_id"], pos))
    return result


# ── internals ─────────────────────────────────────────────────────────────────

def _row_to_wheel_position(row: dict) -> WheelPosition:
    pos = WheelPosition(symbol=row["symbol"])
    pos.state = WheelState(row["state"])
    pos.csp_strike = row["csp_strike"]
    pos.csp_expiry = row["csp_expiry"]
    pos.csp_premium_received = float(row["csp_premium_received"] or 0.0)
    pos.shares = int(row["shares"] or 0)
    pos.cost_basis = row["cost_basis"]
    pos.cc_strike = row["cc_strike"]
    pos.cc_expiry = row["cc_expiry"]
    pos.cc_premium_received = float(row["cc_premium_received"] or 0.0)
    pos.total_premium_collected = float(row["total_premium_collected"] or 0.0)
    pos.cycle_count = int(row["cycle_count"] or 0)
    return pos
