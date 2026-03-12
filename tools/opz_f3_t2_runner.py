from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class BrokerCfg:
    host: str
    port: int
    client_id: int


class IbkrConnectivityError(RuntimeError):
    pass


class IbkrContractError(RuntimeError):
    pass


class IbkrOrderError(RuntimeError):
    pass


def _tcp_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _require_ib_insync() -> None:
    try:
        import ib_insync  # noqa: F401
    except Exception as e:
        raise IbkrConnectivityError("ib_insync not installed. Run: py -m pip install -r requirements-broker-ib.txt") from e


def _load_broker_cfg(profile: str) -> BrokerCfg:
    try:
        from execution.config_loader import load_profile_config  # type: ignore
        cfg: Dict[str, Any] = load_profile_config(profile)
        b = cfg.get("broker", {}) or {}
        host = str(b.get("host", "127.0.0.1"))
        port = int(b.get("port", 7497))
        client_id = int(b.get("client_id", b.get("clientId", 7)))
        return BrokerCfg(host=host, port=port, client_id=client_id)
    except Exception as e:
        raise RuntimeError(f"cannot load config for profile={profile}: {e}") from e


def _connect_ib(cfg: BrokerCfg, timeout_sec: int):
    from ib_insync import IB
    ib = IB()
    ib.RequestTimeout = float(timeout_sec)
    ok = ib.connect(cfg.host, cfg.port, clientId=cfg.client_id, timeout=timeout_sec)
    if not ok:
        raise IbkrConnectivityError("connect returned False")
    return ib


def _pick_expirations(exps: Sequence[str], max_n: int = 12) -> List[str]:
    # Keep YYYYMMDD only, sorted.
    out: List[str] = []
    for e in exps:
        if isinstance(e, str) and len(e) == 8 and e.isdigit():
            out.append(e)
    out = sorted(set(out))
    # Prefer expirations in the near future (>=1 day)
    today = datetime.now(timezone.utc).date()
    scored: List[Tuple[int, str]] = []
    for e in out:
        try:
            d = datetime.strptime(e, "%Y%m%d").date()
        except Exception:
            continue
        dte = (d - today).days
        if dte >= 1:
            scored.append((dte, e))
    scored.sort()
    return [e for _, e in scored[:max_n]]


def _candidate_pairs(strikes: Sequence[float], max_pairs: int = 80) -> List[Tuple[float, float]]:
    s = sorted(set(float(x) for x in strikes))
    if len(s) < 4:
        return []
    # Use central strikes to reduce nonsense far OTM picks.
    lo = int(len(s) * 0.25)
    hi = int(len(s) * 0.75)
    core = s[lo:hi] if hi > lo else s
    if len(core) < 4:
        core = s
    pairs: List[Tuple[float, float]] = []
    # adjacent pairs create tight spreads
    for i in range(1, len(core)):
        long_k = core[i - 1]
        short_k = core[i]
        if long_k < short_k:
            pairs.append((long_k, short_k))
            if len(pairs) >= max_pairs:
                break
    return pairs


def _build_bull_put_bag(ib, symbol: str, currency: str, qualify_timeout: int, max_attempts: int):
    from ib_insync import ComboLeg, Contract, Stock, Option

    stk = Stock(symbol, "SMART", currency)
    ib.qualifyContracts(stk)
    if not getattr(stk, "conId", 0):
        raise IbkrContractError(f"cannot qualify underlying {symbol}")

    params = ib.reqSecDefOptParams(stk.symbol, "", stk.secType, stk.conId)
    if not params:
        raise IbkrContractError(f"No option chain params for {symbol} (DEMO/permissions?)")

    attempt = 0
    last_err: Optional[str] = None

    # Iterate each chain separately to avoid mixing incompatible strike/expiry sets.
    for p in params:
        chain_ex = getattr(p, "exchange", "SMART") or "SMART"
        trading_class = getattr(p, "tradingClass", None)
        expirations = _pick_expirations(list(getattr(p, "expirations", []) or []), max_n=12)
        strikes_raw = [float(x) for x in (getattr(p, "strikes", []) or [])]
        # Broad sanity range; don't over-filter.
        strikes = [s for s in strikes_raw if 1.0 <= s <= 5000.0]
        pairs = _candidate_pairs(strikes, max_pairs=80)
        if not expirations or not pairs:
            continue

        for exp in expirations:
            for (long_k, short_k) in pairs:
                attempt += 1
                if attempt > max_attempts:
                    raise IbkrContractError(f"unable to qualify any put pair for {symbol}; last_err={last_err}")
                short_put = Option(symbol, exp, short_k, "P", chain_ex, currency=currency, multiplier="100")
                long_put = Option(symbol, exp, long_k, "P", chain_ex, currency=currency, multiplier="100")
                if trading_class:
                    # Some contracts need tradingClass to qualify correctly
                    setattr(short_put, "tradingClass", trading_class)
                    setattr(long_put, "tradingClass", trading_class)
                try:
                    ib.qualifyContracts(short_put, long_put)
                    if getattr(short_put, "conId", 0) and getattr(long_put, "conId", 0):
                        bag = Contract(secType="BAG", symbol=symbol, exchange="SMART", currency=currency)
                        bag.comboLegs = [
                            ComboLeg(conId=short_put.conId, ratio=1, action="SELL", exchange="SMART"),
                            ComboLeg(conId=long_put.conId, ratio=1, action="BUY", exchange="SMART"),
                        ]
                        return bag, short_put, long_put
                except Exception as e:
                    last_err = str(e)
                if attempt % 5 == 0:
                    print(f"[{_now()}] qualify attempt={attempt}/{max_attempts} ex={chain_ex} exp={exp} pair=({long_k},{short_k}) last_err={last_err}")

    raise IbkrContractError(f"unable to qualify any put pair for {symbol}; last_err={last_err}")


