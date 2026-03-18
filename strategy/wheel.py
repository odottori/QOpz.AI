"""
Wheel Strategy — Cash-Secured Put → Covered Call state machine.

State flow:
    IDLE
      └─ open_csp()      → OPEN_CSP   (sell cash-secured put)
           ├─ expire()   → IDLE        (put expired OTM: collect premium, repeat)
           └─ assign()   → ASSIGNED    (put exercised: receive shares at csp_strike)
                └─ open_cc()  → OPEN_CC  (sell covered call at/above cost_basis)
                      ├─ expire_cc()  → ASSIGNED   (call expired OTM: sell another CC)
                      └─ call_away()  → IDLE        (shares called away: full cycle done)

Tier eligibility: SMALL and above.
Sizing: adaptive_fixed_fractional (pre-Kelly) for SMALL; Kelly gate applies at MEDIUM+.
Human confirmation required before any order transition (invariant).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from execution.ibkr_combo import (
    CspPlan,
    CoveredCallPlan,
    build_csp_plan,
    build_covered_call_plan,
)


class WheelState(str, Enum):
    IDLE = "IDLE"
    OPEN_CSP = "OPEN_CSP"       # cash-secured put open
    ASSIGNED = "ASSIGNED"        # shares held at csp_strike cost basis
    OPEN_CC = "OPEN_CC"          # covered call open against shares
    CLOSED = "CLOSED"            # full cycle completed (terminal — create new position)


@dataclass
class WheelPosition:
    """Tracks one full Wheel cycle for a single underlying."""

    symbol: str
    state: WheelState = WheelState.IDLE

    # CSP leg
    csp_strike: Optional[float] = None
    csp_expiry: Optional[str] = None       # YYYYMMDD
    csp_premium_received: float = 0.0

    # Assignment
    shares: int = 0
    cost_basis: Optional[float] = None     # csp_strike (what we paid for shares)

    # CC leg
    cc_strike: Optional[float] = None
    cc_expiry: Optional[str] = None        # YYYYMMDD
    cc_premium_received: float = 0.0

    # Cycle accounting
    total_premium_collected: float = 0.0
    cycle_count: int = 0                   # number of CC legs sold on this assignment

    def open_csp(
        self,
        *,
        strike: float,
        expiry: str,
        premium: float,
        shares: int = 100,
    ) -> None:
        """
        Transition IDLE → OPEN_CSP.
        `premium` is the net credit received (per share, x100 for contract value).
        Human confirmation must occur before calling this.
        """
        if self.state != WheelState.IDLE:
            raise ValueError(f"open_csp requires IDLE state, got {self.state}")
        self.csp_strike = float(strike)
        self.csp_expiry = str(expiry)
        self.csp_premium_received = float(premium)
        self.shares = int(shares)
        self.state = WheelState.OPEN_CSP

    def expire_csp(self) -> None:
        """
        Transition OPEN_CSP → IDLE: put expired worthless (OTM).
        Collect full premium, reset for next CSP.
        """
        if self.state != WheelState.OPEN_CSP:
            raise ValueError(f"expire_csp requires OPEN_CSP state, got {self.state}")
        self.total_premium_collected += self.csp_premium_received
        self._reset_csp_fields()
        self.state = WheelState.IDLE

    def assign(self) -> None:
        """
        Transition OPEN_CSP → ASSIGNED: put exercised (ITM at expiry).
        Shares assigned at csp_strike; cost basis = strike - csp_premium_received.
        """
        if self.state != WheelState.OPEN_CSP:
            raise ValueError(f"assign requires OPEN_CSP state, got {self.state}")
        self.cost_basis = self.csp_strike  # gross cost; net = strike - premium
        self.total_premium_collected += self.csp_premium_received
        self.state = WheelState.ASSIGNED

    def open_cc(
        self,
        *,
        strike: float,
        expiry: str,
        premium: float,
    ) -> None:
        """
        Transition ASSIGNED → OPEN_CC.
        Strike should be >= cost_basis to avoid selling at a loss.
        Human confirmation must occur before calling this.
        """
        if self.state != WheelState.ASSIGNED:
            raise ValueError(f"open_cc requires ASSIGNED state, got {self.state}")
        if self.cost_basis is not None and float(strike) < self.cost_basis:
            raise ValueError(
                f"CC strike {strike} < cost_basis {self.cost_basis}: "
                "selling below cost locks in a loss — operator must override explicitly."
            )
        self.cc_strike = float(strike)
        self.cc_expiry = str(expiry)
        self.cc_premium_received = float(premium)
        self.cycle_count += 1
        self.state = WheelState.OPEN_CC

    def expire_cc(self) -> None:
        """
        Transition OPEN_CC → ASSIGNED: call expired OTM.
        Keep shares, collect CC premium, ready to sell another CC.
        """
        if self.state != WheelState.OPEN_CC:
            raise ValueError(f"expire_cc requires OPEN_CC state, got {self.state}")
        self.total_premium_collected += self.cc_premium_received
        self._reset_cc_fields()
        self.state = WheelState.ASSIGNED

    def call_away(self) -> None:
        """
        Transition OPEN_CC → CLOSED: call exercised, shares called away at cc_strike.
        Full cycle complete — realized gain = (cc_strike - cost_basis) * shares + total_premium.
        """
        if self.state != WheelState.OPEN_CC:
            raise ValueError(f"call_away requires OPEN_CC state, got {self.state}")
        self.total_premium_collected += self.cc_premium_received
        self.state = WheelState.CLOSED

    # ── accounting helpers ──────────────────────────────────────────────────

    def realized_pnl(self) -> Optional[float]:
        """
        Total P&L for completed cycle (CLOSED state only).
        = (cc_strike - cost_basis) * shares + total_premium_collected * shares_per_contract
        """
        if self.state != WheelState.CLOSED:
            return None
        if self.cost_basis is None or self.cc_strike is None:
            return None
        capital_gain = (self.cc_strike - self.cost_basis) * self.shares
        premium_gain = self.total_premium_collected * 100  # per contract (100 shares)
        return capital_gain + premium_gain

    def unrealized_cost_basis_per_share(self) -> Optional[float]:
        """
        Effective cost basis after subtracting all collected premium.
        = cost_basis - total_premium_collected
        """
        if self.cost_basis is None:
            return None
        return self.cost_basis - self.total_premium_collected

    # ── combo plan helpers ──────────────────────────────────────────────────

    def to_csp_plan(
        self,
        *,
        strike: float,
        expiry: str,
        quantity: int = 1,
    ) -> "CspPlan":
        """
        Return a CspPlan ready for broker submission (state must be IDLE).
        Caller must confirm with operator before submitting.
        Does NOT transition state — call open_csp() after confirmation + fill.
        """
        if self.state != WheelState.IDLE:
            raise ValueError(f"to_csp_plan requires IDLE state, got {self.state}")
        return build_csp_plan(
            symbol=self.symbol,
            expiry=expiry,
            strike=strike,
            quantity=quantity,
        )

    def to_cc_plan(
        self,
        *,
        strike: float,
        expiry: str,
        quantity: int = 1,
    ) -> "CoveredCallPlan":
        """
        Return a CoveredCallPlan ready for broker submission (state must be ASSIGNED).
        Validates strike >= cost_basis. Caller must confirm with operator before submitting.
        Does NOT transition state — call open_cc() after confirmation + fill.
        """
        if self.state != WheelState.ASSIGNED:
            raise ValueError(f"to_cc_plan requires ASSIGNED state, got {self.state}")
        return build_covered_call_plan(
            symbol=self.symbol,
            expiry=expiry,
            strike=strike,
            quantity=quantity,
            cost_basis=self.cost_basis,
        )

    # ── internal ────────────────────────────────────────────────────────────

    def _reset_csp_fields(self) -> None:
        self.csp_strike = None
        self.csp_expiry = None
        self.csp_premium_received = 0.0
        self.shares = 0
        self.cost_basis = None

    def _reset_cc_fields(self) -> None:
        self.cc_strike = None
        self.cc_expiry = None
        self.cc_premium_received = 0.0
