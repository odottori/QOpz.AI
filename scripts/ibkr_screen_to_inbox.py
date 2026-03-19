from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _norm_key(s: str) -> str:
    return "".join(ch for ch in (s or "").strip().lower() if ch.isalnum())


def _pick(row: dict[str, Any], aliases: list[str]) -> Any:
    for a in aliases:
        if a in row:
            return row.get(a)
    return None


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace("%", "")
    if not s:
        return None
    s = s.replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def _read_rows(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    sample = raw[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except Exception:
        class _D(csv.Dialect):
            delimiter = "\t"
            quotechar = '"'
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL
        dialect = _D

    rows: list[dict[str, Any]] = []
    reader = csv.reader(raw.splitlines(), dialect)
    all_rows = list(reader)
    if not all_rows:
        return rows

    headers = [_norm_key(x) for x in all_rows[0]]
    for r in all_rows[1:]:
        if not any(str(x).strip() for x in r):
            continue
        obj: dict[str, Any] = {}
        for i, h in enumerate(headers):
            if not h:
                continue
            obj[h] = r[i] if i < len(r) else ""
        rows.append(obj)
    return rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    inp = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_rows(inp)
    ts_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    written = 0
    skipped = 0
    files: list[str] = []

    for row in rows:
        symbol = _pick(
            row,
            [
                "strumentofinanziario",
                "symbol",
                "simbolo",
                "ticker",
                "strumento",
            ],
        )
        sym = str(symbol or "").strip().upper()
        if not sym or len(sym) > 20:
            skipped += 1
            continue

        bid = _to_float(_pick(row, ["bid", "denaro"]))
        ask = _to_float(_pick(row, ["ask", "lettera"]))
        last = _to_float(_pick(row, ["ultimo", "last", "prezzo", "prezzota", "prezzooperazione"]))
        volume = _to_float(_pick(row, ["volume", "vol", "volumegiornaliero"]))
        iv = _to_float(_pick(row, ["viopz", "ivopzioni", "iv", "impliedvolatility"]))

        if bid is None and ask is None and last is None:
            skipped += 1
            continue

        payload = {
            "source": "ibkr_screen_file",
            "symbol": sym,
            "page_type": "quote",
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "bid": bid,
            "ask": ask,
            "last": last,
            "volume": int(volume) if volume is not None else None,
            "iv": iv / 100.0 if (iv is not None and iv > 1.0) else iv,
            "raw_row": row,
        }

        path = out_dir / f"{sym}__quote__{ts_tag}_{written+1:03d}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        files.append(path.as_posix())
        written += 1

    return {
        "input": inp.as_posix(),
        "out_dir": out_dir.as_posix(),
        "rows_total": len(rows),
        "written": written,
        "skipped": skipped,
        "files": files[:20],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="ibkr_screen_to_inbox")
    p.add_argument("--input", required=True, help="file csv/tsv export schermata IBKR")
    p.add_argument("--out-dir", default="data/demo_pipeline/inbox")
    p.add_argument("--format", choices=["line", "json"], default="line")
    return p.parse_args(argv)


if __name__ == "__main__":
    a = parse_args()
    out = run(a)
    if a.format == "json":
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            "IBKR_SCREEN_IMPORT "
            f"rows_total={out['rows_total']} written={out['written']} skipped={out['skipped']} out_dir={out['out_dir']}"
        )
