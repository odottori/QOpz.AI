"""Tests for Wheel strategy state machine (CSP → CC)."""
import pytest
from strategy.wheel import WheelPosition, WheelState


@pytest.fixture
def pos():
    return WheelPosition(symbol="IWM")


class TestOpenCSP:
    def test_idle_to_open_csp(self, pos):
        pos.open_csp(strike=195.0, expiry="20260417", premium=1.50)
        assert pos.state == WheelState.OPEN_CSP
        assert pos.csp_strike == 195.0
        assert pos.csp_premium_received == 1.50

    def test_wrong_state_raises(self, pos):
        pos.open_csp(strike=195.0, expiry="20260417", premium=1.50)
        with pytest.raises(ValueError, match="IDLE"):
            pos.open_csp(strike=194.0, expiry="20260417", premium=1.20)


class TestExpireCSP:
    def test_csp_expires_otm(self, pos):
        pos.open_csp(strike=195.0, expiry="20260417", premium=1.50)
        pos.expire_csp()
        assert pos.state == WheelState.IDLE
        assert pos.total_premium_collected == 1.50
        assert pos.csp_strike is None  # reset

    def test_wrong_state_raises(self, pos):
        with pytest.raises(ValueError, match="OPEN_CSP"):
            pos.expire_csp()


class TestAssign:
    def test_assignment_sets_cost_basis(self, pos):
        pos.open_csp(strike=195.0, expiry="20260417", premium=1.50)
        pos.assign()
        assert pos.state == WheelState.ASSIGNED
        assert pos.cost_basis == 195.0
        assert pos.total_premium_collected == 1.50  # CSP premium banked

    def test_wrong_state_raises(self, pos):
        with pytest.raises(ValueError, match="OPEN_CSP"):
            pos.assign()


class TestOpenCC:
    def test_assigned_to_open_cc(self, pos):
        pos.open_csp(strike=195.0, expiry="20260417", premium=1.50)
        pos.assign()
        pos.open_cc(strike=196.0, expiry="20260515", premium=1.20)
        assert pos.state == WheelState.OPEN_CC
        assert pos.cc_strike == 196.0
        assert pos.cycle_count == 1

    def test_cc_below_cost_basis_raises(self, pos):
        pos.open_csp(strike=195.0, expiry="20260417", premium=1.50)
        pos.assign()
        with pytest.raises(ValueError, match="cost_basis"):
            pos.open_cc(strike=194.0, expiry="20260515", premium=0.80)

    def test_wrong_state_raises(self, pos):
        with pytest.raises(ValueError, match="ASSIGNED"):
            pos.open_cc(strike=196.0, expiry="20260515", premium=1.20)


class TestExpireCC:
    def test_cc_expires_otm_returns_to_assigned(self, pos):
        pos.open_csp(strike=195.0, expiry="20260417", premium=1.50)
        pos.assign()
        pos.open_cc(strike=196.0, expiry="20260515", premium=1.20)
        pos.expire_cc()
        assert pos.state == WheelState.ASSIGNED
        assert pos.total_premium_collected == 1.50 + 1.20
        assert pos.cc_strike is None

    def test_multiple_cc_cycles(self, pos):
        pos.open_csp(strike=195.0, expiry="20260417", premium=1.50)
        pos.assign()
        for i in range(3):
            pos.open_cc(strike=196.0 + i, expiry="20260515", premium=1.00)
            pos.expire_cc()
        assert pos.cycle_count == 3
        assert pos.total_premium_collected == pytest.approx(1.50 + 3 * 1.00)


class TestCallAway:
    def test_full_cycle_pnl(self, pos):
        pos.open_csp(strike=195.0, expiry="20260417", premium=1.50, shares=100)
        pos.assign()
        pos.open_cc(strike=200.0, expiry="20260515", premium=1.20)
        pos.call_away()
        assert pos.state == WheelState.CLOSED
        # capital_gain = (200 - 195) * 100 = 500
        # premium_gain = (1.50 + 1.20) * 100 = 270
        assert pos.realized_pnl() == pytest.approx(770.0)

    def test_wrong_state_raises(self, pos):
        with pytest.raises(ValueError, match="OPEN_CC"):
            pos.call_away()


class TestUnrealizedCostBasis:
    def test_reduces_with_premium(self, pos):
        pos.open_csp(strike=195.0, expiry="20260417", premium=1.50)
        pos.assign()
        # effective cost = 195 - 1.50 = 193.50
        assert pos.unrealized_cost_basis_per_share() == pytest.approx(193.50)
        pos.open_cc(strike=196.0, expiry="20260515", premium=1.20)
        pos.expire_cc()
        # effective cost = 195 - (1.50 + 1.20) = 192.30
        assert pos.unrealized_cost_basis_per_share() == pytest.approx(192.30)
