from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import db_integrity


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="f1_t4_db_integrity")
    p.add_argument("--outdir", default="reports")
    p.add_argument("--backend", default="duckdb", choices=["duckdb", "auto"])
    p.add_argument("--seed", action="store_true", help="Seed a synthetic execution dataset before checks (safe for temp DBs).")
    p.add_argument("--db", default=":memory:", help="DB path for execution integrity checks. Use :memory: for in-memory duckdb.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outdir = Path(args.outdir)

    con = db_integrity.connect(args.db, backend=args.backend)
    try:
        if args.seed:
            db_integrity.seed_execution_synthetic(con)
        res = db_integrity.run_execution_integrity_checks(con)
    finally:
        try:
            con.close()
        except Exception:
            pass

    payload = {"ok": res.ok, "errors": res.errors, "report": res.report}
    db_integrity.write_reports(outdir, stem="db_integrity_execution_f1_t4", payload=payload)

    if res.ok:
        print("OK F1-T4 DB integrity execution")
        return 0
    print("FAIL F1-T4 DB integrity execution")
    for e in res.errors:
        print(f"- {e}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

