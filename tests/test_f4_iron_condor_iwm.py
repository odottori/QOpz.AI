"""Tests for Iron Condor 4-leg combo builder."""
import pytest
from execution.ibkr_combo import (
    IronCondorPlan,
    build_iron_condor_plan,
    default_iron_condor_credit,
)


class TestBuildIronCondorPlan:
    def test_valid_plan(self):
        plan = build_iron_condor_plan(
            symbol="IWM",
            expiry="20260417",
            put_long_strike=185.0,
            put_short_strike=190.0,
            call_short_strike=205.0,
            call_long_strike=210.0,
            quantity=1,
        )
        assert isinstance(plan, IronCondorPlan)
        assert plan.symbol == "IWM"
        assert plan.put_width == pytest.approx(5.0)
        assert plan.call_width == pytest.approx(5.0)
        assert plan.quantity == 1

    def test_strike_order_violation_raises(self):
        # put_short > call_short (inverted)
        with pytest.raises(ValueError, match="Strike order violation"):
            build_iron_condor_plan(
                symbol="IWM",
                expiry="20260417",
                put_long_strike=205.0,
                put_short_strike=210.0,
                call_short_strike=190.0,
                call_long_strike=195.0,
            )

    def test_equal_strikes_raises(self):
        with pytest.raises(ValueError, match="Strike order violation"):
            build_iron_condor_plan(
                symbol="IWM",
                expiry="20260417",
                put_long_strike=190.0,
                put_short_strike=190.0,  # same as put_long
                call_short_strike=205.0,
                call_long_strike=210.0,
            )

    def test_put_short_above_call_short_raises(self):
        with pytest.raises(ValueError, match="Strike order violation"):
            build_iron_condor_plan(
                symbol="IWM",
                expiry="20260417",
                put_long_strike=185.0,
                put_short_strike=210.0,  # > call_short
                call_short_strike=205.0,
                call_long_strike=215.0,
            )

    def test_asymmetric_wings(self):
        plan = build_iron_condor_plan(
            symbol="SPY",
            expiry="20260515",
            put_long_strike=480.0,
            put_short_strike=490.0,
            call_short_strike=520.0,
            call_long_strike=525.0,  # 5-wide call, 10-wide put
        )
        assert plan.put_width == pytest.approx(10.0)
        assert plan.call_width == pytest.approx(5.0)

    def test_quantity_default_is_one(self):
        plan = build_iron_condor_plan(
            symbol="IWM",
            expiry="20260417",
            put_long_strike=185.0,
            put_short_strike=190.0,
            call_short_strike=205.0,
            call_long_strike=210.0,
        )
        assert plan.quantity == 1


class TestDefaultIronCondorCredit:
    def test_credit_is_positive(self):
        plan = build_iron_condor_plan(
            symbol="IWM",
            expiry="20260417",
            put_long_strike=185.0,
            put_short_strike=190.0,
            call_short_strike=205.0,
            call_long_strike=210.0,
        )
        credit = default_iron_condor_credit(plan)
        assert credit > 0

    def test_credit_bounded(self):
        plan = build_iron_condor_plan(
            symbol="IWM",
            expiry="20260417",
            put_long_strike=185.0,
            put_short_strike=190.0,
            call_short_strike=205.0,
            call_long_strike=210.0,
        )
        credit = default_iron_condor_credit(plan)
        assert 0.10 <= credit <= 5.00

    def test_narrow_wing_gives_small_credit(self):
        plan = build_iron_condor_plan(
            symbol="IWM",
            expiry="20260417",
            put_long_strike=189.0,
            put_short_strike=190.0,  # 1-wide
            call_short_strike=205.0,
            call_long_strike=206.0,  # 1-wide
        )
        credit = default_iron_condor_credit(plan)
        assert credit == pytest.approx(0.20)  # 1 * 0.20
