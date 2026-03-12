from __future__ import annotations

"""
F1-T1 - Market data ingestion (daily OHLCV) into DuckDB + completeness report.

DuckDB-only implementation:
- Requires DuckDB (requirements-core)

Table: `market_data`
Primary key: (symbol, dt)
"""

import csv
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import duckdb  # type: ignore
except Exception:  # pragma: no cover
    duckdb = None  # type: ignore


@dataclass(frozen=True)
class DailyBar:
    dt: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: int
    split_factor: float = 1.0


def _parse_date(s: str) -> date:
    return date.fromisoformat(s.strip())


def load_daily_bars_csv(path: Path) -> list[DailyBar]:
    if not path.exists():
        raise FileNotFoundError(f"missing CSV: {path}")
    out: list[DailyBar] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        required = {"date", "open", "high", "low", "close", "adj_close", "volume"}
        if not required.issubset(set(r.fieldnames or [])):
            raise ValueError(f"CSV missing required columns: {sorted(required)} got={r.fieldnames}")
        for row in r:
            out.append(
                DailyBar(
                    dt=_parse_date(row["date"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    adj_close=float(row["adj_close"]),
                    volume=int(float(row["volume"])),
                    split_factor=float(row.get("split_factor") or 1.0),
                )
            )
    if not out:
        raise ValueError(f"empty CSV: {path}")
    out.sort(key=lambda b: b.dt)
    return out


def connect_db(path: Path) -> Any:
    """Return a DB-API-ish connection.

    - DuckDB: duckdb.connect()
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if duckdb is None:
        raise RuntimeError("duckdb is required by project policy")
    return duckdb.connect(str(path))


def _execute(con: Any, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> Any:
    if params is None:
        return con.execute(sql)
    return con.execute(sql, params)


def ensure_market_schema(con: Any) -> None:
    # DuckDB schema for market ingestion.
    _execute(
        con,
        """
        CREATE TABLE IF NOT EXISTS market_data (
            symbol TEXT NOT NULL,
            dt TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            adj_close REAL,
            volume INTEGER,
            split_factor REAL,
            source TEXT,
            ingested_at TEXT,
            PRIMARY KEY(symbol, dt)
        );
        """,
    )


def ingest_daily_bars(
    con: Any,
    *,
    symbol: str,
    bars: Iterable[DailyBar],
    source: str = "csv",
) -> int:
    ensure_market_schema(con)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    rows = [
        (symbol, b.dt.isoformat(), b.open, b.high, b.low, b.close, b.adj_close, b.volume, b.split_factor, source, now)
        for b in bars
    ]
    con.executemany(
        "INSERT OR REPLACE INTO market_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    try:
        con.commit()
    except Exception:
        pass
    return len(rows)


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(days=7 * (n - 1))


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _easter_date(year: int) -> date:
    # Anonymous Gregorian algorithm
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _observed_fixed(dt: date) -> date:
    # NYSE observed: Sat -> Fri, Sun -> Mon
    if dt.weekday() == 5:
        return dt - timedelta(days=1)
    if dt.weekday() == 6:
        return dt + timedelta(days=1)
    return dt


def nyse_holidays_approx(year: int) -> set[date]:
    """Approx NYSE holiday set (sufficient for DEV gating checks).

    Not intended to be exhaustive for exceptional closures.
    """
    hol: set[date] = set()
    hol.add(_observed_fixed(date(year, 1, 1)))  # New Year
    hol.add(_nth_weekday_of_month(year, 1, 0, 3))  # MLK day
    hol.add(_nth_weekday_of_month(year, 2, 0, 3))  # Presidents day
    hol.add(_easter_date(year) - timedelta(days=2))  # Good Friday
    hol.add(_last_weekday_of_month(year, 5, 0))  # Memorial day
    if year >= 2022:
        hol.add(_observed_fixed(date(year, 6, 19)))  # Juneteenth
    hol.add(_observed_fixed(date(year, 7, 4)))  # Independence
    hol.add(_nth_weekday_of_month(year, 9, 0, 1))  # Labor day
    hol.add(_nth_weekday_of_month(year, 11, 3, 4))  # Thanksgiving
    hol.add(_observed_fixed(date(year, 12, 25)))  # Christmas
    return hol


def expected_trading_days(start: date, end: date) -> list[date]:
    cur = start
    out: list[date] = []
    hol_by_year: dict[int, set[date]] = {}
    while cur <= end:
        if cur.weekday() < 5:
            hol = hol_by_year.setdefault(cur.year, nyse_holidays_approx(cur.year))
            if cur not in hol:
                out.append(cur)
        cur += timedelta(days=1)
    return out


def _as_date(v: Any) -> date:
    if isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return date.fromisoformat(v)
    raise TypeError(f"cannot convert to date: {type(v)} {v!r}")


def validate_non_null(con: Any, symbol: str) -> dict[str, int]:
    row = _execute(
        con,
        """
        SELECT
            SUM(CASE WHEN open IS NULL THEN 1 ELSE 0 END) AS n_open_null,
            SUM(CASE WHEN high IS NULL THEN 1 ELSE 0 END) AS n_high_null,
            SUM(CASE WHEN low IS NULL THEN 1 ELSE 0 END) AS n_low_null,
            SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) AS n_close_null,
            SUM(CASE WHEN adj_close IS NULL THEN 1 ELSE 0 END) AS n_adj_close_null,
            SUM(CASE WHEN volume IS NULL THEN 1 ELSE 0 END) AS n_volume_null
        FROM market_data
        WHERE symbol = ?
        """,
        [symbol],
    ).fetchone()
    keys = ["open", "high", "low", "close", "adj_close", "volume"]
    vals = [int(v or 0) for v in row]
    return {k: v for k, v in zip(keys, vals)}


def validate_trading_day_gaps(con: Any, symbol: str) -> dict[str, object]:
    dates_raw = [d[0] for d in _execute(con, "SELECT dt FROM market_data WHERE symbol=? ORDER BY dt", [symbol]).fetchall()]
    if not dates_raw:
        return {"missing": 0, "missing_dates": []}
    dates = [_as_date(v) for v in dates_raw]
    start = dates[0]
    end = dates[-1]
    expected = expected_trading_days(start, end)
    got = set(dates)
    missing = [d for d in expected if d not in got]
    return {"missing": len(missing), "missing_dates": [d.isoformat() for d in missing[:50]]}


def validate_split_adjustment(
    con: Any,
    *,
    symbol: str,
    split_date: date,
    split_ratio: float,
    tol_ratio: float = 0.02,
) -> dict[str, object]:
    prev = _execute(
        con,
        "SELECT dt, close, adj_close FROM market_data WHERE symbol=? AND dt < ? ORDER BY dt DESC LIMIT 1",
        [symbol, split_date.isoformat()],
    ).fetchone()
    cur = _execute(
        con,
        "SELECT dt, close, adj_close FROM market_data WHERE symbol=? AND dt = ?",
        [symbol, split_date.isoformat()],
    ).fetchone()

    if not prev or not cur:
        return {"ok": False, "reason": "missing prev/split rows"}

    prev_close = float(prev[1])
    cur_close = float(cur[1])
    prev_adj = float(prev[2])
    cur_adj = float(cur[2])

    if cur_close == 0.0:
        return {"ok": False, "reason": "split close is zero"}

    ratio = prev_close / cur_close
    adj_cont = prev_adj / cur_adj if cur_adj != 0.0 else math.inf

    ok = (abs(ratio - split_ratio) <= tol_ratio * split_ratio) and (abs(adj_cont - 1.0) <= tol_ratio)

    return {
        "ok": ok,
        "prev_dt": str(prev[0]),
        "split_dt": str(cur[0]),
        "close_ratio": ratio,
        "expected_ratio": split_ratio,
        "adj_close_ratio": adj_cont,
        "tol_ratio": tol_ratio,
    }


def build_ingestion_report(
    con: Any,
    *,
    symbol: str,
    split_date: Optional[date] = None,
    split_ratio: Optional[float] = None,
) -> dict[str, object]:
    n = int(_execute(con, "SELECT COUNT(*) FROM market_data WHERE symbol=?", [symbol]).fetchone()[0])
    rng = _execute(con, "SELECT MIN(dt), MAX(dt) FROM market_data WHERE symbol=?", [symbol]).fetchone()
    date_min = _as_date(rng[0]).isoformat() if rng and rng[0] else None
    date_max = _as_date(rng[1]).isoformat() if rng and rng[1] else None

    non_null = validate_non_null(con, symbol)
    gaps = validate_trading_day_gaps(con, symbol)
    split = None
    if split_date and split_ratio:
        split = validate_split_adjustment(con, symbol=symbol, split_date=split_date, split_ratio=split_ratio)

    return {
        "symbol": symbol,
        "rows": n,
        "date_min": date_min,
        "date_max": date_max,
        "null_counts": non_null,
        "gap_check": gaps,
        "split_check": split,
    }


def ingest_csv_to_duckdb(
    *,
    csv_path: Path,
    duckdb_path: Path,
    symbol: str,
    source: str = "csv",
) -> dict[str, object]:
    bars = load_daily_bars_csv(csv_path)
    con = connect_db(duckdb_path)
    try:
        n = ingest_daily_bars(con, symbol=symbol, bars=bars, source=source)
        report = build_ingestion_report(con, symbol=symbol, split_date=date(2022, 6, 6), split_ratio=4.0)
        report["ingested_rows"] = n
        report["engine"] = "duckdb"
        return report
    finally:
        try:
            con.close()
        except Exception:
            pass
