from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

SHARES_PER_CONTRACT = 100


@dataclass(frozen=True)
class CapitalFeasibility:
    collateral_required: float
    collateral_pct_of_account: float
    max_loss_pct_of_account: float
    post_fill_concentration_pct: float
    post_assignment_concentration_pct: float
    annualized_return_on_locked_capital: float
    capital_efficiency_score: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _short_put_assignment_notional(strategy: str, underlying_price: float, strikes: list[float]) -> float:
    st = (strategy or '').strip().upper()
    if st == 'WHEEL':
        base = max(strikes) if strikes else underlying_price
        return max(0.0, float(base) * SHARES_PER_CONTRACT)
    if st == 'BULL_PUT':
        base = max(strikes) if strikes else underlying_price
        return max(0.0, float(base) * SHARES_PER_CONTRACT)
    return 0.0


def _collateral_required(strategy: str, max_loss: float, credit_or_debit: float, underlying_price: float, strikes: list[float]) -> float:
    st = (strategy or '').strip().upper()
    if st in {'BULL_PUT', 'IRON_CONDOR'}:
        return max(0.0, float(max_loss))
    if st in {'BULL_CALL', 'STRADDLE'}:
        return max(0.0, abs(float(credit_or_debit))) if credit_or_debit else max(0.0, float(max_loss))
    if st == 'WHEEL':
        base = max(strikes) if strikes else underlying_price
        return max(0.0, float(base) * SHARES_PER_CONTRACT)
    return max(0.0, float(max_loss))


def build_capital_feasibility(*, strategy: str, account_size: float, underlying_price: float, dte: int, strikes: list[float] | None = None, credit_or_debit: float = 0.0, max_loss: float = 0.0) -> CapitalFeasibility:
    if account_size <= 0:
        raise ValueError('account_size must be > 0')

    st = (strategy or '').strip().upper()
    strikes_list = [float(s) for s in (strikes or [])]
    collateral_required = _collateral_required(st, max_loss, credit_or_debit, underlying_price, strikes_list)
    collateral_pct = (collateral_required / account_size) * 100.0 if account_size > 0 else 0.0
    max_loss_pct = (max(0.0, float(max_loss)) / account_size) * 100.0 if account_size > 0 else 0.0
    post_fill = collateral_pct
    assignment_notional = _short_put_assignment_notional(st, underlying_price, strikes_list)
    post_assignment = (assignment_notional / account_size) * 100.0 if account_size > 0 else 0.0

    annualized = 0.0
    if collateral_required > 0 and dte > 0:
        annualized = (float(credit_or_debit) / collateral_required) * (365.0 / float(dte)) * 100.0

    roc_component = _clamp(annualized / 25.0 * 100.0)
    collateral_component = _clamp(100.0 - collateral_pct)
    assignment_component = _clamp(100.0 - min(post_assignment, 100.0))
    max_loss_component = _clamp(100.0 - (max_loss_pct * 4.0))
    capital_efficiency_score = round(
        (0.40 * roc_component) +
        (0.25 * collateral_component) +
        (0.20 * assignment_component) +
        (0.15 * max_loss_component),
        2,
    )

    return CapitalFeasibility(
        collateral_required=round(collateral_required, 2),
        collateral_pct_of_account=round(collateral_pct, 3),
        max_loss_pct_of_account=round(max_loss_pct, 3),
        post_fill_concentration_pct=round(post_fill, 3),
        post_assignment_concentration_pct=round(post_assignment, 3),
        annualized_return_on_locked_capital=round(annualized, 3),
        capital_efficiency_score=capital_efficiency_score,
    )
