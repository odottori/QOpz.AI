"""F3-T2 — Bull Put 2 legs, send paper order, modify limit, cancel, simulated fill + P&L.

This tool is HUMAN-CONFIRMED. It will not place/cancel orders unless you confirm.

PowerShell examples:
  py tools\f3_t2_ibkr_combo_smoke.py --profile paper --symbols SPY,IWM
  py tools\f3_t2_ibkr_combo_smoke.py --profile paper --symbols SPY,IWM --execute

Exit codes:
  0  PASS
  10 CONNECTIVITY_FAIL
  11 ORDER_FAIL
  20 DEPENDENCY_FAIL
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import tomllib  # py3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore

try:
    from ib_insync import IB  # type: ignore
except Exception:  # pragma: no cover
    IB = None  # type: ignore

from execution.ibkr_combo import auto_pick_bull_put_plan, default_credit, place_modify_cancel
from execution.storage import init_execution_schema, record_event, upsert_order


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json_crlf(path: Path, obj: Any) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    text = text.replace("\r\n", "\n").replace("\n", "\r\n") + "\r\n"
    path.write_text(text, encoding="utf-8", newline="")

def _advance_state_f3_t2(next_step_after: str = "F6-T1") -> None:
    """Mark F3-T2 completed in .qoaistate.json(progress) and .step_index.json."""
    # step index
    si_path = _repo_root() / ".step_index.json"
    if si_path.exists():
        try:
            si = json.loads(si_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            si = {}
        sc = si.get("steps_completed")
        if not isinstance(sc, list):
            sc = []
        if "F3-T2" not in sc:
            sc.append("F3-T2")
        si["steps_completed"] = sc
        si["next_step"] = next_step_after
        _write_json_crlf(si_path, si)

    st_path = _repo_root() / ".qoaistate.json"
    if not st_path.exists():
        return
    try:
        st = json.loads(st_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        st = {}
    progress = st.get("progress")
    if not isinstance(progress, dict):
        progress = {}
        st["progress"] = progress
    # completion list
    raw_sc = progress.get("steps_completed", [])
    sc2 = raw_sc if isinstance(raw_sc, list) else []
    already = False
    for it in sc2:
        if it == "F3-T2":
            already = True
            break
        if isinstance(it, dict) and (it.get("id") == "F3-T2" or it.get("step") == "F3-T2"):
            already = True
            break
    if not already:
        if sc2 and all(isinstance(it, str) for it in sc2):
            sc2.append("F3-T2")
        else:
            sc2.append({"id": "F3-T2", "ts_utc": _utc_now()})
    progress["steps_completed"] = sc2

    progress["next_step"] = next_step_after
    st["next_step"] = next_step_after
    _write_json_crlf(st_path, st)

def _repo_root() -> Path:
    return ROOT


def _load_profile(profile: str) -> dict[str, Any]:
    cfg_path = _repo_root() / "config" / f"{profile}.toml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Missing profile config: {cfg_path}")
    if tomllib is None:
        raise RuntimeError("tomllib not available (unexpected on py>=3.11)")
    data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    return data


def _tcp_open(host: str, port: int) -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def _confirm_or_abort(execute: bool) -> None:
    if not execute:
        return
    # Allow the calling .bat to pass confirmation (avoid double prompt).
    if os.environ.get("OPZ_CONFIRM") == "YES":
        return
    print("CONFIRM REQUIRED: this will PLACE/MODIFY/CANCEL PAPER orders via TWS/IB Gateway.")
    s = input('Type EXACTLY "YES" to continue: ').strip()
    if s != "YES":
        raise SystemExit(11)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="f3_t2_ibkr_combo_smoke")
    ap.add_argument("--profile", default="paper")
    ap.add_argument("--symbols", default="SPY,IWM", help="Comma-separated underlyings (default: SPY,IWM).")
    ap.add_argument("--width", type=float, default=5.0)
    ap.add_argument("--min-dte", type=int, default=7)
    ap.add_argument("--max-dte", type=int, default=60)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--execute", action="store_true", help="If set, will place/modify/cancel orders AFTER confirmation.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--advance-state", action="store_true", help="If set and PASS, mark F3-T2 completed and set next_step=F6-T1 (tool-based).")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if IB is None:
        print("F3-T2 IBKR COMBO: CRITICAL_FAIL (exit=20)")
        print("- DEPENDENCY_FAIL missing ib_insync")
        print("- HINT: py -m pip install -r requirements-broker-ib.txt")
        return 20

    try:
        cfg = _load_profile(args.profile)
        broker = cfg.get("broker", {}) if isinstance(cfg, dict) else {}
        host = str(broker.get("host", "127.0.0.1"))
        port = int(broker.get("port", 7497))
        client_id = int(broker.get("clientId", 7))
    except Exception as e:
        print("F3-T2 IBKR COMBO: CRITICAL_FAIL (exit=10)")
        print(f"- CONFIG_FAIL err={e}")
        return 10

    # Fast precheck: port must be open.
    if not _tcp_open(host, port):
        print("F3-T2 IBKR COMBO: CRITICAL_FAIL (exit=10)")
        print(f"- CONNECTIVITY_FAIL no listener host={host} port={port}")
        print("- HINT: avvia TWS/IB Gateway e abilita API socket; verifica config/paper.toml [broker].port")
        return 10

    syms = [s.strip().upper() for s in str(args.symbols).split(",") if s.strip()]
    if not syms:
        print("F3-T2 IBKR COMBO: CRITICAL_FAIL (exit=10)")
        print("- CONFIG_FAIL empty symbols")
        return 10

    _confirm_or_abort(args.execute)

    ib = IB()
    try:
        ok = ib.connect(host, port, clientId=client_id, timeout=float(args.timeout))
        if not ok:
            raise TimeoutError("connect returned False")
    except Exception as e:
        print("F3-T2 IBKR COMBO: CRITICAL_FAIL (exit=10)")
        print(f"- CONNECTIVITY_FAIL host={host} port={port} err={e}")
        return 10

    init_execution_schema()
    run_id = f"F3-T2-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    results: list[dict[str, Any]] = []
    try:
        for sym in syms:
            plan = auto_pick_bull_put_plan(
                ib=ib,
                symbol=sym,
                width=float(args.width),
                min_dte=int(args.min_dte),
                max_dte=int(args.max_dte),
                quantity=1,
            )
            credit = default_credit(plan)

            if not args.execute:
                results.append(
                    {
                        "symbol": sym,
                        "plan": plan.__dict__,
                        "limit_credit_default": credit,
                        "mode": "DRY_RUN",
                    }
                )
                continue

            # 1) Create + 2) Send paper order + 3) Modify + 4) Cancel
            client_order_id = f"OPZ-F3T2-{uuid.uuid4()}"
            upsert_order(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=args.profile,
                symbol=sym,
                side="SELL",
                quantity=1,
                state="SUBMITTED",
                limit_price=float(credit),
            )
            record_event(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=args.profile,
                event_type="SUBMIT",
                prev_state="NEW",
                new_state="SUBMITTED",
                details={"plan": plan.__dict__, "limit_credit": credit},
            )

            summary = place_modify_cancel(
                ib=ib,
                plan=plan,
                limit_credit=float(credit),
                bump=0.05,
                timeout_sec=float(args.timeout),
            )

            # Log modify/cancel
            record_event(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=args.profile,
                event_type="MODIFY",
                prev_state="SUBMITTED",
                new_state="ACKED",
                details={"new_limit_credit": summary.get("final_limit_credit")},
            )
            upsert_order(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=args.profile,
                symbol=sym,
                side="SELL",
                quantity=1,
                state="CANCELLED",
                limit_price=float(summary.get("final_limit_credit") or credit),
            )
            record_event(
                client_order_id=client_order_id,
                run_id=run_id,
                profile=args.profile,
                event_type="CANCEL",
                prev_state="ACKED",
                new_state="CANCELLED",
                details={"order_id": summary.get("order_id"), "status": summary.get("status")},
            )

            # 5) Simulated fill + P&L
            sim_id = f"OPZ-F3T2-SIM-{uuid.uuid4()}"
            fill_price = float(summary.get("final_limit_credit") or credit)
            pnl = round(fill_price * 100.0, 2)  # 1 contract multiplier=100
            upsert_order(
                client_order_id=sim_id,
                run_id=run_id,
                profile=args.profile,
                symbol=sym,
                side="SELL",
                quantity=1,
                state="FILLED",
                limit_price=fill_price,
                fill_price=fill_price,
                slippage=0.0,
                outcome=f"SIM_PNL={pnl}",
            )
            record_event(
                client_order_id=sim_id,
                run_id=run_id,
                profile=args.profile,
                event_type="SIM_FILL",
                prev_state="SUBMITTED",
                new_state="FILLED",
                details={"fill_price": fill_price, "pnl": pnl, "note": "simulated fill per canonici/02_TEST.md F3-T2 step 5"},
            )

            results.append(
                {
                    "symbol": sym,
                    "plan": plan.__dict__,
                    "order_summary": summary,
                    "sim_fill": {"fill_price": fill_price, "pnl": pnl},
                }
            )

        if args.json:
            print(json.dumps({"run_id": run_id, "results": results}, ensure_ascii=False, indent=2))
            if getattr(args, "advance_state", False) and args.execute:
                _advance_state_f3_t2(next_step_after="F6-T1")
                print("- STATE advanced next_step=F6-T1 (F3-T2 completed)")
        else:
            if not args.execute:
                print("F3-T2 IBKR COMBO: DRY_RUN (no orders placed)")
                for r in results:
                    p = r["plan"]
                    print(f"- {r['symbol']} expiry={p['expiry']} short={p['short_strike']} long={p['long_strike']} credit~{r['limit_credit_default']}")
                print('HINT: rerun with --execute and type YES to place/modify/cancel paper orders.')
                return 11
            print("F3-T2 IBKR COMBO: PASS (exit=0)")
            for r in results:
                s = r["order_summary"]
                p = r["plan"]
                print(f"- {r['symbol']} legs_ok short={p['short_strike']} long={p['long_strike']} orderId={s['order_id']} status={s['status']}")
        if getattr(args, 'advance_state', False):
            _advance_state_f3_t2(next_step_after='F6-T1')
            print('- STATE advanced next_step=F6-T1 (F3-T2 completed)')
        return 0

    except SystemExit as e:
        return int(getattr(e, "code", 11) or 11)
    except Exception as e:
        msg = str(e)
        # common IB read-only error surfaced as string
        if "Read-Only" in msg or "read-only" in msg or "Error 321" in msg:
            print("F3-T2 IBKR COMBO: CRITICAL_FAIL (exit=11)")
            print("- ORDER_FAIL API is in Read-Only mode (TWS setting).")
            print("- HINT: in TWS disable Read-Only API, then rerun.")
            return 11
        print("F3-T2 IBKR COMBO: CRITICAL_FAIL (exit=11)")
        print(f"- ORDER_FAIL err={e}")
        return 11
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
