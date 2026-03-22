from __future__ import annotations

import csv
import importlib
import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ibkr_settings_profile import extract_ibkr_universe_context, pick_ibkr_scanner
from .market_provider_contract import UniverseSnapshotRequest
from .providers.router import ProviderRouter
from .storage import _connect, init_execution_schema


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DB_PATH = ROOT / "data" / "demo_pipeline" / "index.duckdb"
PIPELINE_DATASET_DIR = ROOT / "data" / "demo_pipeline" / "datasets"
ROUTER = ProviderRouter()


@dataclass(frozen=True)
class UniverseItem:
    rank: int
    symbol: str
    strategy: str
    score: float
    iv_rank: float
    spread_pct: float
    volume: int
    open_interest: int
    regime_fit: float
    liquidity_score: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "score": self.score,
            "iv_rank": self.iv_rank,
            "spread_pct": self.spread_pct,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "regime_fit": self.regime_fit,
            "liquidity_score": self.liquidity_score,
        }

class UniverseDataUnavailableError(RuntimeError):
    def __init__(self, detail: dict[str, Any]):
        super().__init__(detail.get("message", "universe data unavailable"))
        self.detail = detail

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def _to_int(value: Any) -> int:
    x = _to_float(value)
    if x is None:
        return 0
    return max(0, int(x))


def _norm_symbol_list(symbols: list[str] | None) -> list[str]:
    if not symbols:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        s = str(raw or "").strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _parse_mm_yyyy(value: str) -> tuple[int, int] | None:
    s = str(value or "").strip()
    parts = s.split("/")
    if len(parts) != 2:
        return None
    try:
        mm = int(parts[0])
        yy = int(parts[1])
    except Exception:
        return None
    if mm < 1 or mm > 12:
        return None
    return yy, mm


def _pick_strategy(iv_rank: float, regime: str) -> str:
    r = regime.upper()
    if r == "SHOCK":
        return "NO_TRADE"
    if iv_rank >= 0.65:
        return "IRON_CONDOR"
    if iv_rank >= 0.45:
        return "BULL_PUT"
    if r == "CAUTION":
        return "WHEEL"
    return "CALENDAR"


def _compute_liquidity(volume: int, open_interest: int, spread_pct: float) -> float:
    v = math.log10(max(1, volume))
    oi = math.log10(max(1, open_interest))
    lv = _clamp01((v - 2.0) / 4.0)
    loi = _clamp01((oi - 2.0) / 4.0)
    spread_quality = _clamp01(1.0 - (spread_pct / 0.020))
    return _clamp01(0.45 * lv + 0.35 * loi + 0.20 * spread_quality)


def _regime_fit(regime: str, iv_rank: float, spread_pct: float) -> float:
    base = 0.65
    r = regime.upper()
    if r == "CAUTION":
        base = 0.48
    elif r == "SHOCK":
        base = 0.12
    # Higher IV helps scanner relevance in NORMAL/CAUTION; wider spread penalizes.
    return _clamp01(base + 0.15 * iv_rank - 0.20 * _clamp01(spread_pct / 0.03))


def _extract_numeric(record: dict[str, Any], keys: list[str]) -> float | None:
    for k in keys:
        if k in record:
            v = _to_float(record.get(k))
            if v is not None:
                return v
    return None


