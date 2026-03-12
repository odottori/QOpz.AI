from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from .storage import init_execution_schema, _connect
from .outcome import ExecutionOutcome


def reconcile(run_id: Optional[str] = None, report_path: Optional[str] = None) -> dict[str, Any]:
    """Reconcile execution ledger and event trail.

    Canonical invariants (derived from canonici/02_TEST.md F3-T3/F3-T4):
      - No orders should remain pending (NEW/SUBMITTED) at end-of-run.
      - Every order must have at least 1 event.
      - Latest event new_state (if present) should match orders.state.

    Parameters
    ----------
    run_id:
        If provided, scope reconcile checks to a single run_id.
    report_path:
        If provided, write reconcile result JSON to this path (runtime artifact; typically under reports/).
        If omitted, no file is written.

    Returns
    -------
    dict
        Reconcile summary with ok flag and details.
    """
    init_execution_schema()
    con = _connect()

    where = ""
    params: tuple[Any, ...] = ()
    if run_id:
        where = "WHERE o.run_id = ?"
        params = (run_id,)

    # Missing events for orders in scope
    missing_events = con.execute(f"""
        SELECT o.client_order_id, o.state
        FROM orders o
        LEFT JOIN order_events e ON e.client_order_id = o.client_order_id
        {where}
        AND e.client_order_id IS NULL
    """, params).fetchall() if run_id else con.execute("""
        SELECT o.client_order_id, o.state
        FROM orders o
        LEFT JOIN order_events e ON e.client_order_id = o.client_order_id
        WHERE e.client_order_id IS NULL
    """).fetchall()

    # Pending orders in scope
    pending = con.execute(f"""
        SELECT client_order_id, state, updated_at
        FROM orders o
        {where}
        AND state IN ('NEW','SUBMITTED')
    """, params).fetchall() if run_id else con.execute("""
        SELECT client_order_id, state, updated_at
        FROM orders
        WHERE state IN ('NEW','SUBMITTED')
    """).fetchall()

    # State mismatches in scope
    if run_id:
        mismatches = con.execute("""
            WITH scoped AS (
              SELECT client_order_id
              FROM orders
              WHERE run_id = ?
            ),
            latest AS (
              SELECT e.client_order_id, MAX(e.ts_utc) AS mx
              FROM order_events e
              JOIN scoped s ON s.client_order_id = e.client_order_id
              GROUP BY e.client_order_id
            )
            SELECT o.client_order_id, o.state AS order_state, e.new_state AS event_state, e.event_type, e.ts_utc
            FROM orders o
            JOIN latest l ON l.client_order_id = o.client_order_id
            JOIN order_events e ON e.client_order_id = l.client_order_id AND e.ts_utc = l.mx
            WHERE o.run_id = ? AND e.new_state IS NOT NULL AND o.state <> e.new_state
        """, (run_id, run_id)).fetchall()
    else:
        mismatches = con.execute("""
            WITH latest AS (
              SELECT client_order_id, MAX(ts_utc) AS mx
              FROM order_events
              GROUP BY client_order_id
            )
            SELECT o.client_order_id, o.state AS order_state, e.new_state AS event_state, e.event_type, e.ts_utc
            FROM orders o
            JOIN latest l ON l.client_order_id = o.client_order_id
            JOIN order_events e ON e.client_order_id = l.client_order_id AND e.ts_utc = l.mx
            WHERE e.new_state IS NOT NULL AND o.state <> e.new_state
        """).fetchall()

    con.close()

    # Outcome invariants (Domain 2.8): terminal orders must have outcome set and coherent.
    con = _connect()
    if run_id:
        missing_outcome = con.execute(
            """
            SELECT client_order_id, state
            FROM orders
            WHERE run_id = ? AND state IN ('REJECTED','FILLED','CANCELLED') AND (outcome IS NULL OR outcome = '')
            """,
            (run_id,),
        ).fetchall()
        wrong_outcome = con.execute(
            """
            SELECT client_order_id, state, outcome
            FROM orders
            WHERE run_id = ?
              AND (
                (state='REJECTED' AND outcome <> 'REJECTED') OR
                (state='FILLED' AND outcome <> 'FILLED') OR
                (state='CANCELLED' AND outcome NOT IN ('CANCELLED','ABANDONED','TIMEOUT'))
              )
            """,
            (run_id,),
        ).fetchall()
    else:
        missing_outcome = con.execute(
            """
            SELECT client_order_id, state
            FROM orders
            WHERE state IN ('REJECTED','FILLED','CANCELLED') AND (outcome IS NULL OR outcome = '')
            """
        ).fetchall()
        wrong_outcome = con.execute(
            """
            SELECT client_order_id, state, outcome
            FROM orders
            WHERE (
              (state='REJECTED' AND outcome <> 'REJECTED') OR
              (state='FILLED' AND outcome <> 'FILLED') OR
              (state='CANCELLED' AND outcome NOT IN ('CANCELLED','ABANDONED','TIMEOUT'))
            )
            """
        ).fetchall()
    con.close()

    ok = (
        len(missing_events) == 0
        and len(mismatches) == 0
        and len(pending) == 0
        and len(missing_outcome) == 0
        and len(wrong_outcome) == 0
    )

    result: dict[str, Any] = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "run_id": run_id,
        "missing_events": [{"client_order_id": r[0], "order_state": r[1]} for r in missing_events],
        "pending_orders": [
            {"client_order_id": r[0], "state": r[1], "updated_at": str(r[2])}
            for r in pending
        ],
        "state_mismatches": [
            {
                "client_order_id": r[0],
                "order_state": r[1],
                "event_state": r[2],
                "event_type": r[3],
                "event_ts_utc": str(r[4]),
            }
            for r in mismatches
        ],
        "missing_outcome": [
            {"client_order_id": r[0], "state": r[1]} for r in missing_outcome
        ],
        "wrong_outcome": [
            {"client_order_id": r[0], "state": r[1], "outcome": r[2]} for r in wrong_outcome
        ],
    }

    if report_path:
        os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, sort_keys=True)

    return result
