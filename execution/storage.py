from __future__ import annotations

import importlib
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from .state_machine import normalize_state

EXEC_DB_PATH = Path("db/execution.duckdb")
_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()
_SOURCE_SYSTEM = "qopz_ai"


def _prov(profile: str, asof_ts: Any) -> tuple[str, str, str, Any, str]:
    """Return (source_system, source_mode, source_quality, asof_ts, received_ts) provenance tuple.

    All DB inserts must include these five fields per project invariant.
    """
    source_mode = os.environ.get("OPZ_DATA_MODE", "SYNTHETIC_SURFACE_CALIBRATED")
    received_ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    asof_s = asof_ts.isoformat().replace("+00:00", "Z") if hasattr(asof_ts, "isoformat") else str(asof_ts)
    return (_SOURCE_SYSTEM, source_mode, profile, asof_s, received_ts)


def _duckdb():
    """Return duckdb module or raise if unavailable (DuckDB-only project policy)."""
    try:
        return importlib.import_module("duckdb")
    except ModuleNotFoundError as exc:
        raise RuntimeError("duckdb is required by project policy") from exc


def _connect():
    """Return a DuckDB connection (DuckDB-only)."""
    EXEC_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    duckdb = _duckdb()
    return duckdb.connect(str(EXEC_DB_PATH))


