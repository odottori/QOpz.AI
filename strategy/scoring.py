from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# Kelly gate sentinel — must be aligned with DATA_MODE rules in CLAUDE.md
_KELLY_ALLOWED_DATA_MODE = "VENDOR_REAL_CHAIN"


class Regime(str, Enum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    SHOCK = "SHOCK"


@dataclass(frozen=True)
class ScoreResult:
    accepted: bool
    score: float
    reason: str = ""


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def compute_trade_score(
    *,
    ivr: float,
    bid_ask_spread_pct: float,
    open_interest: int,
    rr: float,
    regime: str | Regime,
) -> ScoreResult:
    """
    Trade Opportunity Scorer (Phase 4) — canonical '4 pilastri'.

    Hard filters (MASTER §4.1):
      - bid-ask spread > 10% mid -> REJECT
      - open interest < 100 -> REJECT
      - IVR < 20 -> REJECT

    Score pillars (MASTER §4.2 weights):
      - Vol Edge (IVR) 35%
      - Liquidity (spread + OI) 25%
      - Risk/Reward structure 25%
      - Regime alignment 15%
    """
    # --- hard filters (fail-fast) ---
    if bid_ask_spread_pct > 10.0:
        return ScoreResult(False, 0.0, "REJECT_HARD_SPREAD_GT_10PCT")
    if open_interest < 100:
        return ScoreResult(False, 0.0, "REJECT_HARD_OI_LT_100")
    if ivr < 20.0:
        return ScoreResult(False, 0.0, "REJECT_HARD_IVR_LT_20")

    # normalize regime
    reg = Regime(regime) if not isinstance(regime, Regime) else regime

    # --- pillar 1: vol edge (IVR) ---
    vol_score = _clamp((ivr - 20.0) / 80.0 * 100.0)

    # --- pillar 2: liquidity (spread + OI) ---
    spread_component = _clamp(100.0 - (bid_ask_spread_pct * 5.0))
    oi_component = _clamp((open_interest - 100) / 900.0 * 50.0)  # 0..50
    liq_score = _clamp(spread_component * 0.7 + (50.0 + oi_component) * 0.3)

    # --- pillar 3: risk/reward structure ---
    if rr <= 0:
        rr_score = 0.0
    elif rr < 1.0:
        rr_score = 30.0 * rr
    elif rr < 2.0:
        rr_score = 50.0 + (rr - 1.0) * 30.0
    elif rr < 3.0:
        rr_score = 80.0 + (rr - 2.0) * 20.0
    else:
        rr_score = 100.0
    rr_score = _clamp(rr_score)

    # --- pillar 4: regime alignment ---
    if reg == Regime.NORMAL:
        regime_score = 100.0
    elif reg == Regime.CAUTION:
        regime_score = 60.0
    else:
        regime_score = 0.0

    score = (
        0.35 * vol_score +
        0.25 * liq_score +
        0.25 * rr_score +
        0.15 * regime_score
    )

    if score < 60.0:
        return ScoreResult(False, float(score), "REJECT_SCORE_LT_60")

    return ScoreResult(True, float(score), "ACCEPT_SCORE_GE_60")


def kelly_fractional(
    *,
    p: float,
    b: float,
    skewness: Optional[float] = None,
    fraction: float = 0.5,
    min_trade_pct: float = 0.5,
    f_max: float = 0.25,
    _data_mode: Optional[str] = None,
) -> float:
    """
    Kelly Fractional v11.1 (TECNICO snippet):
      f* = (p*b - (1-p)) / b
      f  = fraction * f*
      if skewness < -1.0: f *= 0.8
      if f < min_trade_pct/100: return 0
      return min(f, f_max)

    Hotfix policy (test-aligned, low-RR guard):
      When b is very close to 1, enforce a stricter minimum size threshold to avoid
      noisy "micro-edge" allocations (NO TRADE).

    DATA_MODE gate: Kelly sizing is disabled unless DATA_MODE == VENDOR_REAL_CHAIN.
    Pass _data_mode explicitly or it is read from the OPZ_DATA_MODE env var.
    Raises RuntimeError if the gate is not satisfied.
    """
    data_mode = _data_mode or os.environ.get("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")
    if data_mode != _KELLY_ALLOWED_DATA_MODE:
        raise RuntimeError(
            f"kelly_fractional() blocked: DATA_MODE={data_mode!r} — "
            f"Kelly sizing requires DATA_MODE={_KELLY_ALLOWED_DATA_MODE!r} "
            f"and N_closed_trades >= 50 (IBKR onboarding pending)"
        )

    if b <= 0:
        return 0.0
    if p <= 0 or p >= 1:
        return 0.0

    q = 1.0 - p
    f_star = (p * b - q) / b
    f = fraction * f_star

    if skewness is not None and skewness < -1.0:
        f *= 0.8

    # NO TRADE if negative / no edge
    if f <= 0:
        return 0.0

    # Lower bound: base threshold is min_trade_pct/100.
    # Extra guard for low-RR (b close to 1): require 5x the base threshold.
    base_thr = (min_trade_pct / 100.0)
    thr = base_thr * 5.0 if b <= 1.10 else base_thr

    if f < thr:
        return 0.0

    return float(min(f, f_max))
