"""
Tier configuration loader and validator.

capital_tier  = ceiling determined by deposited capital (e.g. "SMALL")
active_mode   = operator-selected operating mode (must be <= capital_tier)

Tier ordering: MICRO < SMALL < MEDIUM < ADVANCED
"""
from __future__ import annotations

from typing import Any

# Canonical tier ordering (lowest to highest)
TIERS: list[str] = ["MICRO", "SMALL", "MEDIUM", "ADVANCED"]

_TIER_RANK: dict[str, int] = {t: i for i, t in enumerate(TIERS)}


class TierConfigError(ValueError):
    pass


def tier_rank(tier: str) -> int:
    t = tier.upper().strip()
    if t not in _TIER_RANK:
        raise TierConfigError(f"Unknown tier '{tier}'. Valid: {TIERS}")
    return _TIER_RANK[t]


def validate_tier_config(capital_tier: str, active_mode: str) -> None:
    """
    Raise TierConfigError if active_mode > capital_tier.
    """
    ct = capital_tier.upper().strip()
    am = active_mode.upper().strip()
    if ct not in _TIER_RANK:
        raise TierConfigError(f"Unknown capital_tier '{capital_tier}'. Valid: {TIERS}")
    if am not in _TIER_RANK:
        raise TierConfigError(f"Unknown active_mode '{active_mode}'. Valid: {TIERS}")
    if _TIER_RANK[am] > _TIER_RANK[ct]:
        raise TierConfigError(
            f"active_mode '{am}' exceeds capital_tier '{ct}'. "
            f"Operator can only select a mode <= capital_tier."
        )


def load_tier_config(config: dict[str, Any]) -> tuple[str, str]:
    """
    Extract and validate (capital_tier, active_mode) from a parsed toml config dict.
    Returns the validated (capital_tier, active_mode) as uppercase strings.
    Defaults to ("MICRO", "MICRO") if [tier] section is absent.
    """
    tier_section = config.get("tier", {})
    capital_tier = str(tier_section.get("capital_tier", "MICRO")).upper().strip()
    active_mode = str(tier_section.get("active_mode", "MICRO")).upper().strip()
    validate_tier_config(capital_tier, active_mode)
    return capital_tier, active_mode
