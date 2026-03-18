"""Tests for tier_config: load, validate, active_mode <= capital_tier."""
import pytest
from strategy.tier_config import (
    TIERS,
    load_tier_config,
    tier_rank,
    validate_tier_config,
    TierConfigError,
)


class TestTierRank:
    def test_ordering(self):
        assert tier_rank("MICRO") < tier_rank("SMALL") < tier_rank("MEDIUM") < tier_rank("ADVANCED")

    def test_case_insensitive(self):
        assert tier_rank("micro") == tier_rank("MICRO")

    def test_unknown_raises(self):
        with pytest.raises(TierConfigError):
            tier_rank("ULTRA")


class TestValidateTierConfig:
    def test_same_tier_ok(self):
        for t in TIERS:
            validate_tier_config(t, t)  # no error

    def test_active_below_capital_ok(self):
        validate_tier_config("SMALL", "MICRO")
        validate_tier_config("MEDIUM", "MICRO")
        validate_tier_config("ADVANCED", "SMALL")

    def test_active_above_capital_raises(self):
        with pytest.raises(TierConfigError, match="exceeds capital_tier"):
            validate_tier_config("MICRO", "SMALL")
        with pytest.raises(TierConfigError, match="exceeds capital_tier"):
            validate_tier_config("SMALL", "ADVANCED")

    def test_unknown_capital_raises(self):
        with pytest.raises(TierConfigError):
            validate_tier_config("NANO", "MICRO")

    def test_unknown_mode_raises(self):
        with pytest.raises(TierConfigError):
            validate_tier_config("MICRO", "NANO")


class TestLoadTierConfig:
    def test_defaults_when_no_tier_section(self):
        ct, am = load_tier_config({})
        assert ct == "MICRO"
        assert am == "MICRO"

    def test_loads_from_tier_section(self):
        cfg = {"tier": {"capital_tier": "SMALL", "active_mode": "MICRO"}}
        ct, am = load_tier_config(cfg)
        assert ct == "SMALL"
        assert am == "MICRO"

    def test_case_normalised(self):
        cfg = {"tier": {"capital_tier": "small", "active_mode": "micro"}}
        ct, am = load_tier_config(cfg)
        assert ct == "SMALL"
        assert am == "MICRO"

    def test_invalid_mode_raises(self):
        cfg = {"tier": {"capital_tier": "MICRO", "active_mode": "SMALL"}}
        with pytest.raises(TierConfigError):
            load_tier_config(cfg)
