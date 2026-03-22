"""Boundary adapters for execution.

Goal (Domain 2): keep broker integration behind a stable interface.

Notes:
- `dev` uses a pure simulation adapter.
- `paper/live` adapters are allowed to be unavailable (expected in Gate0).
- Even when unavailable, we record a deterministic event trail in the execution journal
  (`orders` + `order_events`) so reconcile remains profile-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Dict, Any

from execution.ack import AckResult, AckStatus
from execution.outcome import ExecutionOutcome


class BrokerUnavailableError(RuntimeError):
    """Raised when a paper/live broker adapter is not configured or not available."""
    pass


@dataclass(frozen=True)
class SubmitResult:
    client_order_id: str
    run_id: str
    ack: AckResult
    broker_order_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ExecutionAdapter(Protocol):
    def submit_limit(
        self,
        *,
        symbol: str,
        side: str,
        qty: int,
        limit_price: float,
        run_id: str,
        client_order_id: str,
    ) -> SubmitResult:
        ...


class PaperLiveAdapterBase:
    """Base class for broker-backed adapters.

    Gate0 behavior (expected):
      - Always raises BrokerUnavailableError.
      - Writes a deterministic journal trail:
          order_events: SUBMIT_ATTEMPT, REJECTED_BROKER_UNAVAILABLE
          orders.state: REJECTED (outcome=REJECTED_BROKER_UNAVAILABLE)
    """

    def __init__(self, profile: str, reason: str = "broker adapter not configured") -> None:
        self._profile = profile
        self._reason = reason

    def submit_limit(
        self,
        *,
        symbol: str,
        side: str,
        qty: int,
        limit_price: float,
        run_id: str,
        client_order_id: str,
    ) -> SubmitResult:
        # Best-effort persistence; never mask the intended BrokerUnavailableError.
        try:
            from execution.storage import init_execution_schema, upsert_order, record_event

            init_execution_schema()
            upsert_order(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=self._profile,
                symbol=symbol,
                side=side,
                quantity=qty,
                state="SUBMITTED",
                limit_price=limit_price,
            )
            record_event(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=self._profile,
                event_type="SUBMIT_ATTEMPT",
                prev_state="NEW",
                new_state="SUBMITTED",
                details={"symbol": symbol, "side": side, "qty": qty, "limit_price": limit_price},
            )

            upsert_order(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=self._profile,
                symbol=symbol,
                side=side,
                quantity=qty,
                state="REJECTED",
                limit_price=limit_price,
                outcome=ExecutionOutcome.REJECTED_BROKER_UNAVAILABLE.value,
            )
            record_event(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=self._profile,
                event_type="REJECTED_BROKER_UNAVAILABLE",
                prev_state="SUBMITTED",
                new_state="REJECTED",
                details={"reason": self._reason, "profile": self._profile},
            )
        except Exception as _exc:  # best-effort — do not mask the real BrokerUnavailableError
            import logging as _log
            _log.getLogger(__name__).warning("record_event failed during broker-unavailable path: %s", _exc)

        raise BrokerUnavailableError(self._reason)


def make_unavailable_result(client_order_id: str, run_id: str, reason: str) -> SubmitResult:
    # Used only if caller wants a structured object instead of an exception.
    return SubmitResult(
        client_order_id=client_order_id,
        run_id=run_id,
        ack=AckResult(status=AckStatus.NO_ACK),
        broker_order_id=None,
        details={"reason": reason},
    )


class DevSimulationAdapter:
    """DEV adapter that routes submissions to the dry-run execution path.

    This implements the ExecutionAdapter protocol without requiring broker deps.
    """

    def submit_limit(
        self,
        *,
        symbol: str,
        side: str,
        qty: int,
        limit_price: float,
        run_id: str,
        client_order_id: str,
    ) -> SubmitResult:
        # Import locally to avoid import cycles at module load time.
        from execution.order_schema import Order
        from execution.dry_run_adapter import submit as dry_submit

        order = Order(symbol=symbol, side=side, quantity=qty)
        order.validate()
        resp = dry_submit(order, client_order_id, run_id=run_id, profile="dev")
        status = resp.get("status")
        ack = AckResult(status=AckStatus.ACKED) if status in ("ACCEPTED", "DEDUPLICATED") else AckResult(status=AckStatus.NO_ACK)
        return SubmitResult(
            client_order_id=client_order_id,
            run_id=run_id,
            ack=ack,
            broker_order_id=None,
            details={"status": status, "limit_price": limit_price},
        )


def make_adapter(profile: str, *, reason: str | None = None) -> ExecutionAdapter:
    """Select the execution adapter for the given profile."""
    p = (profile or "").lower()
    if p == "dev":
        return DevSimulationAdapter()
    if p in {"paper", "live"}:
        return PaperLiveAdapterBase(p, reason=reason or "Gate0: broker adapter not installed/configured")
    raise ValueError(f"Unknown profile: {profile!r}")
