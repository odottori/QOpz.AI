from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from .storage import init_execution_schema, order_exists, get_order_state, upsert_order, record_event
from .state_machine import normalize_state
from .execution_plan import select_execution_plan
from .outcome import ExecutionOutcome


def submit(order, client_order_id: str, *, run_id: str = "UNKNOWN", profile: str = "dev"):
    """Dry-run submit with idempotency + state/event persistence."""
    init_execution_schema()

    # NEW -> SUBMITTED on first time
    if order_exists(client_order_id):
        prev = get_order_state(client_order_id) or "SUBMITTED"
        # DEDUPLICATED is a terminal-ish result here
        upsert_order(
            client_order_id=client_order_id,
            run_id=run_id,
            profile=profile,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            state="DEDUPLICATED",
            outcome=ExecutionOutcome.DEDUPLICATED.value,
        )
        record_event(
            client_order_id=client_order_id,
            run_id=run_id,
            profile=profile,
            event_type="DEDUPLICATED",
            prev_state=prev,
            new_state="DEDUPLICATED",
            details={"order": asdict(order)},
        )
        return {"status": "DEDUPLICATED", "client_order_id": client_order_id}

    # First time: create order row and event
    upsert_order(
        client_order_id=client_order_id,
        run_id=run_id,
        profile=profile,
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        state="SUBMITTED",
    )
    record_event(
        client_order_id=client_order_id,
        run_id=run_id,
        profile=profile,
        event_type="SUBMITTED",
        prev_state="NEW",
        new_state="SUBMITTED",
        details={"order": asdict(order)},
    )

    # Ack trail (DEV): record a synthetic ack for observability.
    record_event(
        client_order_id=client_order_id,
        run_id=run_id,
        profile=profile,
        event_type="ACK",
        prev_state="SUBMITTED",
        new_state="SUBMITTED",
        details={"source": "dry_run"},
    )
    return {"status": "ACCEPTED", "client_order_id": client_order_id}


from .smart_ladder import build_smart_limit_ladder


