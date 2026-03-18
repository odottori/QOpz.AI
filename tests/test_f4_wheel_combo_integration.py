"""Tests for Wheel ↔ combo plan integration (CSP/CC builders)."""
import pytest
from execution.ibkr_combo import (
    CspPlan,
    CoveredCallPlan,
    build_csp_plan,
    build_covered_call_plan,
    default_csp_premium,
    default_cc_premium,
)
from strategy.wheel import WheelPosition, WheelState


# ── CspPlan builder ──────────────────────────────────────────────────────────

class TestBuildCspPlan:
    def test_basic(self):
        plan = build_csp_plan(symbol="IWM", expiry="20260417", strike=190.0)
        assert isinstance(plan, CspPlan)
        assert plan.symbol == "IWM"
        assert plan.strike == 190.0
        assert plan.quantity == 1

    def test_quantity(self):
        plan = build_csp_plan(symbol="IWM", expiry="20260417", strike=190.0, quantity=3)
        assert plan.quantity == 3

    def test_immutable(self):
        plan = build_csp_plan(symbol="IWM", expiry="20260417", strike=190.0)
        with pytest.raises(Exception):
            plan.strike = 200.0  # frozen dataclass


# ── CoveredCallPlan builder ──────────────────────────────────────────────────

class TestBuildCoveredCallPlan:
    def test_basic(self):
        plan = build_covered_call_plan(symbol="IWM", expiry="20260515", strike=195.0)
        assert isinstance(plan, CoveredCallPlan)
        assert plan.strike == 195.0

    def test_strike_above_cost_basis_ok(self):
        plan = build_covered_call_plan(
            symbol="IWM", expiry="20260515", strike=196.0, cost_basis=195.0
        )
        assert plan.strike == 196.0

    def test_strike_equal_cost_basis_ok(self):
        plan = build_covered_call_plan(
            symbol="IWM", expiry="20260515", strike=195.0, cost_basis=195.0
        )
        assert plan.strike == 195.0

    def test_strike_below_cost_basis_raises(self):
        with pytest.raises(ValueError, match="cost_basis"):
            build_covered_call_plan(
                symbol="IWM", expiry="20260515", strike=193.0, cost_basis=195.0
            )

    def test_no_cost_basis_no_check(self):
        # explicit override: cost_basis=None skips the guard
        plan = build_covered_call_plan(
            symbol="IWM", expiry="20260515", strike=180.0, cost_basis=None
        )
        assert plan.strike == 180.0


# ── Default premium estimates ─────────────────────────────────────────────────

class TestDefaultPremiums:
    def test_csp_premium_positive(self):
        assert default_csp_premium(190.0, 30) > 0

    def test_csp_premium_capped(self):
        p = default_csp_premium(190.0, 30)
        assert p <= 190.0 * 0.05

    def test_cc_premium_less_than_csp(self):
        # CC premium should be roughly half of CSP premium
        csp = default_csp_premium(190.0, 30)
        cc = default_cc_premium(190.0, 30)
        assert cc < csp

    def test_longer_dte_higher_premium(self):
        p30 = default_csp_premium(190.0, 30)
        p60 = default_csp_premium(190.0, 60)
        assert p60 > p30


# ── WheelPosition.to_csp_plan / to_cc_plan ───────────────────────────────────

class TestWheelToPlan:
    def test_to_csp_plan_from_idle(self):
        pos = WheelPosition(symbol="IWM")
        plan = pos.to_csp_plan(strike=190.0, expiry="20260417")
        assert isinstance(plan, CspPlan)
        assert plan.symbol == "IWM"
        assert plan.strike == 190.0
        assert pos.state == WheelState.IDLE  # no state change

    def test_to_csp_plan_wrong_state_raises(self):
        pos = WheelPosition(symbol="IWM")
        pos.open_csp(strike=190.0, expiry="20260417", premium=1.50)
        with pytest.raises(ValueError, match="IDLE"):
            pos.to_csp_plan(strike=190.0, expiry="20260417")

    def test_to_cc_plan_from_assigned(self):
        pos = WheelPosition(symbol="IWM")
        pos.open_csp(strike=190.0, expiry="20260417", premium=1.50)
        pos.assign()
        plan = pos.to_cc_plan(strike=192.0, expiry="20260515")
        assert isinstance(plan, CoveredCallPlan)
        assert plan.symbol == "IWM"
        assert plan.strike == 192.0
        assert pos.state == WheelState.ASSIGNED  # no state change

    def test_to_cc_plan_below_cost_basis_raises(self):
        pos = WheelPosition(symbol="IWM")
        pos.open_csp(strike=190.0, expiry="20260417", premium=1.50)
        pos.assign()
        with pytest.raises(ValueError, match="cost_basis"):
            pos.to_cc_plan(strike=188.0, expiry="20260515")

    def test_to_cc_plan_wrong_state_raises(self):
        pos = WheelPosition(symbol="IWM")
        with pytest.raises(ValueError, match="ASSIGNED"):
            pos.to_cc_plan(strike=192.0, expiry="20260515")

    def test_full_cycle_with_plans(self):
        """End-to-end: IDLE → CSP plan → open_csp → assign → CC plan → open_cc → call_away."""
        pos = WheelPosition(symbol="IWM")

        # Operator gets CSP plan, confirms, gets fill
        csp_plan = pos.to_csp_plan(strike=190.0, expiry="20260417")
        assert csp_plan.strike == 190.0
        pos.open_csp(strike=190.0, expiry="20260417", premium=1.50)

        # Put assigned
        pos.assign()

        # Operator gets CC plan, confirms, gets fill
        cc_plan = pos.to_cc_plan(strike=193.0, expiry="20260515")
        assert cc_plan.strike == 193.0
        pos.open_cc(strike=193.0, expiry="20260515", premium=1.20)

        # Shares called away
        pos.call_away()
        assert pos.state == WheelState.CLOSED
        assert pos.realized_pnl() == pytest.approx(
            (193.0 - 190.0) * 100 + (1.50 + 1.20) * 100
        )
