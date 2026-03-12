"""QuantOptionAI — Domain 2 (D2.1)
Minimal PowerShell-friendly CLI to submit an order via the D2 execution boundary.

- Works even when invoked from a different working directory (sys.path fix).
- Adds explicit dependency preflight for core runtime deps (duckdb).
- Uses dedicated execution DB (db/execution.duckdb) via execution.idempotency.
- Gate0: paper/live broker adapter may be unavailable => controlled reject (exit 10).
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import tomllib  # Py 3.11+
except Exception:  # pragma: no cover
    tomllib = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dataset_mode_fallback(raw: str) -> dict:
    """Very small TOML fallback used on Python 3.10 when tomllib is unavailable."""
    dataset_mode = None
    in_dataset = False
    for ln in raw.splitlines():
        line = ln.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_dataset = line.strip("[]").strip().lower() == "dataset"
            continue
        if in_dataset and line.lower().startswith("mode") and "=" in line:
            _, rhs = line.split("=", 1)
            dataset_mode = rhs.strip().strip('"').strip("'")
            break
    if dataset_mode is None:
        return {}
    return {"dataset": {"mode": dataset_mode}, "_warning": "parsed via fallback (tomllib unavailable)"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="submit_order", add_help=True)
    p.add_argument("--profile", required=True, choices=["dev", "paper", "live"])
    p.add_argument("--config", required=False, default=None, help="Path to config TOML (optional for D2.1)")

    p.add_argument("--symbol", required=True)
    p.add_argument("--side", required=True, choices=["BUY", "SELL"])
    p.add_argument("--qty", required=True, type=int)

    p.add_argument("--run-id", default=None, help="Override run id (otherwise auto)")
    p.add_argument("--client-order-id", default=None, help="Override client order id (otherwise auto)")

    p.add_argument("--out", default=None, help="Optional path to write a one-line JSON result")
    return p.parse_args(argv)


def safe_load_config(path: str | None) -> dict:
    if not path:
        return {}
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except Exception as e:
        return {"_error": f"Failed to read config: {e!r}", "_path": path}

    if tomllib is None:
        return _parse_dataset_mode_fallback(raw)

    try:
        return tomllib.loads(raw)
    except Exception as e:
        return {"_error": f"Failed to load config: {e!r}", "_path": path}


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def preflight_core_deps() -> tuple[bool, str | None]:
    try:
        importlib.import_module("duckdb")
        return True, None
    except ModuleNotFoundError:
        return False, "Missing dependency: duckdb. Install: py -m pip install -r requirements-core.txt"


def validate_dataset_mode_for_profile(profile: str, cfg: dict) -> tuple[bool, str | None]:
    """Guard profile/data-mode mismatch when config is provided.

    This is intentionally strict only for paper/live to avoid accidental synthetic leakage.
    """
    if not isinstance(cfg, dict) or not cfg:
        return True, None

    mode = str(cfg.get("dataset", {}).get("mode", "")).strip().lower()
    if not mode:
        return True, None

    prof = profile.lower()
    if prof in {"paper", "live"}:
        if mode == "synthetic":
            return False, "dataset.mode=synthetic is not allowed for paper/live submits"
        if mode != prof:
            return False, f"dataset.mode={mode} does not match profile={prof}"

    return True, None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    from execution.order_schema import Order
    from execution.client_id import generate_client_order_id

    client_order_id = args.client_order_id or generate_client_order_id(run_id)

    order = Order(symbol=args.symbol, side=args.side, quantity=args.qty)
    try:
        order.validate()
    except Exception as e:
        result = {
            "ts_utc": utc_now_iso(),
            "run_id": run_id,
            "profile": args.profile,
            "status": "REJECTED_SCHEMA",
            "reason": str(e),
            "order": asdict(order),
            "client_order_id": client_order_id,
        }
        if args.out:
            Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        append_jsonl(Path("logs/execution_events.jsonl"), {"event": "ORDER_SCHEMA_REJECTED", **result})
        print(json.dumps(result, ensure_ascii=False))
        return 10 if args.profile in ("paper", "live") else 2

    # Keep config load for traceability (even if not used by dev dry-run today)
    cfg = safe_load_config(args.config)

    ok_mode, mode_reason = validate_dataset_mode_for_profile(args.profile, cfg)
    if not ok_mode:
        payload = {
            "ts_utc": utc_now_iso(),
            "run_id": run_id,
            "profile": args.profile,
            "status": "REJECTED_DATA_MODE",
            "reason": mode_reason,
            "client_order_id": client_order_id,
            "order": asdict(order),
            "config_meta": {
                "config_path": args.config,
                "config_loaded": isinstance(cfg, dict) and "_error" not in cfg,
            },
        }
        append_jsonl(Path("logs/execution_events.jsonl"), {"event": "DATA_MODE_REJECTED", **payload})
        print(json.dumps(payload, ensure_ascii=False))
        return 10 if args.profile in ("paper", "live") else 2

    # D2 boundary behavior:
    # - dev: use existing dry-run adapter (deterministic, broker-free)
    # - paper/live: broker adapter boundary (Gate0 expected unavailable)
    if args.profile == "dev":
        ok, msg = preflight_core_deps()
        if not ok:
            result = {
                "ts_utc": utc_now_iso(),
                "run_id": run_id,
                "profile": args.profile,
                "status": "REJECTED_ENV",
                "reason": msg,
            }
            append_jsonl(Path("logs/execution_events.jsonl"), {"event": "EXEC_ENV_REJECTED", **result})
            print(json.dumps(result, ensure_ascii=False))
            return 2

        from execution.dry_run_adapter import submit as dry_submit

        try:
            response = dry_submit(order, client_order_id, run_id=run_id, profile="dev")
        except Exception as e:
            result = {
                "ts_utc": utc_now_iso(),
                "run_id": run_id,
                "profile": args.profile,
                "status": "REJECTED_DB",
                "reason": str(e),
                "order": asdict(order),
                "client_order_id": client_order_id,
            }
            append_jsonl(Path("logs/execution_events.jsonl"), {"event": "EXEC_DB_REJECTED", **result})
            print(json.dumps(result, ensure_ascii=False))
            return 2

        result = {
            "ts_utc": utc_now_iso(),
            "run_id": run_id,
            "profile": args.profile,
            "status": response.get("status"),
            "client_order_id": response.get("client_order_id"),
            "order": asdict(order),
            "config_meta": {
                "config_path": args.config,
                "config_loaded": isinstance(cfg, dict) and "_error" not in cfg,
            },
            "storage": {"db": "db/execution.duckdb (or db/execution_recovered_<ts>.duckdb on recovery)"},
        }
        append_jsonl(Path("logs/execution_events.jsonl"), {"event": "ORDER_SUBMIT", **result})

        if args.out:
            Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        print(json.dumps(result, ensure_ascii=False))
        return 0

    # paper/live
    from execution.boundary_adapter import make_adapter, BrokerUnavailableError

    try:
        adapter = make_adapter(args.profile)

        # Gate0: no market pricing in CLI; broker adapters will override.
        adapter.submit_limit(
            symbol=order.symbol,
            side=order.side,
            qty=order.quantity,
            limit_price=0.0,
            run_id=run_id,
            client_order_id=client_order_id,
        )

        payload = {
            "ts_utc": utc_now_iso(),
            "run_id": run_id,
            "profile": args.profile,
            "status": "ACCEPTED_BOUNDARY",
            "client_order_id": client_order_id,
            "order": asdict(order),
        }
        append_jsonl(Path("logs/execution_events.jsonl"), {"event": "ORDER_SUBMIT_BOUNDARY", **payload})
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    except BrokerUnavailableError as e:
        payload = {
            "ts_utc": utc_now_iso(),
            "run_id": run_id,
            "profile": args.profile,
            "status": "REJECTED_BROKER_UNAVAILABLE",
            "reason": str(e),
            "client_order_id": client_order_id,
            "order": asdict(order),
        }
        append_jsonl(Path("logs/execution_events.jsonl"), {"event": "BROKER_UNAVAILABLE", **payload})
        print(json.dumps(payload, ensure_ascii=False))
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
