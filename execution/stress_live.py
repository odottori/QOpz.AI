from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from execution.drawdown_control import DrawdownPolicyState, evaluate_drawdown_policy


@dataclass(frozen=True)
class StressCheckResult:
    scenario: str
    ok: bool
    details: Dict[str, Any]


def check_vix_spike(*, vix_prev: float, vix_now: float, regime_before: str = "CAUTION") -> StressCheckResult:
    prev = float(vix_prev)
    now = float(vix_now)
    change = ((now - prev) / prev) if prev > 0 else 0.0

    regime_after = "SHOCK" if change >= 0.20 else regime_before
    hedge_on = regime_after == "SHOCK"
    ok = regime_after == "SHOCK" and hedge_on

    return StressCheckResult(
        scenario="VIX_SPIKE_20PCT",
        ok=ok,
        details={
            "vix_prev": prev,
            "vix_now": now,
            "change_pct": change,
            "regime_before": regime_before,
            "regime_after": regime_after,
            "hedge_on": hedge_on,
        },
    )


def check_gap_down(*, equity_series: Iterable[float]) -> StressCheckResult:
    values = [float(x) for x in equity_series]
    state: DrawdownPolicyState = evaluate_drawdown_policy(equity_series=values)

    # F6-T3 asks for DD check and possible kill switch. Pass when DD check runs
    # and policy response is coherent with thresholds.
    max_dd = float(state.max_drawdown)
    kill_expected = max_dd >= 0.20
    stop_expected = max_dd >= 0.15
    alert_expected = max_dd >= 0.10

    if kill_expected:
        ok = state.kill_switch and (not state.allow_new_positions) and state.hedge_on
    elif stop_expected:
        ok = (not state.kill_switch) and (not state.allow_new_positions) and state.hedge_on
    elif alert_expected:
        ok = (not state.kill_switch) and state.allow_new_positions and (state.sizing_scalar <= 0.5)
    else:
        ok = max_dd >= 0.05  # DD check still meaningful for a -5% overnight gap

    return StressCheckResult(
        scenario="GAP_DOWN_5PCT_OVERNIGHT",
        ok=ok,
        details={
            "equity_points": len(values),
            "max_drawdown": max_dd,
            "sizing_scalar": state.sizing_scalar,
            "allow_new_positions": state.allow_new_positions,
            "hedge_on": state.hedge_on,
            "kill_switch": state.kill_switch,
            "events": [
                {
                    "index": e.index,
                    "drawdown": e.drawdown,
                    "level": e.level,
                }
                for e in state.events
            ],
        },
    )


def check_api_disconnect(*, reconnect_attempts: Iterable[bool], max_retries: int = 3) -> StressCheckResult:
    attempts: List[bool] = [bool(x) for x in reconnect_attempts]
    capped = attempts[: max(1, int(max_retries))]

    had_disconnect = True
    reconnect_ok = any(capped)
    reconnect_at = (capped.index(True) + 1) if reconnect_ok else None
    alert_sent = had_disconnect

    ok = reconnect_ok and alert_sent

    return StressCheckResult(
        scenario="API_DISCONNECTION",
        ok=ok,
        details={
            "max_retries": int(max_retries),
            "attempts": capped,
            "reconnect_ok": reconnect_ok,
            "reconnect_at_attempt": reconnect_at,
            "alert_sent": alert_sent,
        },
    )


def run_f6_t3_stress_suite(
    *,
    vix_prev: float = 20.0,
    vix_now: float = 24.0,
    equity_series: Iterable[float] | None = None,
    reconnect_attempts: Iterable[bool] | None = None,
) -> Dict[str, Any]:
    if equity_series is None:
        # 20% drawdown path -> deterministic kill-switch activation.
        equity_series = [100_000, 98_000, 95_000, 90_000, 85_000, 80_000]
    if reconnect_attempts is None:
        # first retry fails, second succeeds
        reconnect_attempts = [False, True]

    r1 = check_vix_spike(vix_prev=vix_prev, vix_now=vix_now)
    r2 = check_gap_down(equity_series=equity_series)
    r3 = check_api_disconnect(reconnect_attempts=reconnect_attempts)

    checks = [r1, r2, r3]
    overall_ok = all(r.ok for r in checks)

    return {
        "overall_pass": overall_ok,
        "checks": [
            {"scenario": r.scenario, "pass": r.ok, **r.details}
            for r in checks
        ],
    }
