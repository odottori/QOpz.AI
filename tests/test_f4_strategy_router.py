"""Tests for strategy router: tier × regime → eligible strategies."""
import pytest
from strategy.router import select_strategies, strategy_eligible
from strategy.tier_config import TierConfigError


class TestSelectStrategies:
    # ── SHOCK ────────────────────────────────────────────────────────────────
    def test_shock_returns_empty(self):
        for tier in ["MICRO", "SMALL", "MEDIUM", "ADVANCED"]:
            assert select_strategies(tier, tier, "SHOCK") == []

    # ── MICRO ─────────────────────────────────────────────────────────────────
    def test_micro_normal(self):
        result = select_strategies("MICRO", "MICRO", "NORMAL")
        assert result == ["bull_put"]

    def test_micro_caution(self):
        result = select_strategies("MICRO", "MICRO", "CAUTION")
        assert result == ["bull_put"]  # bull_put is directional, allowed in CAUTION

    # ── SMALL ─────────────────────────────────────────────────────────────────
    def test_small_normal(self):
        result = select_strategies("SMALL", "SMALL", "NORMAL")
        assert "bull_put" in result
        assert "iron_condor" in result
        assert "wheel" in result

    def test_small_caution_suspends_ic_and_wheel(self):
        result = select_strategies("SMALL", "SMALL", "CAUTION")
        assert "bull_put" in result
        assert "iron_condor" not in result
        assert "wheel" not in result

    # ── active_mode < capital_tier ───────────────────────────────────────────
    def test_active_micro_with_small_capital(self):
        # capital_tier=SMALL but active_mode=MICRO -> only MICRO strategies
        result = select_strategies("SMALL", "MICRO", "NORMAL")
        assert result == ["bull_put"]

    def test_active_small_with_advanced_capital(self):
        result = select_strategies("ADVANCED", "SMALL", "NORMAL")
        assert set(result) == {"bull_put", "iron_condor", "wheel"}

    # ── validation ──────────────────────────────────────────────────────────
    def test_active_above_capital_raises(self):
        with pytest.raises(TierConfigError, match="exceeds capital_tier"):
            select_strategies("MICRO", "SMALL", "NORMAL")

    def test_unknown_regime_raises(self):
        with pytest.raises(ValueError):
            select_strategies("SMALL", "SMALL", "PANIC")

    # ── result is sorted ─────────────────────────────────────────────────────
    def test_result_is_sorted(self):
        result = select_strategies("ADVANCED", "ADVANCED", "NORMAL")
        assert result == sorted(result)


class TestStrategyEligible:
    def test_bull_put_eligible_in_micro(self):
        assert strategy_eligible("bull_put", "MICRO", "MICRO", "NORMAL") is True

    def test_iron_condor_not_eligible_in_micro(self):
        assert strategy_eligible("iron_condor", "SMALL", "MICRO", "NORMAL") is False

    def test_iron_condor_eligible_in_small_normal(self):
        assert strategy_eligible("iron_condor", "SMALL", "SMALL", "NORMAL") is True

    def test_iron_condor_not_eligible_in_small_caution(self):
        assert strategy_eligible("iron_condor", "SMALL", "SMALL", "CAUTION") is False

    def test_wheel_eligible_in_small_normal(self):
        assert strategy_eligible("wheel", "SMALL", "SMALL", "NORMAL") is True

    def test_nothing_eligible_in_shock(self):
        assert strategy_eligible("bull_put", "ADVANCED", "ADVANCED", "SHOCK") is False