def _load_record_from_output(output_path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    rec = payload.get("record")
    if isinstance(rec, dict):
        return rec
    return None


def _duckdb_module() -> Any | None:
    try:
        return importlib.import_module("duckdb")
    except ModuleNotFoundError:
        return None


def _market_row_from_record(symbol: str, regime: str, rec: dict[str, Any]) -> dict[str, Any] | None:
    bid = _extract_numeric(rec, ["bid", "best_bid", "b"])
    ask = _extract_numeric(rec, ["ask", "best_ask", "a"])
    last = _extract_numeric(rec, ["last", "price", "mid", "mark"])
    underlying = _extract_numeric(rec, ["underlying_price", "underlying", "spot", "underlyingLast"])
    iv = _extract_numeric(rec, ["iv", "implied_volatility", "impl_vol", "opt_imp_vol", "option_iv"])

    price = underlying if underlying is not None else last
    if price is None:
        return None

    if bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid:
        mid = (bid + ask) / 2.0
        spread_pct = (ask - bid) / mid if mid > 0 else 1.0
    else:
        spread_pct = _clamp01(abs((ask or 0) - (bid or 0))) if (bid is not None and ask is not None) else 1.0

    iv_rank = _clamp01((iv or 0.0) / 1.0)
    volume = _to_int(
        _extract_numeric(
            rec,
            [
                "volume",
                "avg_volume",
                "avgVolume",
                "opt_volume",
                "option_volume",
            ],
        )
    )
    open_interest = _to_int(_extract_numeric(rec, ["open_interest", "oi", "option_oi", "optoi"]))
    market_cap_mln = _extract_numeric(rec, ["market_cap_mln", "market_cap", "mktcap", "mkt_cap"]) or 0.0
    if market_cap_mln > 1_000_000:
        market_cap_mln = market_cap_mln / 1_000_000.0

    last_vs_ema20 = _extract_numeric(rec, ["last_vs_ema20", "price_vs_ema_20", "PRICE_VS_EMA_20"]) or 0.0
    last_vs_ema50 = _extract_numeric(rec, ["last_vs_ema50", "price_vs_ema_50", "PRICE_VS_EMA_50"]) or 0.0
    has_options_raw = rec.get("has_options")
    has_options = True if has_options_raw is None else str(has_options_raw).strip().lower() in {"true", "1", "yes"}
    industry = str(rec.get("industry") or rec.get("sector") or "Unknown").strip() or "Unknown"
    dividend_next_date = str(rec.get("dividend_next_date") or rec.get("next_dividend_date") or "").strip() or "01/2030"

    liquidity = _compute_liquidity(volume, open_interest, spread_pct)
    regime_fit = _regime_fit(regime, iv_rank, spread_pct)
    score = _clamp01(0.36 * iv_rank + 0.34 * liquidity + 0.30 * regime_fit)

    return {
        "symbol": symbol,
        "strategy": _pick_strategy(iv_rank, regime),
        "score": score,
        "iv_rank": iv_rank,
        "spread_pct": spread_pct,
        "volume": volume,
        "open_interest": open_interest,
        "regime_fit": regime_fit,
        "liquidity_score": liquidity,
        "price": price,
        "market_cap_mln": market_cap_mln,
        "industry": industry,
        "has_options": has_options,
        "last_vs_ema20": last_vs_ema20,
        "last_vs_ema50": last_vs_ema50,
        "dividend_next_date": dividend_next_date,
    }


def _load_from_pipeline_duckdb(symbols: list[str], regime: str) -> list[dict[str, Any]]:
    if not PIPELINE_DB_PATH.exists():
        return []

    duckdb = _duckdb_module()
    if duckdb is None:
        return []

    symbol_set = {s.upper() for s in symbols}
    con = duckdb.connect(str(PIPELINE_DB_PATH), read_only=True)
    rows = con.execute(
        """
        SELECT c.id, c.symbol, c.page_type, e.output_path
        FROM captures c
        JOIN extractions e ON e.capture_id = c.id
        WHERE e.status = 'VALID'
        ORDER BY c.id DESC
        LIMIT 50000
        """
    ).fetchall()
    con.close()

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, raw_symbol, page_type, output_path in rows:
        symbol = str(raw_symbol or "").strip().upper()
        ptype = str(page_type or "").strip().lower()
        if "__" in ptype and re.match(r"^[a-z_]+__\d{8}t\d{6}z$", ptype):
            ptype = ptype.split("__", 1)[0]
        # Backward compatibility for legacy captures parsed as SYMBOL__TYPE + TIMESTAMP.
        if "__" in symbol and re.match(r"^\d{8}t\d{6}z$", ptype):
            parts = symbol.split("__", 1)
            if len(parts) == 2:
                symbol = parts[0].strip().upper()
                ptype = parts[1].strip().lower()
        if not symbol or symbol in seen:
            continue
        if symbol_set and symbol not in symbol_set:
            continue

        if ptype and ptype not in {"quote", "scanner", "snapshot", "summary", "optionchain", "option_chain"}:
            continue

        op = Path(str(output_path or "").strip())
        if not op.exists() or not op.is_file():
            continue

        rec = _load_record_from_output(op)
        if not rec:
            continue

        row = _market_row_from_record(symbol, regime, rec)
        if row is None:
            continue

        seen.add(symbol)
        out.append(row)

    return out


def _latest_dataset_csv() -> Path | None:
    if not PIPELINE_DATASET_DIR.exists():
        return None
    csvs = [p for p in PIPELINE_DATASET_DIR.glob("*.csv") if p.is_file()]
    if not csvs:
        return None
    csvs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return csvs[0]


def _load_from_dataset_csv(symbols: list[str], regime: str) -> list[dict[str, Any]]:
    csv_path = _latest_dataset_csv()
    if csv_path is None:
        return []

    symbol_set = {s.upper() for s in symbols}
    latest_by_symbol: dict[str, dict[str, Any]] = {}

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            if symbol_set and symbol not in symbol_set:
                continue

            prev = latest_by_symbol.get(symbol)
            cur_id = _to_int(row.get("capture_id"))
            prev_id = _to_int(prev.get("capture_id")) if prev else -1
            if prev is None or cur_id >= prev_id:
                latest_by_symbol[symbol] = dict(row)

    out: list[dict[str, Any]] = []
    for symbol, row in latest_by_symbol.items():
        rec = {
            "bid": row.get("bid"),
            "ask": row.get("ask"),
            "last": row.get("last"),
            "iv": row.get("iv"),
            "delta": row.get("delta"),
            "underlying_price": row.get("underlying_price"),
            "volume": row.get("volume"),
            "open_interest": row.get("open_interest"),
            "industry": row.get("industry"),
            "market_cap_mln": row.get("market_cap_mln"),
            "last_vs_ema20": row.get("last_vs_ema20"),
            "last_vs_ema50": row.get("last_vs_ema50"),
            "has_options": row.get("has_options"),
            "dividend_next_date": row.get("dividend_next_date"),
        }
        market_row = _market_row_from_record(symbol, regime, rec)
        if market_row is not None:
            out.append(market_row)

    return out


def _load_market_rows_ibkr_only(symbols: list[str], regime: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    snap = ROUTER.get_universe_snapshot(UniverseSnapshotRequest(symbols=symbols, regime=regime))
    rows = list(snap.get("rows") or [])
    diag = {
        "ibkr_only": False,
        "requested_symbols": len(symbols),
        "source": "provider_router",
        "policy_version": snap.get("policy_version"),
        "primary_count": snap.get("primary_count"),
        "fallback_count": snap.get("fallback_count"),
    }
    return rows, diag


def _passes_ibkr_filters(row: dict[str, Any], filters: dict[str, str]) -> bool:
    for key, raw in filters.items():
        val = str(raw).strip()
        if not val:
            continue

        if key == "priceAbove":
            x = _to_float(val)
            if x is not None and float(row.get("price", 0.0)) <= x:
                return False
        elif key == "priceBelow":
            x = _to_float(val)
            if x is not None and float(row.get("price", 0.0)) >= x:
                return False
        elif key in {"volumeAbove", "avgVolumeAbove"}:
            x = _to_float(val)
            if x is not None and float(row.get("volume", 0.0)) <= x:
                return False
        elif key == "marketCapAbove1e6":
            x = _to_float(val)
            if x is not None and float(row.get("market_cap_mln", 0.0)) <= x:
                return False
        elif key == "lastVsEMAChangeRatio20Above":
            x = _to_float(val)
            if x is not None and float(row.get("last_vs_ema20", 0.0)) <= x:
                return False
        elif key == "lastVsEMAChangeRatio50Above":
            x = _to_float(val)
            if x is not None and float(row.get("last_vs_ema50", 0.0)) <= x:
                return False
        elif key == "hasOptionsIs":
            want = val.lower() in {"true", "1", "yes"}
            if bool(row.get("has_options", False)) != want:
                return False
        elif key == "industryLike":
            tokens = [t.strip().lower() for t in val.split("|") if t.strip()]
            if tokens:
                ind = str(row.get("industry") or "").lower()
                if not any(tok in ind for tok in tokens):
                    return False
        elif key == "dividendNextDateAbove":
            cut = _parse_mm_yyyy(val)
            cur = _parse_mm_yyyy(str(row.get("dividend_next_date") or ""))
            if cut is not None and cur is not None and cur <= cut:
                return False

    return True


def init_universe_schema() -> None:
    init_execution_schema()
    con = _connect()
    backend = type(con).__module__.split(".")[0]
    if backend == "duckdb":
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS universe_scan_batches (
                batch_id VARCHAR PRIMARY KEY,
                profile VARCHAR,
                regime VARCHAR,
                source VARCHAR,
                scanner_name VARCHAR,
                ibkr_settings_path VARCHAR,
                ibkr_settings_exists BOOLEAN,
                symbols_json VARCHAR,
                top_n INTEGER,
                market_rows_available INTEGER,
                filter_fallback BOOLEAN,
                created_at TIMESTAMP
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS universe_scan_items (
                item_id VARCHAR PRIMARY KEY,
                batch_id VARCHAR,
                rank INTEGER,
                symbol VARCHAR,
                strategy VARCHAR,
                score DOUBLE,
                iv_rank DOUBLE,
                spread_pct DOUBLE,
                volume INTEGER,
                open_interest INTEGER,
                regime_fit DOUBLE,
                liquidity_score DOUBLE,
                created_at TIMESTAMP
            )
            """
        )
        try:
            con.execute("ALTER TABLE universe_scan_batches ADD COLUMN IF NOT EXISTS source VARCHAR")
            con.execute("ALTER TABLE universe_scan_batches ADD COLUMN IF NOT EXISTS scanner_name VARCHAR")
            con.execute("ALTER TABLE universe_scan_batches ADD COLUMN IF NOT EXISTS ibkr_settings_path VARCHAR")
            con.execute("ALTER TABLE universe_scan_batches ADD COLUMN IF NOT EXISTS ibkr_settings_exists BOOLEAN")
            con.execute("ALTER TABLE universe_scan_batches ADD COLUMN IF NOT EXISTS market_rows_available INTEGER")
            con.execute("ALTER TABLE universe_scan_batches ADD COLUMN IF NOT EXISTS filter_fallback BOOLEAN")
            con.execute("ALTER TABLE universe_scan_items ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'PENDING'")
            con.execute("ALTER TABLE universe_scan_items ADD COLUMN IF NOT EXISTS trade_id VARCHAR")
        except Exception:
            pass
        con.close()
        return

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS universe_scan_batches (
            batch_id TEXT PRIMARY KEY,
            profile TEXT,
            regime TEXT,
            source TEXT,
            scanner_name TEXT,
            ibkr_settings_path TEXT,
            ibkr_settings_exists INTEGER,
            symbols_json TEXT,
            top_n INTEGER,
            market_rows_available INTEGER,
            filter_fallback INTEGER,
            created_at TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS universe_scan_items (
            item_id TEXT PRIMARY KEY,
            batch_id TEXT,
            rank INTEGER,
            symbol TEXT,
            strategy TEXT,
            score REAL,
            iv_rank REAL,
            spread_pct REAL,
            volume INTEGER,
            open_interest INTEGER,
            regime_fit REAL,
            liquidity_score REAL,
            created_at TEXT
        )
        """
    )
    try:
        con.execute("ALTER TABLE universe_scan_batches ADD COLUMN IF NOT EXISTS source TEXT")
        con.execute("ALTER TABLE universe_scan_batches ADD COLUMN IF NOT EXISTS scanner_name TEXT")
        con.execute("ALTER TABLE universe_scan_batches ADD COLUMN IF NOT EXISTS ibkr_settings_path TEXT")
        con.execute("ALTER TABLE universe_scan_batches ADD COLUMN IF NOT EXISTS ibkr_settings_exists INTEGER")
        con.execute("ALTER TABLE universe_scan_batches ADD COLUMN IF NOT EXISTS market_rows_available INTEGER")
        con.execute("ALTER TABLE universe_scan_batches ADD COLUMN IF NOT EXISTS filter_fallback INTEGER")
        con.execute("ALTER TABLE universe_scan_items ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'PENDING'")
        con.execute("ALTER TABLE universe_scan_items ADD COLUMN IF NOT EXISTS trade_id TEXT")
    except Exception:
        pass

    if hasattr(con, "commit"):
        con.commit()
    con.close()


def run_universe_scan(
    *,
    profile: str = "paper",
    symbols: list[str] | None = None,
    regime: str = "NORMAL",
    top_n: int = 8,
    ibkr_filters: dict[str, str] | None = None,
    source: str = "manual",
    scanner_name: str | None = None,
    ibkr_settings_path: str | None = None,
    ibkr_settings_exists: bool = False,
) -> dict[str, Any]:
    init_universe_schema()
    requested_symbols = _norm_symbol_list(symbols)
    r = regime.strip().upper() or "NORMAL"
    if r not in {"NORMAL", "CAUTION", "SHOCK"}:
        r = "NORMAL"

    rows_all, source_diag = _load_market_rows_ibkr_only(requested_symbols, r)
    if not rows_all:
        raise UniverseDataUnavailableError(
            {
                "code": "NO_IBKR_MARKET_ROWS",
                "message": "Nessun dato IBKR valido disponibile per Universe scan.",
                "details": source_diag,
            }
        )
    rows = []
    for r0 in rows_all:
        row = dict(r0)
        row.setdefault("price", row.get("last"))
        row.setdefault("strategy", _pick_strategy(float(row.get("iv_rank") or 0.0), r))
        row.setdefault("score", float(row.get("score") or 0.0))
        row.setdefault("iv_rank", float(row.get("iv_rank") or 0.0))
        row.setdefault("spread_pct", float(row.get("spread_pct") or 1.0))
        row.setdefault("volume", int(row.get("volume") or 0))
        row.setdefault("open_interest", int(row.get("open_interest") or 0))
        row.setdefault("regime_fit", float(row.get("regime_fit") or 0.0))
        row.setdefault("liquidity_score", float(row.get("liquidity_score") or 0.0))
        rows.append(row)

    filter_fallback = False
    filters_used = ibkr_filters or {}
    if filters_used and rows:
        filtered = [row for row in rows if _passes_ibkr_filters(row, filters_used)]
        if filtered:
            rows = filtered
        else:
            filter_fallback = True

    rows.sort(key=lambda x: float(x["score"]), reverse=True)
    n = max(0, min(int(top_n), len(rows)))
    top = rows[:n]

    items: list[UniverseItem] = []
    for idx, row in enumerate(top, start=1):
        items.append(
            UniverseItem(
                rank=idx,
                symbol=str(row["symbol"]),
                strategy=str(row["strategy"]),
                score=round(float(row["score"]), 6),
                iv_rank=round(float(row["iv_rank"]), 6),
                spread_pct=round(float(row["spread_pct"]), 6),
                volume=int(row["volume"]),
                open_interest=int(row["open_interest"]),
                regime_fit=round(float(row["regime_fit"]), 6),
                liquidity_score=round(float(row["liquidity_score"]), 6),
            )
        )

    universe_symbols = requested_symbols
    if not universe_symbols:
        universe_symbols = sorted({str(x.get("symbol", "")).upper() for x in rows_all if x.get("symbol")})

    batch_id = str(uuid.uuid4())
    ts = _utcnow()
    con = _connect()
    con.execute(
        """
        INSERT INTO universe_scan_batches
        (batch_id, profile, regime, source, scanner_name, ibkr_settings_path, ibkr_settings_exists, symbols_json, top_n, market_rows_available, filter_fallback, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            profile,
            r,
            source,
            (scanner_name or ""),
            (ibkr_settings_path or ""),
            bool(ibkr_settings_exists),
            json.dumps(universe_symbols, ensure_ascii=False),
            len(items),
            len(rows_all),
            bool(filter_fallback),
            ts,
        ),
    )
    for it in items:
        con.execute(
            """
            INSERT INTO universe_scan_items
            (item_id, batch_id, rank, symbol, strategy, score, iv_rank, spread_pct, volume, open_interest, regime_fit, liquidity_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                batch_id,
                it.rank,
                it.symbol,
                it.strategy,
                it.score,
                it.iv_rank,
                it.spread_pct,
                it.volume,
                it.open_interest,
                it.regime_fit,
                it.liquidity_score,
                ts,
            ),
        )
    if hasattr(con, "commit"):
        con.commit()
    con.close()

    return {
        "batch_id": batch_id,
        "profile": profile,
        "regime": r,
        "top_n": len(items),
        "universe_size": len(universe_symbols),
        "created_at_utc": ts.isoformat().replace("+00:00", "Z"),
        "source": source,
        "scanner_name": (scanner_name or ""),
        "ibkr_settings_path": (ibkr_settings_path or ""),
        "ibkr_settings_exists": bool(ibkr_settings_exists),
        "filters_applied": filters_used,
        "filter_fallback": filter_fallback,
        "market_rows_available": len(rows_all),
        "items": [it.as_dict() for it in items],
    }


def run_universe_scan_from_ibkr_settings(
    *,
    profile: str = "paper",
    regime: str = "NORMAL",
    top_n: int = 8,
    scanner_name: str | None = None,
    settings_path: str | None = None,
) -> dict[str, Any]:
    ctx = extract_ibkr_universe_context(settings_path=settings_path)
    scanner = pick_ibkr_scanner(ctx.get("scanners", []), scanner_name=scanner_name)
    scanner_name_persisted = ""
    if isinstance(scanner, dict):
        scanner_name_persisted = str(scanner.get("scanner_name") or "").strip()
    # Explicit scanner_name from caller takes priority — operator intent over XML label
    if scanner_name:
        scanner_name_persisted = str(scanner_name).strip()
    elif not scanner_name_persisted:
        scanner_name_persisted = ""

    symbols_raw = ctx.get("symbols")
    symbols = [str(x) for x in symbols_raw] if isinstance(symbols_raw, list) else None
    filters = scanner.get("filters", {}) if scanner else {}

    out = run_universe_scan(
        profile=profile,
        symbols=symbols,
        regime=regime,
        top_n=top_n,
        ibkr_filters=filters,
        source="ibkr_settings",
        scanner_name=scanner_name_persisted,
        ibkr_settings_path=str(ctx.get("settings_path") or ""),
        ibkr_settings_exists=bool(ctx.get("settings_exists")),
    )
    out["ibkr_settings_path"] = ctx.get("settings_path")
    out["ibkr_settings_exists"] = bool(ctx.get("settings_exists"))
    out["ibkr_scanner"] = scanner
    out["ibkr_quote_symbol_count"] = int(ctx.get("quote_symbol_count", 0))
    return out


def fetch_latest_universe_batch() -> dict[str, Any]:
    init_universe_schema()
    con = _connect()
    row = con.execute(
        """
        SELECT batch_id, profile, regime, source, scanner_name, ibkr_settings_path, ibkr_settings_exists, symbols_json, top_n, market_rows_available, filter_fallback, created_at
        FROM universe_scan_batches
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        con.close()
        return {
            "has_data": False,
            "batch_id": None,
            "profile": None,
            "regime": None,
            "top_n": 0,
            "universe_size": 0,
            "created_at_utc": "",
            "source": None,
            "items": [],
        }

    batch_id, profile, regime, source, scanner_name, ibkr_settings_path, ibkr_settings_exists, symbols_json, top_n, market_rows_available, filter_fallback, created_at = row
    item_rows = con.execute(
        """
        SELECT rank, symbol, strategy, score, iv_rank, spread_pct, volume, open_interest, regime_fit, liquidity_score
        FROM universe_scan_items
        WHERE batch_id = ?
        ORDER BY rank ASC
        """,
        (batch_id,),
    ).fetchall()
    con.close()

    symbols: list[str]
    try:
        parsed = json.loads(symbols_json or "[]")
        symbols = [str(x) for x in parsed] if isinstance(parsed, list) else []
    except Exception:
        symbols = []

    items = [
        {
            "rank": int(r[0]),
            "symbol": str(r[1]),
            "strategy": str(r[2]),
            "score": float(r[3]),
            "iv_rank": float(r[4]),
            "spread_pct": float(r[5]),
            "volume": int(r[6]),
            "open_interest": int(r[7]),
            "regime_fit": float(r[8]),
            "liquidity_score": float(r[9]),
        }
        for r in item_rows
    ]

    created_iso = ""
    if isinstance(created_at, datetime):
        created_iso = created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    elif created_at is not None:
        created_iso = str(created_at)

    return {
        "has_data": True,
        "batch_id": str(batch_id),
        "profile": str(profile),
        "regime": str(regime),
        "top_n": int(top_n),
        "universe_size": len(symbols),
        "created_at_utc": created_iso,
        "source": str(source or "db"),
        "scanner_name": str(scanner_name or ""),
        "ibkr_settings_path": str(ibkr_settings_path or ""),
        "ibkr_settings_exists": bool(ibkr_settings_exists),
        "market_rows_available": int(market_rows_available or 0),
        "filter_fallback": bool(filter_fallback),
        "items": items,
    }









def _parse_ocr_num(token: str) -> float | None:
    s = str(token or "").strip()
    if not s:
        return None
    pct = s.endswith("%")
    s = s.replace("%", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        v = float(s)
    except Exception:
        return None
    if pct:
        return v / 100.0
    return v


def _extract_ocr_fields(raw_line: str) -> dict[str, Any]:
    toks = re.findall(r"[-+]?\d+(?:[\.,]\d+)?%?", str(raw_line or ""))
    vals = [_parse_ocr_num(t) for t in toks]
    vals = [v for v in vals if v is not None]
    pct_toks = [t for t in toks if t.endswith("%")]
    pct_vals = [_parse_ocr_num(t) for t in pct_toks]
    pct_vals = [v for v in pct_vals if v is not None]

    last = None
    for t in toks:
        if t.endswith("%"):
            continue
        v = _parse_ocr_num(t)
        if v is None:
            continue
        if 0 < v < 100000:
            last = v
            break

    vs_pct = pct_vals[0] if len(pct_vals) >= 1 else None
    vi_pct = pct_vals[1] if len(pct_vals) >= 2 else None

    return {
        "last": last,
        "bid": None,
        "ask": None,
        "vs_pct": vs_pct,
        "vi_pct": vi_pct,
        "delta": None,
    }


def _ocr_tab_to_ui_tab(tab: str) -> str:
    t = str(tab or "").strip().lower()
    if t in {"titoli", "indici", "opzioni", "palinsesto"}:
        return t
    if t in {"ciclo", "ciclo_economico", "cicloeconomico"}:
        return "ciclo"
    if t in {"watchlist"}:
        return "palinsesto"
    return "palinsesto"


def _load_ocr_compare_rows(*, ocr_path: str | None, allowed_symbols: set[str]) -> dict[str, dict[str, Any]]:
    p = Path(ocr_path) if ocr_path else (ROOT / "data" / "ibkr_screens" / "tesseract_extraction.json")
    if not p.exists():
        return {}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}

    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        symbol = str(r.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        if allowed_symbols and symbol not in allowed_symbols:
            continue
        tab = _ocr_tab_to_ui_tab(str(r.get("tab") or ""))
        key = f"{tab}:{symbol}"
        line = str(r.get("raw_line") or "")
        fields = _extract_ocr_fields(line)
        prev = out.get(key, {"tab": tab, "symbol": symbol, "last": None, "bid": None, "ask": None, "vs_pct": None, "vi_pct": None, "delta": None, "raw_lines": []})
        for f in ("last", "bid", "ask", "vs_pct", "vi_pct", "delta"):
            if prev.get(f) is None and fields.get(f) is not None:
                prev[f] = fields[f]
        prev["raw_lines"].append(line)
        out[key] = prev
    return out


def _api_rows_map(*, symbols: list[str], regime: str) -> dict[str, dict[str, Any]]:
    rows = _load_from_pipeline_duckdb(symbols, regime)
    out: dict[str, dict[str, Any]] = {}

    index_set = {"SPY", "QQQ", "IWM", "TLT", "DBC", "DAX", "SHY", "EUR.USD", "EUR.GBP"}
    cycle_set = {"SPY", "IWN", "QQQ", "TLT", "DBC", "XLY", "XLK", "XLC", "XLI", "XLB", "XLP", "XLE", "XLV", "XLU", "XLF", "XLRE"}

    for r in rows:
        sym = str(r.get("symbol") or "").upper().strip()
        if not sym:
            continue
        if sym in index_set:
            tab = "indici"
        elif sym in cycle_set:
            tab = "ciclo"
        else:
            tab = "palinsesto"
        out[f"{tab}:{sym}"] = {
            "tab": tab,
            "symbol": sym,
            "last": _to_float(r.get("price")),
            "bid": None,
            "ask": None,
            "vs_pct": None,
            "vi_pct": _to_float(r.get("iv_rank")),
            "delta": None,
        }
    return out


def _mismatch(a: float | None, b: float | None, *, rel_tol: float, abs_tol: float) -> bool:
    if a is None or b is None:
        return False
    diff = abs(a - b)
    if diff <= abs_tol:
        return False
    base = max(abs(a), abs(b), 1e-9)
    return (diff / base) > rel_tol


def _load_batch_meta(batch_id: str | None) -> dict[str, Any]:
    if not batch_id:
        return {}
    init_universe_schema()
    con = _connect()
    row = con.execute(
        """
        SELECT symbols_json, source, scanner_name, ibkr_settings_path, ibkr_settings_exists
        FROM universe_scan_batches
        WHERE batch_id = ?
        LIMIT 1
        """,
        (batch_id,),
    ).fetchone()
    con.close()
    if row is None:
        return {}
    try:
        parsed = json.loads(row[0] or "[]")
        symbols = [str(x).strip().upper() for x in parsed] if isinstance(parsed, list) else []
    except Exception:
        symbols = []
    return {
        "symbols": [s for s in symbols if s],
        "source": str(row[1] or ""),
        "scanner_name": str(row[2] or ""),
        "ibkr_settings_path": str(row[3] or ""),
        "ibkr_settings_exists": bool(row[4]),
    }


def _load_batch_symbols(batch_id: str | None) -> list[str]:
    return list(_load_batch_meta(batch_id).get("symbols") or [])


def build_universe_compare(*, settings_path: str | None = None, ocr_path: str | None = None, regime: str = "NORMAL", batch_id: str | None = None) -> dict[str, Any]:
    batch_meta = _load_batch_meta(batch_id)
    effective_settings_path = settings_path
    if batch_id:
        persisted = str(batch_meta.get("ibkr_settings_path") or "").strip()
        if persisted:
            effective_settings_path = persisted
    ctx = extract_ibkr_universe_context(settings_path=effective_settings_path)
    symbols = list(batch_meta.get("symbols") or [])
    symbol_scope = "batch" if symbols else "settings"
    if not symbols:
        symbols_raw = ctx.get("symbols")
        symbols = [str(x).strip().upper() for x in symbols_raw] if isinstance(symbols_raw, list) else []
        symbols = [s for s in symbols if s]

    snap = ROUTER.get_universe_snapshot(UniverseSnapshotRequest(symbols=symbols, regime=regime))
    rows_raw = list(snap.get("rows") or [])

    index_set = {"SPY", "QQQ", "IWM", "TLT", "DBC", "DAX", "SHY", "EUR.USD", "EUR.GBP"}
    cycle_set = {"SPY", "IWN", "QQQ", "TLT", "DBC", "XLY", "XLK", "XLC", "XLI", "XLB", "XLP", "XLE", "XLV", "XLU", "XLF", "XLRE"}

    rows: list[dict[str, Any]] = []
    for r in rows_raw:
        sym = str(r.get("symbol") or "").strip().upper()
        if not sym:
            continue
        if sym in index_set:
            tab = "indici"
        elif sym in cycle_set:
            tab = "ciclo"
        else:
            tab = "palinsesto"

        rows.append(
            {
                "tab": tab,
                "symbol": sym,
                "last": _to_float(r.get("last")),
                "bid": _to_float(r.get("bid")),
                "ask": _to_float(r.get("ask")),
                "vs_pct": None,
                "vi_pct": _to_float(r.get("iv_rank") if r.get("iv_rank") is not None else r.get("iv")),
                "delta": _to_float(r.get("delta")),
                "source": str(r.get("source") or "none"),
                "field_sources": dict(r.get("field_sources") or {}),
                "mismatch_fields": list(r.get("conflict_flags") or []),
                "freshness_s": r.get("freshness_s"),
            }
        )

    return {
        "generated_at_utc": _utcnow().isoformat().replace("+00:00", "Z"),
        "batch_id": batch_id,
        "symbol_scope": symbol_scope,
        "settings_path": str(batch_meta.get("ibkr_settings_path") or ctx.get("settings_path") or ""),
        "settings_exists": bool(batch_meta.get("ibkr_settings_exists") if batch_id else ctx.get("settings_exists")),
        "symbols_count": len(symbols),
        "api_rows": int(snap.get("primary_count") or 0),
        "ocr_rows": 0,
        "fallback_rows": int(snap.get("fallback_count") or 0),
        "policy_version": snap.get("policy_version"),
        "ocr_ignored": bool(ocr_path),
        "rows": rows,
    }


def update_scan_item_status(
    item_id: str,
    status: str,
    trade_id: str | None = None,
) -> None:
    """Update human-layer status of a scan item: PENDING | EXECUTED | EXPIRED."""
    init_universe_schema()
    con = _connect()
    if trade_id is not None:
        con.execute(
            "UPDATE universe_scan_items SET status = ?, trade_id = ? WHERE item_id = ?",
            (status, trade_id, item_id),
        )
    else:
        con.execute(
            "UPDATE universe_scan_items SET status = ? WHERE item_id = ?",
            (status, item_id),
        )
    if hasattr(con, "commit"):
        con.commit()
    con.close()


def expire_pending_scan_items(profile: str, before_ts: str) -> int:
    """Mark all PENDING items from batches older than before_ts as EXPIRED.
    Called by EOD session. Returns count of expired items."""
    init_universe_schema()
    con = _connect()
    result = con.execute(
        """
        UPDATE universe_scan_items
        SET status = 'EXPIRED'
        WHERE status = 'PENDING'
          AND batch_id IN (
              SELECT batch_id FROM universe_scan_batches
              WHERE profile = ? AND created_at < ?
          )
        """,
        (profile, before_ts),
    )
    count = result.rowcount if hasattr(result, "rowcount") else 0
    if hasattr(con, "commit"):
        con.commit()
    con.close()
    return count or 0


def query_backtest_applied(
    profile: str,
    from_ts: str,
    to_ts: str,
) -> list[dict]:
    """Backtest 'a trading applicato': all scan items in period with execution outcome."""
    init_universe_schema()
    con = _connect()
    rows = con.execute(
        """
        SELECT
            si.item_id, si.batch_id, si.rank, si.symbol, si.strategy,
            si.score, si.status, si.trade_id,
            sb.created_at AS batch_ts, sb.regime,
            pt.pnl, pt.pnl_pct, pt.exit_reason, pt.trigger AS trade_trigger
        FROM universe_scan_items si
        JOIN universe_scan_batches sb ON si.batch_id = sb.batch_id
        LEFT JOIN paper_trades pt ON si.trade_id = pt.trade_id
        WHERE sb.profile = ?
          AND sb.created_at >= ?
          AND sb.created_at <= ?
        ORDER BY sb.created_at ASC, si.rank ASC
        """,
        (profile, from_ts, to_ts),
    ).fetchall()
    con.close()
    keys = ["item_id", "batch_id", "rank", "symbol", "strategy", "score",
            "status", "trade_id", "batch_ts", "regime", "pnl", "pnl_pct",
            "exit_reason", "trade_trigger"]
    return [dict(zip(keys, r)) for r in rows]


