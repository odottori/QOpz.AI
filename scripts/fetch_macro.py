"""
scripts/fetch_macro.py — Ingestione indicatori macro da yfinance

Fetcha i principali indicatori macro di mercato (VIX, VIX3M, yield 10Y)
usando yfinance come sorgente gratuita senza API key.

Indicatori:
  ^VIX   — CBOE Volatility Index (30 giorni)
  ^VIX3M — CBOE 93-day Volatility Index
  ^TNX   — US Treasury Yield 10 anni (%)
  ^TYX   — US Treasury Yield 30 anni (%)

I dati vengono salvati nella tabella `macro_indicators` del DB di esecuzione.
La tabella ha PK (ticker, dt) — INSERT OR REPLACE (idempotente).

CLI:
    python scripts/fetch_macro.py
    python scripts/fetch_macro.py --days 30
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Indicatori da fetchare: (ticker_yfinance, serie_name, unit)
MACRO_TICKERS: list[tuple[str, str, str]] = [
    ("^VIX",   "vix",    "index"),
    ("^VIX3M", "vix3m",  "index"),
    ("^TNX",   "tnx_10y","pct"),
    ("^TYX",   "tyx_30y","pct"),
]

DEFAULT_LOOKBACK_DAYS = 90

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore[assignment]


# ─────────────────────────────────────────────────────────────────────────────
# Schema e storage
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_schema(con: Any) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS macro_indicators (
            ticker      TEXT NOT NULL,
            series_name TEXT NOT NULL,
            unit        TEXT,
            dt          TEXT NOT NULL,
            open        REAL,
            high        REAL,
            low         REAL,
            close       REAL,
            volume      BIGINT,
            ingested_at TEXT NOT NULL,
            PRIMARY KEY (ticker, dt)
        )
    """)


def _connect(profile: str = "paper") -> Any:
    import duckdb
    from execution.storage import EXEC_DB_PATH
    path = EXEC_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


# ─────────────────────────────────────────────────────────────────────────────
# Fetch + save
# ─────────────────────────────────────────────────────────────────────────────

def fetch_macro_indicators(
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    profile: str = "paper",
) -> dict[str, Any]:
    """Fetcha tutti i ticker macro e salva in DuckDB.

    Ritorna un dict con:
      n_series  — numero di serie processate
      n_saved   — righe salvate totali
      n_errors  — serie in errore
      details   — {ticker: {"rows": int, "error": str|None}}
    """
    if yf is None:
        return {"n_series": 0, "n_saved": 0, "n_errors": 0,
                "error": "yfinance non disponibile"}

    now_iso = datetime.now(timezone.utc).isoformat()
    details: dict[str, Any] = {}
    total_saved = 0
    n_errors = 0

    con = _connect(profile)
    try:
        _ensure_schema(con)

        for ticker, series_name, unit in MACRO_TICKERS:
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period=f"{lookback_days}d", auto_adjust=True)
                if hist is None or hist.empty:
                    details[ticker] = {"rows": 0, "error": "nessun dato da yfinance"}
                    n_errors += 1
                    continue

                rows = []
                for idx, row in hist.iterrows():
                    dt_str = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
                    rows.append((
                        ticker, series_name, unit, dt_str,
                        float(row.get("Open") or 0) or None,
                        float(row.get("High") or 0) or None,
                        float(row.get("Low") or 0) or None,
                        float(row.get("Close") or 0) or None,
                        int(row.get("Volume") or 0) or None,
                        now_iso,
                    ))

                con.executemany(
                    """
                    INSERT OR REPLACE INTO macro_indicators
                    (ticker, series_name, unit, dt, open, high, low, close, volume, ingested_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                try:
                    con.commit()
                except Exception:
                    pass

                details[ticker] = {"rows": len(rows), "error": None}
                total_saved += len(rows)
                logger.info("fetch_macro: %s → %d righe salvate", ticker, len(rows))

            except Exception as exc:
                details[ticker] = {"rows": 0, "error": str(exc)}
                n_errors += 1
                logger.warning("fetch_macro: %s fallito: %s", ticker, exc)
    finally:
        con.close()

    return {
        "n_series": len(MACRO_TICKERS),
        "n_saved": total_saved,
        "n_errors": n_errors,
        "details": details,
    }


def latest_macro_snapshot(profile: str = "paper") -> dict[str, Any]:
    """Ritorna l'ultimo valore disponibile per ogni serie macro."""
    con = _connect(profile)
    try:
        _ensure_schema(con)
        rows = con.execute("""
            SELECT ticker, series_name, unit, dt, close
            FROM macro_indicators
            WHERE (ticker, dt) IN (
                SELECT ticker, MAX(dt) FROM macro_indicators GROUP BY ticker
            )
            ORDER BY ticker
        """).fetchall()
        return {
            row[0]: {
                "series": row[1], "unit": row[2],
                "date": row[3], "value": row[4],
            }
            for row in rows
        }
    except Exception as exc:
        logger.warning("latest_macro_snapshot: %s", exc)
        return {}
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch indicatori macro (VIX, yield)")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help=f"Giorni di storico (default {DEFAULT_LOOKBACK_DAYS})")
    parser.add_argument("--profile", default="paper")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    result = fetch_macro_indicators(lookback_days=args.days, profile=args.profile)
    print(f"Serie processate: {result['n_series']}")
    print(f"Righe salvate:    {result['n_saved']}")
    print(f"Errori:           {result['n_errors']}")
    for ticker, d in result.get("details", {}).items():
        status = "OK" if not d["error"] else f"ERR: {d['error']}"
        print(f"  {ticker:10s}  {d['rows']:4d} righe  {status}")

    snapshot = latest_macro_snapshot(args.profile)
    if snapshot:
        print("\nUltimi valori:")
        for ticker, v in snapshot.items():
            print(f"  {ticker:10s}  {v['series']:8s}  {v['date']}  {v['value']:.2f} {v['unit']}")


if __name__ == "__main__":
    main()
