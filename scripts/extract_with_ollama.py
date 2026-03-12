from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from scripts import demo_pipeline_lib as dpl
except ModuleNotFoundError:  # support direct execution: py scripts\extract_with_ollama.py
    import demo_pipeline_lib as dpl

PROMPT_VERSION = "v1"
VALIDATOR_VERSION = "v1"


def _try_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _first_key(d: dict[str, Any], keys: list[str]) -> Any:
    for k in keys:
        if k in d:
            return d[k]
    return None


def _extract_from_dict(raw: dict[str, Any], *, symbol: str, page_type: str) -> dict[str, Any]:
    nested = raw.get("data") if isinstance(raw.get("data"), dict) else raw

    rec = {
        "symbol": symbol,
        "page_type": page_type,
        "observed_ts_utc": _first_key(raw, ["ts", "timestamp", "time", "quote_time", "asof"]) or _first_key(nested, ["ts", "timestamp", "time", "quote_time", "asof"]),
        "bid": _try_float(_first_key(nested, ["bid", "best_bid", "b"])),
        "ask": _try_float(_first_key(nested, ["ask", "best_ask", "a"])),
        "last": _try_float(_first_key(nested, ["last", "price", "mark", "mid"])),
        "iv": _try_float(_first_key(nested, ["iv", "implied_volatility", "impl_vol"])),
        "delta": _try_float(_first_key(nested, ["delta"])),
        "underlying_price": _try_float(_first_key(nested, ["underlying_price", "underlying", "spot", "underlyingLast"])),
    }
    return rec


def _extract_from_text(raw_text: str, *, symbol: str, page_type: str) -> dict[str, Any]:
    def _pick_num(pattern: str) -> float | None:
        m = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if not m:
            return None
        return _try_float(m.group(1))

    return {
        "symbol": symbol,
        "page_type": page_type,
        "observed_ts_utc": None,
        "bid": _pick_num(r"\"?bid\"?\s*[:=]\s*([-+]?\d+(?:\.\d+)?)"),
        "ask": _pick_num(r"\"?ask\"?\s*[:=]\s*([-+]?\d+(?:\.\d+)?)"),
        "last": _pick_num(r"\"?(?:last|price|mid)\"?\s*[:=]\s*([-+]?\d+(?:\.\d+)?)"),
        "iv": _pick_num(r"\"?iv\"?\s*[:=]\s*([-+]?\d+(?:\.\d+)?)"),
        "delta": _pick_num(r"\"?delta\"?\s*[:=]\s*([-+]?\d+(?:\.\d+)?)"),
        "underlying_price": _pick_num(r"\"?(?:underlying|spot)\"?\s*[:=]\s*([-+]?\d+(?:\.\d+)?)"),
    }


