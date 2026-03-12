import importlib
from pathlib import Path
from datetime import datetime, timezone

# IMPORTANT:
# Phase0 may ship with db/quantoptionai.duckdb that is not a real DuckDB database file in some snapshots.
# Domain 2 execution must not depend on that artifact. We isolate execution state to a dedicated DB file.
EXEC_DB_PATH = Path("db/execution.duckdb")


def _require_duckdb():
    try:
        return importlib.import_module("duckdb")
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Missing dependency: duckdb. Install core deps with: py -m pip install -r requirements-core.txt"
        ) from e


def _connect(duckdb):
    """Connect to the execution DB. If the file exists but is invalid/corrupt, create a new one non-destructively."""
    try:
        return duckdb.connect(str(EXEC_DB_PATH))
    except Exception:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        fallback = Path(f"db/execution_recovered_{ts}.duckdb")
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(fallback))


def init_table():
    duckdb = _require_duckdb()
    con = _connect(duckdb)
    con.execute("""
        CREATE TABLE IF NOT EXISTS execution_orders (
            client_order_id VARCHAR PRIMARY KEY,
            symbol VARCHAR,
            side VARCHAR,
            quantity INTEGER,
            created_at TIMESTAMP
        )
    """)
    con.close()


def insert_order(client_order_id, symbol, side, quantity, created_at):
    duckdb = _require_duckdb()
    con = _connect(duckdb)
    try:
        con.execute(
            "INSERT INTO execution_orders VALUES (?, ?, ?, ?, ?)",
            (client_order_id, symbol, side, quantity, created_at),
        )
        con.close()
        return True
    except Exception:
        con.close()
        return False
