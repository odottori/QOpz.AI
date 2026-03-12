from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Sequence


@dataclass(frozen=True)
class MicrostructureFeatures:
    volume_profile_delta: float
    oi_change_velocity: float
    oi_velocity_spike: bool
    iv_curvature_accel: float


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_volume_profile_delta(*, bid_volume: float, ask_volume: float) -> float:
    """Return signed order-flow delta ratio in [-1, 1]."""
    bid = max(0.0, float(bid_volume))
    ask = max(0.0, float(ask_volume))
    den = bid + ask
    if den <= 0.0:
        return 0.0
    return _clamp((ask - bid) / den, -1.0, 1.0)


def compute_oi_change_velocity(
    *,
    oi_t: float,
    oi_t_minus_n: float,
    periods: int = 3,
    annualization_factor: int = 252,
) -> float:
    """Annualized OI change velocity from t-n to t."""
    cur = float(oi_t)
    prev = float(oi_t_minus_n)
    if periods <= 0:
        raise ValueError("periods must be > 0")
    if prev <= 0.0:
        return 0.0
    pct = (cur / prev) - 1.0
    return pct * (annualization_factor / periods)


def detect_velocity_spike(*, velocity_history: Sequence[float], z_threshold: float = 2.0) -> bool:
    """True when latest velocity is a positive z-score spike over history."""
    if len(velocity_history) < 4:
        return False
    series = [float(x) for x in velocity_history]
    baseline = series[:-1]
    sigma = pstdev(baseline)
    if sigma <= 1e-12:
        return False
    z = (series[-1] - mean(baseline)) / sigma
    return bool(z >= z_threshold)


def compute_iv_curvature_accel(*, skew_5d_series: Sequence[float]) -> float:
    """Second finite difference of skew over last 3 points."""
    if len(skew_5d_series) < 3:
        return 0.0
    x0, x1, x2 = map(float, skew_5d_series[-3:])
    accel = x2 - (2.0 * x1) + x0
    if not math.isfinite(accel):
        return 0.0
    return accel


def compute_microstructure_features(
    *,
    bid_volume: float,
    ask_volume: float,
    oi_t: float,
    oi_t_minus_n: float,
    oi_velocity_history: Sequence[float],
    skew_5d_series: Sequence[float],
) -> MicrostructureFeatures:
    return MicrostructureFeatures(
        volume_profile_delta=compute_volume_profile_delta(bid_volume=bid_volume, ask_volume=ask_volume),
        oi_change_velocity=compute_oi_change_velocity(oi_t=oi_t, oi_t_minus_n=oi_t_minus_n),
        oi_velocity_spike=detect_velocity_spike(velocity_history=oi_velocity_history),
        iv_curvature_accel=compute_iv_curvature_accel(skew_5d_series=skew_5d_series),
    )