def execute_smart_limit(
    order,
    client_order_id: str,
    *,
    run_id: str = "UNKNOWN",
    profile: str = "dev",
    bid: float,
    ask: float,
    tick: float = 0.01,
    spread_reject_pct: float = 0.10,
    spread_reject_abs: float | None = None,
    timeout_sec: int = 120,
    simulate_fill_step: int | None = None,
    simulate_timeout_step: int | None = None,
    simulate_no_ack: bool = False,
) -> dict:
    """Execute Smart Limit Order Ladder in dry-run mode.

    Canonical source: canonici/01_TECNICO.md T6.2

    Notes:
      - This is a DEV/dry-run executor: no sleeps; timeouts are simulated and recorded as events.
      - Order state remains SUBMITTED until terminal (FILLED/CANCELLED/REJECTED).
    """
    init_execution_schema()

    # Ensure order exists (submitted) for tracking. This is not destructive: creates if missing.
    if not order_exists(client_order_id):
        upsert_order(
            client_order_id=client_order_id,
            run_id=run_id,
            profile=profile,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            state="SUBMITTED",
        )
        record_event(
            client_order_id=client_order_id,
            run_id=run_id,
            profile=profile,
            event_type="SUBMITTED",
            prev_state="NEW",
            new_state="SUBMITTED",
            details={"order": asdict(order)},
        )

        # Ack trail (DEV): by default we record an immediate synthetic ACK.
        if not simulate_no_ack:
            record_event(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=profile,
                event_type="ACK",
                prev_state="SUBMITTED",
                new_state="SUBMITTED",
                details={"source": "dry_run"},
            )

    prev_state = get_order_state(client_order_id) or "SUBMITTED"

    # Guardrail: reject if spread too wide.
    # Canonical reference (02_TEST.md F3-T3): reject if spread > 10% of mid.
    plan = select_execution_plan(
        bid=float(bid),
        ask=float(ask),
        spread_reject_pct=float(spread_reject_pct),
        spread_reject_abs=(float(spread_reject_abs) if spread_reject_abs is not None else None),
        enable_twap=False,  # TWAP planning exists canonically but applicability is operational; keep off by default here.
    )

    if plan.kind == "REJECT":
        prev_state = get_order_state(client_order_id) or "SUBMITTED"
        upsert_order(
            client_order_id=client_order_id,
            run_id=run_id,
            profile=profile,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            state="REJECTED",
            outcome=ExecutionOutcome.REJECTED.value,
            limit_price=float(plan.details.get("mid", (float(bid) + float(ask)) / 2.0)),
        )
        record_event(
            client_order_id=client_order_id,
            run_id=run_id,
            profile=profile,
            event_type="REJECT_SPREAD",
            prev_state=prev_state,
            new_state="REJECTED",
            details={"reason": plan.reason, **plan.details},
        )
        record_event(
            client_order_id=client_order_id,
            run_id=run_id,
            profile=profile,
            event_type="OUTCOME_SET",
            prev_state="REJECTED",
            new_state="REJECTED",
            details={"outcome": ExecutionOutcome.REJECTED.value},
        )
        return {"status": "REJECTED", "reason": plan.reason, "client_order_id": client_order_id}


    ladder = build_smart_limit_ladder(bid=bid, ask=ask, tick=tick, timeout_sec=timeout_sec)

    for step in ladder:
        # Update ledger with the latest working limit price.
        upsert_order(
            client_order_id=client_order_id,
            run_id=run_id,
            profile=profile,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            state=prev_state,
            limit_price=float(step.limit_price),
        )
        record_event(
            client_order_id=client_order_id,
            run_id=run_id,
            profile=profile,
            event_type="LADDER_STEP_PLACED",
            prev_state=prev_state,
            new_state=prev_state,
            details={"step_no": step.step_no, "limit_price": step.limit_price, "timeout_sec": step.timeout_sec},
        )

        if simulate_fill_step is not None and int(simulate_fill_step) == int(step.step_no):
            limit_price = float(step.limit_price)
            fill_price = float(step.limit_price)
            slip = 0.0
            if limit_price not in (0.0, -0.0):
                slip = (fill_price - limit_price) / limit_price
            upsert_order(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=profile,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                state="FILLED",
                outcome=ExecutionOutcome.FILLED.value,
                limit_price=limit_price,
                fill_price=fill_price,
                slippage=slip,
            )
            record_event(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=profile,
                event_type="FILLED",
                prev_state=prev_state,
                new_state="FILLED",
                details={"step_no": step.step_no, "fill_price": step.limit_price},
            )
            record_event(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=profile,
                event_type="OUTCOME_SET",
                prev_state="FILLED",
                new_state="FILLED",
                details={"outcome": ExecutionOutcome.FILLED.value},
            )
            return {"status": "FILLED", "client_order_id": client_order_id, "fill_price": fill_price}

        # No fill -> timeout -> fallback
        record_event(
            client_order_id=client_order_id,
            run_id=run_id,
            profile=profile,
            event_type="LADDER_STEP_TIMEOUT",
            prev_state=prev_state,
            new_state=prev_state,
            details={"step_no": step.step_no, "timeout_sec": step.timeout_sec},
        )

        # Optional: simulate a terminal timeout classification (DEV only)
        if simulate_timeout_step is not None and int(simulate_timeout_step) == int(step.step_no):
            upsert_order(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=profile,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                state="CANCELLED",
                outcome=ExecutionOutcome.TIMEOUT.value,
            )
            record_event(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=profile,
                event_type="OUTCOME_SET",
                prev_state=prev_state,
                new_state="CANCELLED",
                details={"outcome": ExecutionOutcome.TIMEOUT.value, "step_no": step.step_no},
            )
            return {"status": "CANCELLED", "client_order_id": client_order_id, "reason": "TIMEOUT", "outcome": ExecutionOutcome.TIMEOUT.value}

    # Abbandono (Step 5)
    upsert_order(
        client_order_id=client_order_id,
        run_id=run_id,
        profile=profile,
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        state="CANCELLED",
        outcome=ExecutionOutcome.ABANDONED.value,
    )
    record_event(
        client_order_id=client_order_id,
        run_id=run_id,
        profile=profile,
        event_type="ABANDON",
        prev_state=prev_state,
        new_state="CANCELLED",
        details={"reason": "SMART_LADDER_EXHAUSTED"},
    )
    record_event(
        client_order_id=client_order_id,
        run_id=run_id,
        profile=profile,
        event_type="OUTCOME_SET",
        prev_state="CANCELLED",
        new_state="CANCELLED",
        details={"outcome": ExecutionOutcome.ABANDONED.value},
    )
    return {"status": "CANCELLED", "client_order_id": client_order_id, "reason": "ABANDON"}