def init_execution_schema() -> None:
    global _SCHEMA_READY
    with _SCHEMA_LOCK:
        if _SCHEMA_READY and EXEC_DB_PATH.exists():
            return
        try:
            con = _connect()
        except Exception as exc:
            logger.warning("init_execution_schema: cannot open DB (%s) — will retry on next call", exc)
            return  # _SCHEMA_READY stays False → next caller retries

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                client_order_id VARCHAR PRIMARY KEY,
                run_id VARCHAR,
                profile VARCHAR,
                symbol VARCHAR,
                side VARCHAR,
                quantity INTEGER,
                limit_price DOUBLE,
                fill_price DOUBLE,
                slippage DOUBLE,
                outcome VARCHAR,
                status VARCHAR,
                state VARCHAR,
                timestamp TIMESTAMP,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                source_system VARCHAR,
                source_mode VARCHAR,
                source_quality VARCHAR,
                asof_ts VARCHAR,
                received_ts VARCHAR
            )
            """
        )

        try:
            con.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS outcome VARCHAR")
        except Exception as _exc:  # column already exists — safe to ignore
            logger.debug("ALTER TABLE skip: %s", _exc)
        for _col in ("source_system VARCHAR", "source_mode VARCHAR", "source_quality VARCHAR", "asof_ts VARCHAR", "received_ts VARCHAR"):
            try:
                con.execute(f"ALTER TABLE orders ADD COLUMN IF NOT EXISTS {_col}")
            except Exception as _exc:  # column already exists — safe to ignore
                logger.debug("ALTER TABLE skip: %s", _exc)

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS order_events (
                event_id VARCHAR PRIMARY KEY,
                client_order_id VARCHAR,
                run_id VARCHAR,
                profile VARCHAR,
                event_type VARCHAR,
                prev_state VARCHAR,
                new_state VARCHAR,
                ts_utc TIMESTAMP,
                details_json VARCHAR,
                source_system VARCHAR,
                source_mode VARCHAR,
                source_quality VARCHAR,
                asof_ts VARCHAR,
                received_ts VARCHAR
            )
            """
        )
        for _col in ("source_system VARCHAR", "source_mode VARCHAR", "source_quality VARCHAR", "asof_ts VARCHAR", "received_ts VARCHAR"):
            try:
                con.execute(f"ALTER TABLE order_events ADD COLUMN IF NOT EXISTS {_col}")
            except Exception as _exc:  # column already exists — safe to ignore
                logger.debug("ALTER TABLE skip: %s", _exc)

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_equity_snapshots (
                snapshot_id VARCHAR PRIMARY KEY,
                profile VARCHAR,
                asof_date DATE,
                equity DOUBLE,
                note VARCHAR,
                trigger VARCHAR DEFAULT 'manual',
                created_at TIMESTAMP,
                source_system VARCHAR,
                source_mode VARCHAR,
                source_quality VARCHAR,
                asof_ts VARCHAR,
                received_ts VARCHAR
            )
            """
        )
        try:
            con.execute("ALTER TABLE paper_equity_snapshots ADD COLUMN IF NOT EXISTS trigger VARCHAR DEFAULT 'manual'")
        except Exception as _exc:
            logger.debug("ALTER TABLE skip: %s", _exc)
        for _col in ("source_system VARCHAR", "source_mode VARCHAR", "source_quality VARCHAR", "asof_ts VARCHAR", "received_ts VARCHAR"):
            try:
                con.execute(f"ALTER TABLE paper_equity_snapshots ADD COLUMN IF NOT EXISTS {_col}")
            except Exception as _exc:  # column already exists — safe to ignore
                logger.debug("ALTER TABLE skip: %s", _exc)

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_trades (
                trade_id VARCHAR PRIMARY KEY,
                profile VARCHAR,
                symbol VARCHAR,
                strategy VARCHAR,
                entry_ts_utc TIMESTAMP,
                exit_ts_utc TIMESTAMP,
                strikes_json VARCHAR,
                regime_at_entry VARCHAR,
                score_at_entry DOUBLE,
                kelly_fraction DOUBLE,
                exit_reason VARCHAR,
                pnl DOUBLE,
                pnl_pct DOUBLE,
                slippage_ticks DOUBLE,
                violations INTEGER,
                note VARCHAR,
                trigger VARCHAR DEFAULT 'manual',
                created_at TIMESTAMP,
                source_system VARCHAR,
                source_mode VARCHAR,
                source_quality VARCHAR,
                asof_ts VARCHAR,
                received_ts VARCHAR
            )
            """
        )
        try:
            con.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS strikes_json VARCHAR")
            con.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS regime_at_entry VARCHAR")
            con.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS score_at_entry DOUBLE")
            con.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS kelly_fraction DOUBLE")
            con.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS exit_reason VARCHAR")
            con.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS trigger VARCHAR DEFAULT 'manual'")
        except Exception as _exc:  # column already exists — safe to ignore
            logger.debug("ALTER TABLE skip: %s", _exc)
        for _col in ("source_system VARCHAR", "source_mode VARCHAR", "source_quality VARCHAR", "asof_ts VARCHAR", "received_ts VARCHAR"):
            try:
                con.execute(f"ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS {_col}")
            except Exception as _exc:  # column already exists — safe to ignore
                logger.debug("ALTER TABLE skip: %s", _exc)

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS compliance_events (
                event_id VARCHAR PRIMARY KEY,
                profile VARCHAR,
                ts_utc TIMESTAMP,
                code VARCHAR,
                severity VARCHAR,
                details_json VARCHAR,
                source_system VARCHAR,
                source_mode VARCHAR,
                source_quality VARCHAR,
                asof_ts VARCHAR,
                received_ts VARCHAR
            )
            """
        )
        for _col in ("source_system VARCHAR", "source_mode VARCHAR", "source_quality VARCHAR", "asof_ts VARCHAR", "received_ts VARCHAR"):
            try:
                con.execute(f"ALTER TABLE compliance_events ADD COLUMN IF NOT EXISTS {_col}")
            except Exception as _exc:  # column already exists — safe to ignore
                logger.debug("ALTER TABLE skip: %s", _exc)

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS operator_opportunity_decisions (
                decision_id VARCHAR PRIMARY KEY,
                profile VARCHAR,
                batch_id VARCHAR,
                symbol VARCHAR,
                strategy VARCHAR,
                score DOUBLE,
                regime VARCHAR,
                scanner_name VARCHAR,
                source VARCHAR,
                decision VARCHAR,
                confidence INTEGER,
                note VARCHAR,
                created_at TIMESTAMP,
                source_system VARCHAR,
                source_mode VARCHAR,
                source_quality VARCHAR,
                asof_ts VARCHAR,
                received_ts VARCHAR
            )
            """
        )
        for _col in ("source_system VARCHAR", "source_mode VARCHAR", "source_quality VARCHAR", "asof_ts VARCHAR", "received_ts VARCHAR"):
            try:
                con.execute(f"ALTER TABLE operator_opportunity_decisions ADD COLUMN IF NOT EXISTS {_col}")
            except Exception as _exc:  # column already exists — safe to ignore
                logger.debug("ALTER TABLE skip: %s", _exc)

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS opportunity_candidates (
                candidate_id  VARCHAR PRIMARY KEY,
                batch_id      VARCHAR NOT NULL,
                profile       VARCHAR,
                scan_ts       TIMESTAMP,
                regime        VARCHAR,
                data_mode     VARCHAR,
                symbol        VARCHAR,
                strategy      VARCHAR,
                score         DOUBLE,
                score_breakdown_json VARCHAR,
                expiry        VARCHAR,
                dte           INTEGER,
                strikes_json  VARCHAR,
                delta         DOUBLE,
                iv            DOUBLE,
                iv_zscore_30  DOUBLE,
                iv_zscore_60  DOUBLE,
                iv_interp     VARCHAR,
                expected_move      DOUBLE,
                signal_vs_em_ratio DOUBLE,
                spread_pct    DOUBLE,
                open_interest INTEGER,
                volume        INTEGER,
                max_loss      DOUBLE,
                max_loss_pct  DOUBLE,
                breakeven     DOUBLE,
                breakeven_pct DOUBLE,
                credit_or_debit   DOUBLE,
                sizing_suggested  DOUBLE,
                kelly_fraction    DOUBLE,
                events_flag       VARCHAR,
                human_review_required BOOLEAN,
                stress_base   DOUBLE,
                stress_shock  DOUBLE,
                data_quality  VARCHAR,
                source        VARCHAR,
                underlying_price  DOUBLE,
                source_system VARCHAR,
                source_mode   VARCHAR,
                source_quality VARCHAR,
                asof_ts       VARCHAR,
                received_ts   VARCHAR
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS opportunity_chain_snapshots (
                snapshot_id   VARCHAR PRIMARY KEY,
                batch_id      VARCHAR NOT NULL,
                profile       VARCHAR,
                symbol        VARCHAR,
                scan_ts       TIMESTAMP,
                source_system VARCHAR,
                source_mode   VARCHAR,
                source_quality VARCHAR,
                asof_ts       VARCHAR,
                received_ts   VARCHAR
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS opportunity_ev_tracking (
                track_id      VARCHAR PRIMARY KEY,
                candidate_id  VARCHAR NOT NULL,
                batch_id      VARCHAR NOT NULL,
                profile       VARCHAR,
                symbol        VARCHAR,
                strategy      VARCHAR,
                expiry        VARCHAR,
                entry_score   DOUBLE,
                entry_credit  DOUBLE,
                entry_max_loss DOUBLE,
                status        VARCHAR,
                exit_ts       TIMESTAMP,
                exit_pnl      DOUBLE,
                exit_reason   VARCHAR,
                ev_realized   DOUBLE,
                source_system VARCHAR,
                source_mode   VARCHAR,
                source_quality VARCHAR,
                asof_ts       VARCHAR,
                received_ts   VARCHAR
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS session_logs (
                log_id        VARCHAR PRIMARY KEY,
                profile       VARCHAR,
                session_date  VARCHAR,
                session_type  VARCHAR,
                regime        VARCHAR,
                equity        DOUBLE,
                n_symbols     INTEGER,
                errors_json   VARCHAR,
                steps_json    VARCHAR,
                trigger       VARCHAR DEFAULT 'auto',
                started_at    VARCHAR,
                finished_at   VARCHAR,
                source_system VARCHAR,
                source_mode   VARCHAR,
                source_quality VARCHAR,
                asof_ts       VARCHAR,
                received_ts   VARCHAR
            )
            """
        )

        try:
            con.execute("ALTER TABLE session_logs ADD COLUMN IF NOT EXISTS steps_json VARCHAR")
        except Exception as _exc:
            logger.debug("ALTER TABLE skip: %s", _exc)

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS ingestion_runs (
                run_id        VARCHAR PRIMARY KEY,
                profile       VARCHAR,
                feed          VARCHAR,
                run_date      VARCHAR,
                started_at    VARCHAR,
                finished_at   VARCHAR,
                duration_ms   INTEGER,
                status        VARCHAR,
                records_in    INTEGER,
                records_out   INTEGER,
                quality_pct   DOUBLE,
                symbols_count INTEGER,
                error_msg     VARCHAR,
                details_json  VARCHAR,
                source_system VARCHAR,
                source_mode   VARCHAR,
                source_quality VARCHAR,
                asof_ts       VARCHAR,
                received_ts   VARCHAR
            )
            """
        )

        try:
            con.close()
        except Exception:
            pass
        _SCHEMA_READY = True


def save_opportunity_scan(
    *,
    batch_id: str,
    profile: str,
    scan_result: Any,
) -> None:
    """Persist ScanResult to opportunity_candidates + opportunity_chain_snapshots.

    scan_result must expose .regime, .data_mode, .scan_ts (str), .candidates (list[OpportunityCandidate]).
    Does NOT raise on individual row failures — logs and continues.
    """
    import dataclasses
    import json as _json

    init_execution_schema()
    con = _connect()
    now = utc_now()
    prov = _prov(profile, now)
    scan_ts_str = getattr(scan_result, "scan_ts", now.isoformat())

    try:
        seen_symbols: set[str] = set()

        for c in getattr(scan_result, "candidates", []):
            cid = str(uuid.uuid4())
            d: dict[str, Any] = (
                dataclasses.asdict(c)
                if dataclasses.is_dataclass(c) and not isinstance(c, type)
                else dict(c)
            )
            con.execute(
                """
                INSERT INTO opportunity_candidates (
                    candidate_id, batch_id, profile, scan_ts, regime, data_mode,
                    symbol, strategy, score, score_breakdown_json,
                    expiry, dte, strikes_json, delta, iv,
                    iv_zscore_30, iv_zscore_60, iv_interp,
                    expected_move, signal_vs_em_ratio,
                    spread_pct, open_interest, volume,
                    max_loss, max_loss_pct, breakeven, breakeven_pct,
                    credit_or_debit, sizing_suggested, kelly_fraction,
                    events_flag, human_review_required,
                    stress_base, stress_shock,
                    data_quality, source, underlying_price,
                    source_system, source_mode, source_quality, asof_ts, received_ts
                ) VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                (
                    cid, batch_id, profile, scan_ts_str,
                    getattr(scan_result, "regime", None),
                    getattr(scan_result, "data_mode", None),
                    d.get("symbol"), d.get("strategy"), d.get("score"),
                    _json.dumps(d.get("score_breakdown") or {}),
                    d.get("expiry"), d.get("dte"),
                    _json.dumps(d.get("strikes") or []),
                    d.get("delta"), d.get("iv"),
                    d.get("iv_zscore_30"), d.get("iv_zscore_60"), d.get("iv_interp"),
                    d.get("expected_move"), d.get("signal_vs_em_ratio"),
                    d.get("spread_pct"), d.get("open_interest"), d.get("volume"),
                    d.get("max_loss"), d.get("max_loss_pct"),
                    d.get("breakeven"), d.get("breakeven_pct"),
                    d.get("credit_or_debit"), d.get("sizing_suggested"), d.get("kelly_fraction"),
                    d.get("events_flag"), d.get("human_review_required"),
                    d.get("stress_base"), d.get("stress_shock"),
                    d.get("data_quality"), d.get("source"), d.get("underlying_price"),
                    *prov,
                ),
            )

            sym = d.get("symbol") or ""
            if sym and sym not in seen_symbols:
                seen_symbols.add(sym)
                con.execute(
                    """
                    INSERT INTO opportunity_chain_snapshots (
                        snapshot_id, batch_id, profile, symbol, scan_ts,
                        source_system, source_mode, source_quality, asof_ts, received_ts
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (str(uuid.uuid4()), batch_id, profile, sym, scan_ts_str, *prov),
                )

        if hasattr(con, "commit"):
            con.commit()
    finally:
        con.close()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def record_event(
    *,
    client_order_id: str,
    run_id: str,
    profile: str,
    event_type: str,
    prev_state: str | None,
    new_state: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    import json

    con = _connect()
    ts = utc_now()
    try:
        prov = _prov(profile, ts)
        con.execute(
            "INSERT INTO order_events (event_id, client_order_id, run_id, profile, event_type, prev_state, new_state, ts_utc, details_json, source_system, source_mode, source_quality, asof_ts, received_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                client_order_id,
                run_id,
                profile,
                event_type,
                prev_state,
                new_state,
                ts,
                None if details is None else json.dumps(details, ensure_ascii=False),
                *prov,
            ),
        )
        if hasattr(con, "commit"):
            con.commit()
    finally:
        con.close()

    # Best-effort JSONL event trail (runtime-only, gitignored via logs/)
    try:
        log_path = Path("logs") / "execution_events.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts_utc": ts.isoformat(),
            "client_order_id": client_order_id,
            "run_id": run_id,
            "profile": profile,
            "event_type": event_type,
            "prev_state": prev_state,
            "new_state": new_state,
            "details": details,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:  # best-effort JSONL trail — do not propagate I/O errors
        pass


def upsert_order(
    *,
    client_order_id: str,
    run_id: str,
    profile: str,
    symbol: str,
    side: str,
    quantity: int,
    state: str,
    limit_price: float | None = None,
    fill_price: float | None = None,
    slippage: float | None = None,
    outcome: str | None = None,
) -> None:
    state = normalize_state(state)
    con = _connect()
    try:
        now = utc_now()
        status = state
        prov = _prov(profile, now)
        con.execute(
            """
            INSERT INTO orders (client_order_id, run_id, profile, symbol, side, quantity, limit_price, fill_price, slippage, outcome, status, state, timestamp, created_at, updated_at, source_system, source_mode, source_quality, asof_ts, received_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (client_order_id) DO UPDATE SET
              run_id=excluded.run_id,
              profile=excluded.profile,
              symbol=excluded.symbol,
              side=excluded.side,
              quantity=excluded.quantity,
              limit_price=COALESCE(excluded.limit_price, orders.limit_price),
              fill_price=COALESCE(excluded.fill_price, orders.fill_price),
              slippage=COALESCE(excluded.slippage, orders.slippage),
              outcome=COALESCE(excluded.outcome, orders.outcome),
              status=excluded.status,
              state=excluded.state,
              timestamp=excluded.timestamp,
              updated_at=excluded.updated_at,
              source_mode=excluded.source_mode,
              received_ts=excluded.received_ts
            """,
            (
                client_order_id,
                run_id,
                profile,
                symbol,
                side,
                quantity,
                limit_price,
                fill_price,
                slippage,
                outcome,
                status,
                state,
                now,
                now,
                now,
                *prov,
            ),
        )
        if hasattr(con, "commit"):
            con.commit()
    finally:
        con.close()


def get_order_state(client_order_id: str) -> str | None:
    con = _connect()
    try:
        row = con.execute("SELECT state FROM orders WHERE client_order_id = ?", (client_order_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return None
    return row[0]


def order_exists(client_order_id: str) -> bool:
    return get_order_state(client_order_id) is not None


def record_ingestion_run(
    *,
    feed: str,
    profile: str,
    run_date: str,
    started_at: str,
    finished_at: str,
    duration_ms: int,
    status: str,
    records_in: int = 0,
    records_out: int = 0,
    symbols_count: int = 0,
    error_msg: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Record one ingestion run per feed.

    feed    — 'yfinance' | 'fred' | 'orats' | 'ibkr_demo' | 'ibwr' | any label
    status  — 'ok' | 'error' | 'partial'
    """
    import json as _json

    init_execution_schema()
    con = _connect()
    now = utc_now()
    prov = _prov(profile, now)
    quality = round(records_out / records_in * 100, 1) if records_in > 0 else None
    try:
        # Upsert: stesso giorno + stesso feed → aggiorna solo se qualità migliore
        existing = con.execute(
            "SELECT quality_pct, status FROM ingestion_runs "
            "WHERE profile=? AND feed=? AND run_date=? "
            "ORDER BY quality_pct DESC NULLS LAST LIMIT 1",
            (profile, feed, run_date),
        ).fetchone()
        if existing is not None:
            ex_quality, ex_status = existing
            new_q = quality if quality is not None else -1.0
            old_q = ex_quality if ex_quality is not None else -1.0
            # mantieni il record esistente solo se la nuova qualità è strettamente peggiore
            # e il vecchio non era un errore — a parità vince il più recente
            if new_q < old_q and ex_status != "error":
                return
            # qualità migliore (o vecchio era error): rimuovi i vecchi e inserisci il nuovo
            con.execute(
                "DELETE FROM ingestion_runs WHERE profile=? AND feed=? AND run_date=?",
                (profile, feed, run_date),
            )
        con.execute(
            """
            INSERT INTO ingestion_runs (
                run_id, profile, feed, run_date, started_at, finished_at,
                duration_ms, status, records_in, records_out, quality_pct,
                symbols_count, error_msg, details_json,
                source_system, source_mode, source_quality, asof_ts, received_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), profile, feed, run_date, started_at, finished_at,
                duration_ms, status, records_in, records_out, quality,
                symbols_count, error_msg,
                None if details is None else _json.dumps(details, ensure_ascii=False),
                *prov,
            ),
        )
        if hasattr(con, "commit"):
            con.commit()
    except Exception as exc:
        logger.warning("record_ingestion_run: failed to write (%s)", exc)
    finally:
        con.close()


def list_ingestion_runs(
    *,
    profile: str,
    days_back: int = 30,
    feed: str | None = None,
) -> list[dict[str, Any]]:
    """Return ingestion_runs rows ordered by started_at DESC."""
    init_execution_schema()
    con = _connect()
    try:
        where = "profile = ? AND CAST(run_date AS DATE) >= CURRENT_DATE - INTERVAL (?) DAY"
        params: list[Any] = [profile, days_back]
        if feed:
            where += " AND feed = ?"
            params.append(feed)
        rows = con.execute(
            f"""
            SELECT run_id, feed, run_date, started_at, finished_at,
                   duration_ms, status, records_in, records_out, quality_pct,
                   symbols_count, error_msg
            FROM ingestion_runs
            WHERE {where}
            ORDER BY started_at DESC
            """,
            params,
        ).fetchall()
        cols = ["run_id", "feed", "run_date", "started_at", "finished_at",
                "duration_ms", "status", "records_in", "records_out", "quality_pct",
                "symbols_count", "error_msg"]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        con.close()

