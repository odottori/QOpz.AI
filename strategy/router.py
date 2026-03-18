"""
Strategy router — maps (capital_tier, active_mode, regime) to eligible strategies.

Rules:
- active_mode determines which strategies are available (not capital_tier).
- capital_tier is the ceiling; active_mode must be <= capital_tier (enforced by tier_config).
- Regime SHOCK → no new trades regardless of tier.
- Regime CAUTION → only directional spreads (bull_put); IC and Wheel suspended.
"""
from __future__ import annotations

from strategy.scoring import Regime
from strategy.tier_config import TIERS, tier_rank, validate_tier_config

# Strategies available per tier (cumulative: each tier adds to previous)
_TIER_STRATEGIES: dict[str, list[str]] = {
    "MICRO":    ["bull_put"],
    "SMALL":    ["bull_put", "iron_condor", "wheel"],
    "MEDIUM":   ["bull_put", "iron_condor", "wheel", "pmcc", "calendar"],
    "ADVANCED": ["bull_put", "iron_condor", "wheel", "pmcc", "calendar", "ratio_spread"],
}

# Strategies suspended in CAUTION regime (too wide / directional only)
_CAUTION_SUSPENDED: frozenset[str] = frozenset(["iron_condor", "wheel", "pmcc", "calendar", "ratio_spread"])


def select_strategies(
    capital_tier: str,
    active_mode: str,
    regime: str | Regime,
) -> list[str]:
    """
    Return list of eligible strategy names for the given tier/mode/regime.

    Args:
        capital_tier: ceiling tier from config (e.g. "SMALL")
        active_mode:  operator-selected mode — must be <= capital_tier
        regime:       current market regime (NORMAL / CAUTION / SHOCK)

    Returns:
        Sorted list of strategy names (empty if SHOCK or no strategies pass filters).
    """
    validate_tier_config(capital_tier, active_mode)

    reg = Regime(regime) if not isinstance(regime, Regime) else regime
    if reg == Regime.SHOCK:
        return []

    available = list(_TIER_STRATEGIES.get(active_mode.upper(), []))

    if reg == Regime.CAUTION:
        available = [s for s in available if s not in _CAUTION_SUSPENDED]

    return sorted(available)


def strategy_eligible(
    strategy: str,
    capital_tier: str,
    active_mode: str,
    regime: str | Regime,
) -> bool:
    """Return True if a specific strategy is eligible given current tier/mode/regime."""
    return strategy in select_strategies(capital_tier, active_mode, regime)
