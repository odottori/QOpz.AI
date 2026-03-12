#!/usr/bin/env python
from __future__ import annotations
import argparse
from pathlib import Path
import datetime as dt
import json
try:
    import tomllib
except Exception:
    tomllib = None

def load_config(p: Path):
    if p.suffix.lower()==".toml":
        if tomllib is None:
            raise RuntimeError("Python 3.11+ required for TOML config.")
        return tomllib.loads(p.read_text(encoding="utf-8"))
    if p.suffix.lower()==".json":
        return json.loads(p.read_text(encoding="utf-8"))
    raise RuntimeError("Config must be .toml or .json")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    cfg = load_config(Path(args.config))
    db_path = Path(cfg.get("storage",{}).get("duckdb_path","db/quantoptionai.duckdb"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        db_path.write_bytes(b"")
    marker = Path("db/schema_applied.ok")
    marker.write_text(f"schema_applied_utc={dt.datetime.now(dt.UTC).isoformat().replace('+00:00','Z')}\n", encoding="utf-8")
    print(f"OK: {db_path} + {marker}")
if __name__=="__main__":
    main()
