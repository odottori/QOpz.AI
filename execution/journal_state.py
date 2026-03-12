from __future__ import annotations

import json
from dataclasses import dataclass

from execution.order_reducer import OrderEvent, reduce_events_to_state
from execution.storage import _connect


@dataclass(frozen=True)
class DerivedOrderState:
    client_order_id: str
    state: str


def derive_state_from_journal(
    client_order_id: str,
    *,
    initial_state: str = "NEW",
    strict_prev_state: bool = False,
) -> DerivedOrderState:
    """Derive deterministic order state from persisted journal events (D2.16).

    Opt-in integration glue built on the D2.15 reducer.
    This function does not affect Gate0 unless called explicitly.
    """
    con = _connect()
    rows = con.execute(
        """
        SELECT ts_utc, event_type, prev_state, new_state, details_json
        FROM order_events
        WHERE client_order_id = ?
        ORDER BY ts_utc ASC
        """,
        (client_order_id,),
    ).fetchall()

    events: list[OrderEvent] = []
    for ts_utc, event_type, prev_state, new_state, details_json in rows:
        details = None
        if details_json:
            try:
                details = json.loads(details_json)
            except Exception:
                details = None
        events.append(
            OrderEvent(
                ts_utc=ts_utc,
                event_type=str(event_type),
                prev_state=prev_state,
                new_state=new_state,
                details=details,
            )
        )

    state = reduce_events_to_state(
        events,
        initial_state=initial_state,
        strict_prev_state=strict_prev_state,
    )
    return DerivedOrderState(client_order_id=client_order_id, state=state)