def _place_modify_cancel(ib, bag, timeout_sec: int) -> Dict[str, Any]:
    from ib_insync import LimitOrder

    order = LimitOrder("SELL", 1, 0.10)  # credit
    trade = ib.placeOrder(bag, order)

    # wait for acknowledgement (strict)
    t0 = time.time()
    last_status = ""
    while time.time() - t0 < timeout_sec:
        ib.sleep(0.2)
        last_status = getattr(trade.orderStatus, "status", "") or ""
        if last_status in ("Submitted", "PreSubmitted", "Filled"):
            break
        if last_status in ("Cancelled", "Inactive"):
            raise IbkrOrderError(f"order rejected/inactive status={last_status}")
    if last_status not in ("Submitted", "PreSubmitted", "Filled"):
        raise IbkrOrderError(f"order not acknowledged status={last_status}")

    # Modify price slightly
    order.lmtPrice = float(order.lmtPrice) + 0.01
    trade2 = ib.placeOrder(bag, order)
    ib.sleep(0.5)

    # Cancel and confirm
    ib.cancelOrder(order)
    t1 = time.time()
    last2 = ""
    while time.time() - t1 < timeout_sec:
        ib.sleep(0.2)
        last2 = getattr(trade2.orderStatus, "status", "") or ""
        if last2 in ("Cancelled", "Filled"):
            break
    if last2 not in ("Cancelled", "Filled"):
        raise IbkrOrderError(f"cancel not confirmed status={last2}")

    return {"order_id": getattr(order, "orderId", None), "status": last2}


def _advance_state_on_pass(next_step: str) -> None:
    from tools.opz_step_ctl import main as step_ctl_main  # type: ignore
    step_ctl_main(["--unfreeze", "F3-T2"])
    step_ctl_main(["--complete", "F3-T2", "--advance-to", next_step])
    step_ctl_main(["--set-next", next_step])


def _block_state(reason: str, advance_to: str) -> None:
    from tools.opz_step_ctl import main as step_ctl_main  # type: ignore
    # Ensure not counted as completed.
    step_ctl_main(["--uncomplete", "F3-T2"])
    step_ctl_main(["--freeze", "F3-T2", "--reason", reason, "--advance-to", advance_to])
    step_ctl_main(["--set-next", advance_to])


def run(profile: str, qualify_timeout: int, qualify_max_attempts: int, advance_state: bool, block_on_fail: bool) -> int:
    _require_ib_insync()
    cfg = _load_broker_cfg(profile)
    if not _tcp_open(cfg.host, cfg.port):
        print("F3-T2 IBKR COMBO: CRITICAL_FAIL (exit=11)")
        print(f"- CONNECTIVITY_FAIL no TCP listener host={cfg.host} port={cfg.port}")
        return 11

    ib = None
    try:
        ib = _connect_ib(cfg, timeout_sec=qualify_timeout)
        # Make qualification bounded
        ib.RequestTimeout = float(qualify_timeout)

        # Run for required symbols (SPY, IWM)
        results: List[Dict[str, Any]] = []
        for sym in ("SPY", "IWM"):
            bag, short_put, long_put = _build_bull_put_bag(
                ib, symbol=sym, currency="USD", qualify_timeout=qualify_timeout, max_attempts=qualify_max_attempts
            )
            summary = _place_modify_cancel(ib, bag, timeout_sec=10)
            results.append({
                "symbol": sym,
                "short": short_put,
                "long": long_put,
                "summary": summary,
            })

        print("F3-T2 IBKR COMBO: PASS (exit=0)")
        print(f"- CONNECTED host={cfg.host} port={cfg.port} clientId={cfg.client_id}")
        for r in results:
            sp = r["short"]; lp = r["long"]; sm = r["summary"]
            print(f"- {r['symbol']} LEGS short_put_strike={sp.strike} long_put_strike={lp.strike} expiry={sp.lastTradeDateOrContractMonth}")
            print(f"- {r['symbol']} ORDER orderId={sm.get('order_id')} status={sm.get('status')}")
        if advance_state:
            _advance_state_on_pass("F6-T1")
            print("- STATE advanced next_step=F6-T1 (F3-T2 completed)")
        return 0

    except (IbkrContractError, IbkrOrderError, IbkrConnectivityError) as e:
        print("F3-T2 IBKR COMBO: CRITICAL_FAIL (exit=11)")
        print(f"- {type(e).__name__}: {e}")
        if block_on_fail and advance_state:
            _block_state(reason=str(e), advance_to="F6-T1")
            print("- STATE blocked F3-T2 and advanced next_step=F6-T1 (continue roadmap while blocked)")
        return 11
    except Exception as e:
        print("F3-T2 IBKR COMBO: CRITICAL_FAIL (exit=11)")
        print(f"- UNEXPECTED {type(e).__name__}: {e}")
        return 11
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="paper")
    ap.add_argument("--qualify-timeout", type=int, default=3)
    ap.add_argument("--qualify-max-attempts", type=int, default=60)
    ap.add_argument("--advance-state", action="store_true")
    ap.add_argument("--block-on-fail", action="store_true")
    args = ap.parse_args(argv)
    return run(
        profile=args.profile,
        qualify_timeout=args.qualify_timeout,
        qualify_max_attempts=args.qualify_max_attempts,
        advance_state=args.advance_state,
        block_on_fail=args.block_on_fail,
    )


if __name__ == "__main__":
    raise SystemExit(main())
