from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))
import json
from datetime import datetime, timezone

from execution.config_loader import load_profile_config
from execution.ibkr_settings_profile import extract_ibkr_universe_context

try:
    from scripts import demo_pipeline_lib as dpl
except ModuleNotFoundError:
    import demo_pipeline_lib as dpl


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _pick_symbols(raw: str | None, settings_path: str | None, limit: int) -> list[str]:
    if raw:
        out = [x.strip().upper() for x in raw.split(",") if x.strip()]
        # dedup preserve order
        seen: set[str] = set()
        uniq: list[str] = []
        for s in out:
            if s in seen:
                continue
            seen.add(s)
            uniq.append(s)
        if limit > 0:
            return uniq[:limit]
        return uniq

    ctx = extract_ibkr_universe_context(settings_path)
    symbols = [str(x).strip().upper() for x in (ctx.get("symbols") or []) if str(x).strip()]
    if not symbols:
        symbols = ["SPY", "QQQ", "IWM"]
    if limit > 0:
        symbols = symbols[:limit]
    return symbols


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except Exception:
        return None


def _safe_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _snapshot_payload(symbol: str, tkr: Any, asof: datetime) -> dict[str, Any]:
    return {
        "source": "ibkr_demo_api",
        "symbol": symbol,
        "page_type": "quote",
        "ts": _iso_utc(asof),
        "bid": _safe_float(getattr(tkr, "bid", None)),
        "ask": _safe_float(getattr(tkr, "ask", None)),
        "last": _safe_float(getattr(tkr, "last", None)),
        "close": _safe_float(getattr(tkr, "close", None)),
        "high": _safe_float(getattr(tkr, "high", None)),
        "low": _safe_float(getattr(tkr, "low", None)),
        "open": _safe_float(getattr(tkr, "open", None)),
        "volume": _safe_int(getattr(tkr, "volume", None)),
        "market_data_type": _safe_int(getattr(tkr, "marketDataType", None)),
    }


def run_fetch(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from ib_insync import IB, Stock
    except Exception as exc:
        raise RuntimeError("ib_insync non installato nel python corrente") from exc

    cfg = load_profile_config(args.profile)
    b = cfg.get("broker") or {}
    host = str(args.host or b.get("host") or "127.0.0.1")
    port = int(args.port if args.port is not None else (b.get("port") or 7497))
    client_id = int(args.client_id if args.client_id is not None else (b.get("client_id") or b.get("clientId") or 7))

    symbols = _pick_symbols(args.symbols, args.settings_path, args.limit)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ib = IB()
    try:
        ok = ib.connect(host, port, clientId=client_id, timeout=float(args.timeout_sec), readonly=True)
        if not ok:
            raise RuntimeError(f"connect false host={host} port={port}")

        # Force delayed data in demo/paper when realtime subscriptions are missing.
        ib.reqMarketDataType(3)

        captured = 0
        failed = 0
        errors: list[str] = []
        ts_tag = _utc_now().strftime("%Y%m%dT%H%M%SZ")

        for sym in symbols:
            try:
                contract = Stock(sym, "SMART", "USD")
                qualified = ib.qualifyContracts(contract)
                if not qualified:
                    raise RuntimeError("qualifyContracts empty")
                c = qualified[0]

                tkr = ib.reqMktData(c, "", snapshot=True, regulatorySnapshot=False)
                ib.sleep(float(args.snapshot_wait_sec))
                payload = _snapshot_payload(sym, tkr, _utc_now())
                ib.cancelMktData(c)

                # Ensure at least one numeric market field exists
                if all(payload.get(k) is None for k in ("bid", "ask", "last", "close", "volume")):
                    raise RuntimeError("snapshot vuoto")

                path = out_dir / f"{sym}__quote__{ts_tag}.json"
                dpl.write_json(path, payload)
                captured += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{sym}: {type(exc).__name__}: {exc}")

        return {
            "ok": failed == 0,
            "host": host,
            "port": port,
            "client_id": client_id,
            "symbols": symbols,
            "captured": captured,
            "failed": failed,
            "out_dir": out_dir.as_posix(),
            "errors": errors[:20],
        }
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="ibkr_demo_fetch_inbox")
    p.add_argument("--profile", default="paper")
    p.add_argument("--host", default="")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--client-id", type=int, default=None)
    p.add_argument("--symbols", default="")
    p.add_argument("--settings-path", default="")
    p.add_argument("--limit", type=int, default=12)
    p.add_argument("--snapshot-wait-sec", type=float, default=2.0)
    p.add_argument("--timeout-sec", type=float, default=4.0)
    p.add_argument("--out-dir", default=str(dpl.DATA_ROOT / "inbox"))
    p.add_argument("--format", choices=["line", "json"], default="line")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_fetch(args)
    except RuntimeError as exc:
        print(f"IBKR_DEMO_FETCH FAIL reason={exc}")
        return 2

    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            "IBKR_DEMO_FETCH "
            f"captured={summary['captured']} failed={summary['failed']} "
            f"host={summary['host']} port={summary['port']} out={summary['out_dir']}"
        )
        for e in summary.get("errors", []):
            print(f"- {e}")

    return 0 if summary.get("captured", 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