def _extract_with_ollama(raw_text: str, *, symbol: str, page_type: str, model: str, timeout_sec: int) -> dict[str, Any]:
    prompt = (
        "Extract market fields as strict JSON object only. "
        "No prose. Keys: symbol,page_type,observed_ts_utc,bid,ask,last,iv,delta,underlying_price. "
        "Keep null if unknown.\n"
        f"symbol={symbol}\npage_type={page_type}\nraw:\n{raw_text[:12000]}"
    )
    proc = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ollama failed").strip())
    out = (proc.stdout or "").strip()
    start = out.find("{")
    end = out.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("ollama output has no JSON object")
    parsed = json.loads(out[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("ollama output is not a JSON object")
    return parsed


def _validate(rec: dict[str, Any], *, symbol: str, page_type: str) -> tuple[bool, str]:
    if rec.get("symbol") != symbol:
        return False, "symbol mismatch"
    if rec.get("page_type") != page_type:
        return False, "page_type mismatch"

    bid = _try_float(rec.get("bid"))
    ask = _try_float(rec.get("ask"))
    last = _try_float(rec.get("last"))
    iv = _try_float(rec.get("iv"))
    delta = _try_float(rec.get("delta"))
    under = _try_float(rec.get("underlying_price"))

    if bid is not None and bid < 0:
        return False, "bid < 0"
    if ask is not None and ask < 0:
        return False, "ask < 0"
    if bid is not None and ask is not None and ask < bid:
        return False, "ask < bid"
    if iv is not None and not (0 <= iv <= 5):
        return False, "iv out of range"
    if delta is not None and not (-1 <= delta <= 1):
        return False, "delta out of range"
    if under is not None and under < 0:
        return False, "underlying_price < 0"

    if all(v is None for v in (bid, ask, last, iv, delta, under)):
        return False, "no numeric fields extracted"

    rec["bid"] = bid
    rec["ask"] = ask
    rec["last"] = last
    rec["iv"] = iv
    rec["delta"] = delta
    rec["underlying_price"] = under
    return True, "ok"


def _log_event(log_path: Path, payload: dict[str, Any]) -> None:
    dpl.append_jsonl(log_path, {"ts_utc": dpl.utc_now_iso(), **payload})


def _pending_captures(conn: Any, *, model: str, prompt_version: str, limit: int) -> list[dict[str, Any]]:
    rows = dpl.fetchall_dicts(
        conn,
        """
        SELECT c.id, c.symbol, c.page_type, c.raw_path, c.fingerprint_sha256
        FROM captures c
        LEFT JOIN extractions e
          ON e.capture_id = c.id AND e.model = ? AND e.prompt_version = ?
        WHERE c.status = 'CAPTURED' AND e.id IS NULL
        ORDER BY c.id ASC
        LIMIT ?
        """,
        (model, prompt_version, limit),
    )
    return rows


def run_extract(args: argparse.Namespace) -> dict[str, Any]:
    conn = dpl.connect_db(Path(args.db))
    dpl.init_db(conn)

    pending = _pending_captures(conn, model=args.model, prompt_version=args.prompt_version, limit=args.limit)
    valid = 0
    needs_review = 0
    errors = 0

    for row in pending:
        capture_id = int(row["id"])
        symbol = str(row["symbol"])
        page_type = str(row["page_type"])
        raw_path = Path(str(row["raw_path"]))

        if not raw_path.exists():
            conn.execute(
                """
                INSERT INTO extractions(
                    capture_id, extracted_ts_utc, model, prompt_version, backend,
                    attempts, status, output_path, error_text
                ) VALUES (?, ?, ?, ?, ?, ?, 'ERROR', NULL, ?)
                """,
                (
                    capture_id,
                    dpl.utc_now_iso(),
                    args.model,
                    args.prompt_version,
                    args.backend,
                    0,
                    f"missing raw file: {raw_path.as_posix()}",
                ),
            )
            errors += 1
            continue

        raw_text = raw_path.read_text(encoding="utf-8-sig", errors="replace")

        final_rec: dict[str, Any] | None = None
        final_error = ""
        attempts = 0
        for attempts in range(1, max(1, args.max_retries) + 1):
            try:
                if args.backend == "ollama":
                    rec = _extract_with_ollama(
                        raw_text,
                        symbol=symbol,
                        page_type=page_type,
                        model=args.model,
                        timeout_sec=args.timeout_sec,
                    )
                else:
                    try:
                        parsed = json.loads(raw_text)
                        if isinstance(parsed, dict):
                            rec = _extract_from_dict(parsed, symbol=symbol, page_type=page_type)
                        else:
                            rec = _extract_from_text(raw_text, symbol=symbol, page_type=page_type)
                    except Exception:
                        rec = _extract_from_text(raw_text, symbol=symbol, page_type=page_type)

                ok, why = _validate(rec, symbol=symbol, page_type=page_type)
                if ok:
                    final_rec = rec
                    final_error = ""
                    break
                final_error = why
                _log_event(
                    Path(args.log_path),
                    {
                        "event": "invalid_json",
                        "capture_id": capture_id,
                        "attempt": attempts,
                        "backend": args.backend,
                        "error": final_error,
                    },
                )
            except Exception as exc:
                final_error = str(exc)
                _log_event(
                    Path(args.log_path),
                    {
                        "event": "invalid_json",
                        "capture_id": capture_id,
                        "attempt": attempts,
                        "backend": args.backend,
                        "error": final_error,
                    },
                )

        if final_rec is not None:
            out_path = Path(args.out_dir) / f"{capture_id}.json"
            dpl.write_json(
                out_path,
                {
                    "capture_id": capture_id,
                    "model": args.model,
                    "prompt_version": args.prompt_version,
                    "backend": args.backend,
                    "validator_version": VALIDATOR_VERSION,
                    "record": final_rec,
                    "source_raw_path": raw_path.as_posix(),
                    "fingerprint_sha256": str(row["fingerprint_sha256"]),
                },
            )
            conn.execute(
                """
                INSERT INTO extractions(
                    capture_id, extracted_ts_utc, model, prompt_version, backend,
                    attempts, status, output_path, error_text
                ) VALUES (?, ?, ?, ?, ?, ?, 'VALID', ?, NULL)
                """,
                (
                    capture_id,
                    dpl.utc_now_iso(),
                    args.model,
                    args.prompt_version,
                    args.backend,
                    attempts,
                    out_path.as_posix(),
                ),
            )
            valid += 1
            _log_event(
                Path(args.log_path),
                {
                    "event": "validated",
                    "capture_id": capture_id,
                    "status": "VALID",
                    "output_path": out_path.as_posix(),
                    "backend": args.backend,
                    "model": args.model,
                    "prompt_version": args.prompt_version,
                    "validator_version": VALIDATOR_VERSION,
                },
            )
            continue

        conn.execute(
            """
            INSERT INTO extractions(
                capture_id, extracted_ts_utc, model, prompt_version, backend,
                attempts, status, output_path, error_text
            ) VALUES (?, ?, ?, ?, ?, ?, 'NEEDS_REVIEW', NULL, ?)
            """,
            (
                capture_id,
                dpl.utc_now_iso(),
                args.model,
                args.prompt_version,
                args.backend,
                attempts,
                final_error,
            ),
        )
        needs_review += 1
        _log_event(
            Path(args.log_path),
            {
                "event": "needs_review",
                "capture_id": capture_id,
                "status": "NEEDS_REVIEW",
                "error": final_error,
                "backend": args.backend,
                "model": args.model,
                "prompt_version": args.prompt_version,
                "validator_version": VALIDATOR_VERSION,
            },
        )

    out = {
        "pending": len(pending),
        "valid": valid,
        "needs_review": needs_review,
        "errors": errors,
        "backend": args.backend,
        "model": args.model,
        "prompt_version": args.prompt_version,
    }
    conn.close()
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="extract_with_ollama")
    p.add_argument("--db", default=str(dpl.DEFAULT_DB))
    p.add_argument("--out-dir", default=str(dpl.DEFAULT_EXTRACTED_DIR))
    p.add_argument("--backend", choices=["ollama", "json-pass"], default="json-pass")
    p.add_argument("--model", default="qwen2.5")
    p.add_argument("--prompt-version", default=PROMPT_VERSION)
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--timeout-sec", type=int, default=45)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--log-path", default=str(dpl.DEFAULT_LOG_DIR / "extract.jsonl"))
    p.add_argument("--format", choices=["line", "json"], default="line")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_extract(args)
    except RuntimeError as exc:
        print(f"EXTRACT_WITH_OLLAMA FAIL reason={exc}")
        return 2

    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            "EXTRACT_WITH_OLLAMA "
            f"pending={summary['pending']} valid={summary['valid']} "
            f"needs_review={summary['needs_review']} errors={summary['errors']} "
            f"backend={summary['backend']} model={summary['model']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


