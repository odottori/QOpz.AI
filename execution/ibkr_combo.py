from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

try:
    from ib_insync import IB, Stock, Option, Contract, ComboLeg, LimitOrder  # type: ignore
except Exception:  # pragma: no cover
    IB = None  # type: ignore


@dataclass(frozen=True)
class ComboPlan:
    symbol: str
    expiry: str  # YYYYMMDD
    short_strike: float
    long_strike: float
    right: str  # "P"
    width: float
    action: str  # "SELL" for credit spread
    quantity: int


def _utc_today_yyyymmdd() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def build_bull_put_plan(
    *,
    symbol: str,
    expiry: str,
    short_strike: float,
    long_strike: float,
    quantity: int = 1,
) -> ComboPlan:
    if long_strike >= short_strike:
        raise ValueError("long_strike must be < short_strike for bull put spread")
    return ComboPlan(
        symbol=symbol,
        expiry=expiry,
        short_strike=float(short_strike),
        long_strike=float(long_strike),
        right="P",
        width=float(short_strike) - float(long_strike),
        action="SELL",
        quantity=int(quantity),
    )


def auto_pick_bull_put_plan(
    *,
    ib: "IB",
    symbol: str,
    width: float = 5.0,
    min_dte: int = 7,
    max_dte: int = 60,
    quantity: int = 1,
) -> ComboPlan:
    """
    Choose a reasonable near-term bull put spread plan using option chain + underlying price.
    Human-confirmed execution must happen outside this function.
    """
    stock = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(stock)

    params = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
    if not params:
        raise RuntimeError(f"No option params for {symbol}")

    # Pick the most "complete" chain parameters (avoid demo/odd small strike sets).
    best = None
    best_score = -1
    for cand in params:
        strikes_raw = list(getattr(cand, "strikes", []) or [])
        exps_raw = list(getattr(cand, "expirations", []) or [])
        # numeric strikes only
        strikes_num = []
        for s in strikes_raw:
            try:
                strikes_num.append(float(s))
            except Exception:
                continue
        max_strike = max(strikes_num) if strikes_num else 0.0

        # Heuristic: for common ETFs (SPY/IWM/QQQ) prefer chains with realistic strike ranges.
        if symbol.upper() in {"SPY", "IWM", "QQQ"} and max_strike < 50.0:
            continue

        score = (len(strikes_num) * 10) + len(exps_raw)
        if score > best_score:
            best = cand
            best_score = score

    p = best or params[0]

    # Pick expiry within [min_dte, max_dte]
    today = datetime.now(timezone.utc).date()
    expiries = sorted(getattr(p, "expirations", []) or [])
    chosen_exp = None
    for e in expiries:
        try:
            d = datetime.strptime(e, "%Y%m%d").date()
        except Exception:
            continue
        dte = (d - today).days
        if dte < min_dte:
            continue
        if dte > max_dte:
            continue
        chosen_exp = e
        break
    if chosen_exp is None:
        # fallback: first future expiry
        for e in expiries:
            try:
                d = datetime.strptime(e, "%Y%m%d").date()
            except Exception:
                continue
            if (d - today).days >= 1:
                chosen_exp = e
                break
    if chosen_exp is None:
        raise RuntimeError(f"No suitable expiry for {symbol}")

    # Underlying price is intentionally NOT requested (avoids market data subscriptions).
    und_price = None
    strikes = sorted(float(s) for s in (getattr(p, 'strikes', []) or []) if str(s).strip() != '')
    if not strikes:
        raise RuntimeError(f"No strikes for {symbol}")

    if und_price is None:
        # fallback: median strike
        und_price = strikes[len(strikes) // 2]

    # pick short strike: nearest strike below underlying
    below = [s for s in strikes if s < und_price]
    if not below:
        short_strike = strikes[0]
    else:
        short_strike = below[-1]

    target_long = short_strike - float(width)
    long_candidates = [s for s in strikes if s <= target_long]
    if long_candidates:
        long_strike = long_candidates[-1]
    else:
        # fallback: previous strike
        idx = max(0, strikes.index(short_strike) - 1)
        long_strike = strikes[idx]

    if long_strike >= short_strike:
        # force one-step lower
        idx = max(0, strikes.index(short_strike) - 1)
        long_strike = strikes[idx]

    return build_bull_put_plan(symbol=symbol, expiry=chosen_exp, short_strike=short_strike, long_strike=long_strike, quantity=quantity)


def build_combo_contract(ib: "IB", plan: ComboPlan) -> tuple["Contract", "Contract", "Contract"]:
    """
    Returns (combo_contract, short_leg_contract, long_leg_contract).
    """
    # Build legs
    short_put = Option(plan.symbol, plan.expiry, plan.short_strike, plan.right, "SMART", currency="USD")
    long_put = Option(plan.symbol, plan.expiry, plan.long_strike, plan.right, "SMART", currency="USD")
    ib.qualifyContracts(short_put, long_put)

    combo = Contract()
    combo.symbol = plan.symbol
    combo.secType = "BAG"
    combo.currency = "USD"
    combo.exchange = "SMART"
    combo.comboLegs = [
        ComboLeg(conId=short_put.conId, ratio=1, action="SELL", exchange="SMART"),
        ComboLeg(conId=long_put.conId, ratio=1, action="BUY", exchange="SMART"),
    ]
    return combo, short_put, long_put


def default_credit(plan: ComboPlan) -> float:
    # width * 0.20 is a reasonable starting point for a credit spread, cap to [0.1, 2.5]
    c = max(0.10, min(2.50, round(plan.width * 0.20, 2)))
    return float(c)


def place_modify_cancel(
    *,
    ib: "IB",
    plan: ComboPlan,
    limit_credit: float,
    bump: float = 0.05,
    timeout_sec: float = 10.0,
) -> dict[str, Any]:
    """
    Places combo order (SELL credit), modifies limit, cancels. Returns a dict summary.
    """
    combo, short_leg, long_leg = build_combo_contract(ib, plan)

    order = LimitOrder("SELL", plan.quantity, float(limit_credit))
    trade = ib.placeOrder(combo, order)

    # Wait for orderId
    t0 = datetime.now(timezone.utc)
    while trade.orderStatus.orderId is None:
        ib.sleep(0.2)
        if (datetime.now(timezone.utc) - t0).total_seconds() > timeout_sec:
            raise TimeoutError("orderId not assigned in time")

    order_id = int(trade.orderStatus.orderId)

    # Modify price (increase credit a bit => less likely to fill)
    order.lmtPrice = float(round(float(order.lmtPrice) + float(bump), 2))
    trade = ib.placeOrder(combo, order)
    ib.sleep(0.5)

    # Cancel
    ib.cancelOrder(order)
    t1 = datetime.now(timezone.utc)
    while True:
        status = str(trade.orderStatus.status or "")
        if status.lower() in {"cancelled", "canceled"}:
            break
        ib.sleep(0.2)
        if (datetime.now(timezone.utc) - t1).total_seconds() > timeout_sec:
            raise TimeoutError(f"cancel not confirmed (status={status})")

    return {
        "symbol": plan.symbol,
        "expiry": plan.expiry,
        "short_strike": plan.short_strike,
        "long_strike": plan.long_strike,
        "order_id": order_id,
        "final_limit_credit": float(order.lmtPrice),
        "status": str(trade.orderStatus.status),
        "short_conId": short_leg.conId,
        "long_conId": long_leg.conId,
    }
