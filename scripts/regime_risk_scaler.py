from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Dict, Any, Optional


def clamp(x: float, lo: float, hi: float) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


@dataclass(frozen=True)
class RiskScalarConfig:
    # weights for probability of shock
    w_hmm: float = 0.6
    w_clf: float = 0.4

    # mapping regime_score -> risk_scalar
    risk_min: float = 0.25
    risk_max: float = 1.0

    # smoothing / hysteresis
    ema_span: int = 5
    # require shock probability to fall below this to start increasing risk again
    shock_release_threshold: float = 0.40
    # require shock probability to rise above this to start decreasing risk
    shock_enter_threshold: float = 0.70


def combine_shock_probability(p_shock_hmm: float, p_shock_clf: float, cfg: RiskScalarConfig) -> float:
    """Combine two probabilities into a single regime_score in [0,1]."""
    p = cfg.w_hmm * p_shock_hmm + cfg.w_clf * p_shock_clf
    return clamp(p, 0.0, 1.0)


def map_score_to_risk(score: float, cfg: RiskScalarConfig) -> float:
    """Linear mapping: score=0 -> risk_max, score=1 -> risk_min."""
    score = clamp(score, 0.0, 1.0)
    risk = cfg.risk_max - (cfg.risk_max - cfg.risk_min) * score
    return clamp(risk, cfg.risk_min, cfg.risk_max)


def _ema(alpha: float, prev: float, x: float) -> float:
    return prev + alpha * (x - prev)


def compute_risk_scalar_series(
    rows: List[Dict[str, Any]],
    cfg: RiskScalarConfig = RiskScalarConfig(),
) -> List[Dict[str, Any]]:
    """
    Compute regime_score and risk_scalar for a series.

    Required keys per row:
      - p_shock_hmm: float in [0,1]
      - p_shock_clf: float in [0,1]

    Adds:
      - regime_score
      - risk_scalar_raw
      - risk_scalar (smoothed + hysteresis)
    """
    if cfg.ema_span <= 1:
        alpha = 1.0
    else:
        alpha = 2.0 / (cfg.ema_span + 1.0)

    out: List[Dict[str, Any]] = []
    risk_prev = cfg.risk_max
    in_shock = False

    for r in rows:
        p_hmm = float(r.get("p_shock_hmm", r.get("p_shock", 0.0)))
        p_clf = float(r.get("p_shock_clf", r.get("p_shock_classifier", 0.0)))
        score = combine_shock_probability(p_hmm, p_clf, cfg)
        raw = map_score_to_risk(score, cfg)

        # hysteresis: once in shock, only release after score drops sufficiently
        if in_shock:
            if score < cfg.shock_release_threshold:
                in_shock = False
        else:
            if score > cfg.shock_enter_threshold:
                in_shock = True

        # If in_shock, don't allow risk to rise above raw (only equal or lower)
        # If not in_shock, don't allow risk to drop below raw (only equal or higher)
        if in_shock:
            raw = min(raw, risk_prev)
        else:
            raw = max(raw, risk_prev)

        risk = _ema(alpha, risk_prev, raw)
        risk = clamp(risk, cfg.risk_min, cfg.risk_max)

        rr = dict(r)
        rr["regime_score"] = float(score)
        rr["risk_scalar_raw"] = float(raw)
        rr["risk_scalar"] = float(risk)
        rr["in_shock"] = bool(in_shock)
        out.append(rr)
        risk_prev = risk

    return out
