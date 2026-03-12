from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _safe_name(info: Any) -> str:
    try:
        return _norm(str(getattr(info, "name", "") or ""))
    except Exception:
        return ""


def _safe_type(info: Any) -> str:
    try:
        return _norm(str(getattr(info, "control_type", "") or ""))
    except Exception:
        return ""


def _load_backend(backend: str):
    try:
        from pywinauto import Desktop  # type: ignore
    except Exception as exc:
        raise SystemExit(
            "pywinauto non disponibile. Installa con: pip install pywinauto\n"
            f"Dettaglio: {exc}"
        )
    return Desktop(backend=backend)


def _pick_window(desktop: Any, title_re: str):
    windows = desktop.windows()
    rgx = re.compile(title_re, re.IGNORECASE)
    for w in windows:
        title = _norm(w.window_text())
        if rgx.search(title):
            return w
    titles = [_norm(w.window_text()) for w in windows if _norm(w.window_text())]
    raise SystemExit(
        "Finestra non trovata. title_re='{}'\\nFinestre viste: {}".format(
            title_re, ", ".join(titles[:20])
        )
    )


def cmd_probe(args: argparse.Namespace) -> int:
    desktop = _load_backend(args.backend)
    w = _pick_window(desktop, args.title_re)
    root = w.element_info

    out: list[dict[str, Any]] = []

    def walk(info: Any, level: int) -> None:
        if level > args.max_depth:
            return
        out.append(
            {
                "level": level,
                "name": _safe_name(info),
                "control_type": _safe_type(info),
                "automation_id": _norm(str(getattr(info, "automation_id", "") or "")),
                "class_name": _norm(str(getattr(info, "class_name", "") or "")),
            }
        )
        for ch in info.children():
            walk(ch, level + 1)

    walk(root, 0)

    payload = {
        "ts_utc": _utc_now(),
        "window_title": _norm(w.window_text()),
        "backend": args.backend,
        "max_depth": args.max_depth,
        "nodes": out,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK probe -> {out_path} nodes={len(out)}")
    return 0


def _first_grid(info: Any):
    queue = [info]
    while queue:
        cur = queue.pop(0)
        ctype = _safe_type(cur).lower()
        if ctype in {"table", "datagrid", "list"}:
            return cur
        queue.extend(cur.children())
    return None


def _row_to_cells(row_info: Any) -> list[str]:
    vals: list[str] = []
    for ch in row_info.children():
        txt = _safe_name(ch)
        if txt:
            vals.append(txt)
        else:
            for d in ch.descendants():
                dtxt = _safe_name(d)
                if dtxt:
                    vals.append(dtxt)
                    break
    return vals


def cmd_extract(args: argparse.Namespace) -> int:
    desktop = _load_backend(args.backend)
    w = _pick_window(desktop, args.title_re)
    root = w.element_info

    grid = _first_grid(root)
    if grid is None:
        raise SystemExit("Nessuna griglia UIA trovata (Table/DataGrid/List).")

    rows = [ch for ch in grid.children() if _safe_type(ch).lower() in {"dataitem", "listitem", "row"}]
    extracted: list[dict[str, Any]] = []
    for i, r in enumerate(rows[: args.max_rows], start=1):
        cells = _row_to_cells(r)
        if not cells:
            continue
        extracted.append({"row": i, "cells": cells})

    payload = {
        "ts_utc": _utc_now(),
        "window_title": _norm(w.window_text()),
        "backend": args.backend,
        "grid": {
            "name": _safe_name(grid),
            "control_type": _safe_type(grid),
            "class_name": _norm(str(getattr(grid, "class_name", "") or "")),
        },
        "rows": extracted,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK extract -> {out_path} rows={len(extracted)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ibkr_uia_extract")
    p.add_argument("--backend", default="uia", choices=["uia", "win32"])
    p.add_argument("--title-re", default=r"(Trader Workstation|TWS|IBKR)")

    sub = p.add_subparsers(dest="cmd", required=True)

    p_probe = sub.add_parser("probe", help="Dump controllo albero UI")
    p_probe.add_argument("--max-depth", type=int, default=4)
    p_probe.add_argument("--output", default="data/ibkr_uia/probe.json")
    p_probe.set_defaults(func=cmd_probe)

    p_ex = sub.add_parser("extract", help="Estrai righe da prima griglia UIA trovata")
    p_ex.add_argument("--max-rows", type=int, default=500)
    p_ex.add_argument("--output", default="data/ibkr_uia/extract.json")
    p_ex.set_defaults(func=cmd_extract)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
