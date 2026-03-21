from __future__ import annotations

import json
import logging
import math
import os
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from scripts.metrics import annualized_sharpe, max_drawdown
from .storage import _connect, _prov, init_execution_schema


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class PaperSummary:
    profile: str
    window_days: int
    as_of_date: date
    equity_points: int
    trades: int
    sharpe_annualized: Optional[float]
    max_drawdown: Optional[float]
    win_rate: Optional[float]
    profit_factor: Optional[float]
    avg_slippage_ticks: Optional[float]
    compliance_violations: int
    gates: Dict[str, Any]


def init_paper_schema() -> None:
    init_execution_schema()


def _norm_ts_utc(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    return v if v else None


def _is_present_text(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def record_equity_snapshot(
    *,
    profile: str,
    asof_date: date,
    equity: float,
    note: str = "",
    trigger: str = "manual",
) -> str:
    init_execution_schema()
    con = _connect()
    sid = str(uuid.uuid4())
    backend = type(con).__module__.split(".")[0]
    created = _utc_now_iso()
    prov = _prov(profile, created)
    if backend == "duckdb":
        con.execute(
            "INSERT INTO paper_equity_snapshots (snapshot_id, profile, asof_date, equity, note, trigger, created_at, source_system, source_mode, source_quality, asof_ts, received_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, profile, asof_date.isoformat(), float(equity), note, trigger, created, *prov),
        )
        con.close()
        return sid

    con.execute(
        "INSERT INTO paper_equity_snapshots (snapshot_id, profile, asof_date, equity, note, trigger, created_at, source_system, source_mode, source_quality, asof_ts, received_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sid, profile, asof_date.isoformat(), float(equity), note, trigger, created, *prov),
    )
    if hasattr(con, "commit"):
        con.commit()
    con.close()
    return sid


def record_trade(
    *,
    profile: str,
    symbol: str,
    strategy: str,
    entry_ts_utc: Optional[datetime],
    exit_ts_utc: Optional[datetime],
    pnl: float,
    pnl_pct: Optional[float] = None,
    slippage_ticks: Optional[float] = None,
    violations: int = 0,
    note: str = "",
    strikes: Optional[list[Any]] = None,
    regime_at_entry: Optional[str] = None,
    score_at_entry: Optional[float] = None,
    kelly_fraction: Optional[float] = None,
    exit_reason: Optional[str] = None,
    trigger: str = "manual",
) -> str:
    init_execution_schema()
    con = _connect()
    tid = str(uuid.uuid4())
    created = _utc_now_iso()

    entry_s = _norm_ts_utc(entry_ts_utc)
    exit_s = _norm_ts_utc(exit_ts_utc)
    strikes_json = json.dumps(strikes, ensure_ascii=False) if strikes is not None else None
    prov = _prov(profile, entry_s or created)

    try:
        con.execute(
            """
            INSERT INTO paper_trades (
                trade_id, profile, symbol, strategy, entry_ts_utc, exit_ts_utc,
                strikes_json, regime_at_entry, score_at_entry, kelly_fraction, exit_reason,
                pnl, pnl_pct, slippage_ticks, violations, note, trigger, created_at,
                source_system, source_mode, source_quality, asof_ts, received_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tid,
                profile,
                symbol,
                strategy,
                entry_s,
                exit_s,
                strikes_json,
                _norm_optional_text(regime_at_entry),
                float(score_at_entry) if score_at_entry is not None else None,
                float(kelly_fraction) if kelly_fraction is not None else None,
                _norm_optional_text(exit_reason),
                float(pnl),
                float(pnl_pct) if pnl_pct is not None else None,
                float(slippage_ticks) if slippage_ticks is not None else None,
                int(violations),
                note,
                trigger,
                created,
                *prov,
            ),
        )
        if hasattr(con, "commit"):
            con.commit()
    finally:
        con.close()
    return tid


def record_compliance_event(
    *,
    profile: str,
    ts_utc: Optional[datetime],
    code: str,
    severity: str = "CRITICAL",
    details: Optional[Dict[str, Any]] = None,
) -> str:
    init_execution_schema()
    con = _connect()
    eid = str(uuid.uuid4())
    ts = (ts_utc or datetime.now(timezone.utc)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    details_json = json.dumps(details or {}, ensure_ascii=False) if details is not None else None
    prov = _prov(profile, ts)

    try:
        con.execute(
            "INSERT INTO compliance_events (event_id, profile, ts_utc, code, severity, details_json, source_system, source_mode, source_quality, asof_ts, received_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (eid, profile, ts, code, severity, details_json, *prov),
        )
        if hasattr(con, "commit"):
            con.commit()
    finally:
        con.close()
    return eid


def compute_paper_summary(
    *,
    profile: str = "paper",
    window_days: int = 60,
    as_of_date: Optional[date] = None,
) -> PaperSummary:
    init_execution_schema()
    d0 = as_of_date or datetime.now(timezone.utc).date()
    start_date = d0 - timedelta(days=window_days - 1)

    con = _connect()
    try:
        rows = con.execute(
            "SELECT asof_date, equity FROM paper_equity_snapshots WHERE profile = ? AND asof_date >= ? AND asof_date <= ? ORDER BY asof_date ASC",
            (profile, start_date.isoformat(), d0.isoformat()),
        ).fetchall()

        equities: list[float] = []
        for _, eq in rows:
            try:
                equities.append(float(eq))
            except (ValueError, TypeError):
                continue

        daily_returns: list[float] = []
        sharpe_a: Optional[float] = None
        mdd: Optional[float] = None
        if len(equities) >= 2:
            for i in range(1, len(equities)):
                prev = equities[i - 1]
                cur = equities[i]
                if prev and prev > 0:
                    daily_returns.append((cur / prev) - 1.0)
            sharpe_a = float(annualized_sharpe(daily_returns, periods_per_year=252))
            mdd = float(max_drawdown(equities))

        trows = con.execute(
            """
            SELECT
              pnl, slippage_ticks, violations,
              entry_ts_utc, symbol, strategy, strikes_json,
              regime_at_entry, score_at_entry, kelly_fraction, exit_reason, note
            FROM paper_trades
            WHERE profile = ? AND created_at IS NOT NULL
            ORDER BY created_at ASC
            """,
            (profile,),
        ).fetchall()

        pnls: list[float] = []
        slippages: list[float] = []
        violation_sum = 0

        required_missing = {
            "entry_ts_utc": 0,
            "symbol_strategy_strikes": 0,
            "regime_at_entry": 0,
            "score_at_entry": 0,
            "kelly_fraction": 0,
            "pnl_realized": 0,
            "slippage_actual": 0,
            "exit_reason": 0,
            "note_operational": 0,
        }

        for row in trows:
            pnl, slip, v, entry_ts, symbol, strategy, strikes_json, regime, score, kelly, exit_reason, note = row

            pnl_ok = False
            if pnl is not None:
                try:
                    fv = float(pnl)
                    pnls.append(fv)
                    pnl_ok = True
                except (ValueError, TypeError):
                    pnl_ok = False
            if not pnl_ok:
                required_missing["pnl_realized"] += 1

            slip_ok = False
            if slip is not None:
                try:
                    sv = float(slip)
                    slippages.append(sv)
                    slip_ok = True
                except (ValueError, TypeError):
                    slip_ok = False
            if not slip_ok:
                required_missing["slippage_actual"] += 1

            if not _is_present_text(entry_ts):
                required_missing["entry_ts_utc"] += 1

            has_symbol = _is_present_text(symbol)
            has_strategy = _is_present_text(strategy)
            has_strikes = _is_present_text(strikes_json)
            if not (has_symbol and has_strategy and has_strikes):
                required_missing["symbol_strategy_strikes"] += 1

            if not _is_present_text(regime):
                required_missing["regime_at_entry"] += 1

            if score is None:
                required_missing["score_at_entry"] += 1

            if kelly is None:
                required_missing["kelly_fraction"] += 1

            if not _is_present_text(exit_reason):
                required_missing["exit_reason"] += 1

            if not _is_present_text(note):
                required_missing["note_operational"] += 1

            try:
                violation_sum += int(v or 0)
            except (ValueError, TypeError):
                pass

        trade_count = len(trows)
        wr: Optional[float] = None
        pf: Optional[float] = None
        if pnls:
            wr = float(sum(1 for p in pnls if p > 0) / len(pnls))
            pos = sum(p for p in pnls if p > 0)
            neg = sum(p for p in pnls if p < 0)
            if neg < 0:
                pf = float(pos / abs(neg)) if abs(neg) > 1e-18 else float("inf")
            else:
                pf = float("inf") if pos > 0 else 0.0

        avg_slip: Optional[float] = None
        if slippages:
            avg_slip = float(sum(slippages) / len(slippages))

        crows = con.execute(
            "SELECT COUNT(*) FROM compliance_events WHERE profile = ?",
            (profile,),
        ).fetchall()
        compliance_events = int(crows[0][0]) if crows else 0
    finally:
        con.close()

    reasons_go: list[str] = []
    reasons_f6: list[str] = []

    go_ok = True
    if sharpe_a is None:
        go_ok = False
        reasons_go.append("missing equity snapshots (need daily equity series to compute Sharpe/MaxDD)")
    elif sharpe_a < 0.8:
        go_ok = False
        reasons_go.append(f"Sharpe {sharpe_a:.3f} < 0.8")

    if mdd is None:
        go_ok = False
        if "missing equity snapshots (need daily equity series to compute Sharpe/MaxDD)" not in reasons_go:
            reasons_go.append("missing equity snapshots (need daily equity series to compute Sharpe/MaxDD)")
    elif mdd >= 0.08:
        go_ok = False
        reasons_go.append(f"MaxDD {mdd:.3%} >= 8%")

    if len(pnls) < 10:
        go_ok = False
        reasons_go.append(f"trades {len(pnls)} < 10")

    if (compliance_events + violation_sum) != 0:
        go_ok = False
        reasons_go.append(f"compliance violations {compliance_events + violation_sum} != 0")

    f6_ok = True
    if len(pnls) < 20:
        f6_ok = False
        reasons_f6.append(f"trades {len(pnls)} < 20")

    if wr is None:
        f6_ok = False
        reasons_f6.append("missing trade journal (win_rate/profit_factor/slippage)")
    elif wr < 0.55:
        f6_ok = False
        reasons_f6.append(f"win_rate {wr:.3%} < 55%")

    if pf is None:
        f6_ok = False
        reasons_f6.append("missing trade journal (win_rate/profit_factor/slippage)")
    elif pf < 1.3:
        f6_ok = False
        reasons_f6.append(f"profit_factor {pf:.3f} < 1.3")

    if sharpe_a is None:
        f6_ok = False
    elif sharpe_a < 0.6:
        f6_ok = False
        reasons_f6.append(f"Sharpe {sharpe_a:.3f} < 0.6")

    if mdd is None:
        f6_ok = False
    elif mdd > 0.15:
        f6_ok = False
        reasons_f6.append(f"MaxDD {mdd:.3%} > 15%")

    if avg_slip is None:
        f6_ok = False
        reasons_f6.append("missing trade journal (win_rate/profit_factor/slippage)")
    elif avg_slip > 3.0:
        f6_ok = False
        reasons_f6.append(f"avg_slippage_ticks {avg_slip:.2f} > 3.0")

    if (compliance_events + violation_sum) != 0:
        f6_ok = False
        reasons_f6.append(f"compliance violations {compliance_events + violation_sum} != 0")

    journal_reasons: list[str] = []
    journal_ok = True
    if trade_count == 0:
        journal_ok = False
        journal_reasons.append("no paper trades recorded")

    missing_cells = 0
    for key, misses in required_missing.items():
        missing_cells += misses
        if misses > 0:
            journal_ok = False
            journal_reasons.append(f"{key} missing in {misses}/{trade_count} trades")

    fields_count = len(required_missing)
    denom = trade_count * fields_count
    completeness_ratio = (1.0 - (missing_cells / denom)) if denom > 0 else 0.0

    gates = {
        "go_nogo": {"pass": bool(go_ok), "reasons": reasons_go},
        "f6_t1_acceptance": {"pass": bool(f6_ok), "reasons": reasons_f6},
        "f6_t2_journal_complete": {
            "pass": bool(journal_ok),
            "reasons": journal_reasons,
            "completeness_ratio": completeness_ratio,
            "required_missing": required_missing,
        },
        "window": {"start_date": start_date.isoformat(), "end_date": d0.isoformat()},
        "data_points": {
            "equity_snapshots": len(equities),
            "trade_journal": trade_count,
            "trade_journal_metrics_rows": len(pnls),
            "compliance_events": compliance_events,
            "trade_violation_sum": violation_sum,
        },
    }

    return PaperSummary(
        profile=profile,
        window_days=window_days,
        as_of_date=d0,
        equity_points=len(equities),
        trades=len(pnls),
        sharpe_annualized=sharpe_a,
        max_drawdown=mdd,
        win_rate=wr,
        profit_factor=pf,
        avg_slippage_ticks=avg_slip,
        compliance_violations=compliance_events + violation_sum,
        gates=gates,
    )


def _history_env_int(name: str, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(value, high))


def _history_env_float(name: str, default: float, low: float, high: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(value, high))


def _history_table_exists(con: Any, table_name: str) -> bool:
    try:
        row = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
            (table_name,),
        ).fetchone()
        return bool(row and int(row[0]) > 0)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return True


def _history_to_day_key(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    txt = str(value).strip()
    if len(txt) < 10:
        return None
    return txt[:10]


def _history_is_present_text(value: Any) -> bool:
    if value is None:
        return False
    txt = str(value).strip()
    if not txt:
        return False
    return txt.lower() not in {"none", "null", "nan", "na", "n/a", "-", "--"}


def build_history_readiness(
    *,
    profile: str = "paper",
    db_connect_ro: Callable[[], AbstractContextManager[Any]],
    logger: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    window_days = _history_env_int("OPZ_HISTORY_READINESS_WINDOW_DAYS", 10, 3, 30)
    target_days = _history_env_int("OPZ_HISTORY_READINESS_TARGET_DAYS", 10, 3, 90)
    target_events = _history_env_int("OPZ_HISTORY_READINESS_TARGET_EVENTS", 40, 1, 10000)
    quality_target = _history_env_float("OPZ_HISTORY_READINESS_QUALITY_TARGET", 0.95, 0.50, 1.00)

    d0 = datetime.now(timezone.utc).date()
    d1 = d0 - timedelta(days=window_days - 1)
    d1_iso = d1.isoformat()
    d0_iso = d0.isoformat()

    days_seen: set[str] = set()
    snapshot_events = 0
    trade_events = 0
    decision_events = 0
    compliance_events_window = 0
    trade_violation_sum = 0
    quality_completeness = 0.0

    required_missing = {
        "entry_ts_utc": 0,
        "symbol_strategy_strikes": 0,
        "regime_at_entry": 0,
        "score_at_entry": 0,
        "kelly_fraction": 0,
        "pnl_realized": 0,
        "slippage_actual": 0,
        "exit_reason": 0,
        "note_operational": 0,
    }
    missing_cells = 0
    trade_rows_in_window = 0

    try:
        with db_connect_ro() as con:
            if _history_table_exists(con, "paper_equity_snapshots"):
                row = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM paper_equity_snapshots
                    WHERE profile = ? AND asof_date >= ? AND asof_date <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchone()
                snapshot_events = int(row[0]) if row and row[0] is not None else 0
                rows = con.execute(
                    """
                    SELECT DISTINCT asof_date
                    FROM paper_equity_snapshots
                    WHERE profile = ? AND asof_date >= ? AND asof_date <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchall()
                for r in rows:
                    day_key = _history_to_day_key(r[0] if r else None)
                    if day_key:
                        days_seen.add(day_key)

            if _history_table_exists(con, "paper_trades"):
                row = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM paper_trades
                    WHERE profile = ? AND created_at IS NOT NULL
                      AND CAST(created_at AS DATE) >= ? AND CAST(created_at AS DATE) <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchone()
                trade_events = int(row[0]) if row and row[0] is not None else 0
                rows = con.execute(
                    """
                    SELECT DISTINCT CAST(created_at AS DATE)
                    FROM paper_trades
                    WHERE profile = ? AND created_at IS NOT NULL
                      AND CAST(created_at AS DATE) >= ? AND CAST(created_at AS DATE) <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchall()
                for r in rows:
                    day_key = _history_to_day_key(r[0] if r else None)
                    if day_key:
                        days_seen.add(day_key)

                quality_rows = con.execute(
                    """
                    SELECT
                      entry_ts_utc, symbol, strategy, strikes_json, regime_at_entry,
                      score_at_entry, kelly_fraction, pnl, slippage_ticks, exit_reason,
                      note, violations
                    FROM paper_trades
                    WHERE profile = ? AND created_at IS NOT NULL
                      AND CAST(created_at AS DATE) >= ? AND CAST(created_at AS DATE) <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchall()
                trade_rows_in_window = len(quality_rows)
                for row in quality_rows:
                    (
                        entry_ts,
                        symbol,
                        strategy,
                        strikes_json,
                        regime_at_entry,
                        score_at_entry,
                        kelly_fraction,
                        pnl,
                        slippage_ticks,
                        exit_reason,
                        note,
                        violations,
                    ) = row

                    pnl_ok = False
                    if pnl is not None:
                        try:
                            _ = float(pnl)
                            pnl_ok = True
                        except (TypeError, ValueError):
                            pnl_ok = False
                    if not pnl_ok:
                        required_missing["pnl_realized"] += 1

                    slippage_ok = False
                    if slippage_ticks is not None:
                        try:
                            _ = float(slippage_ticks)
                            slippage_ok = True
                        except (TypeError, ValueError):
                            slippage_ok = False
                    if not slippage_ok:
                        required_missing["slippage_actual"] += 1

                    if not _history_is_present_text(entry_ts):
                        required_missing["entry_ts_utc"] += 1

                    has_symbol = _history_is_present_text(symbol)
                    has_strategy = _history_is_present_text(strategy)
                    has_strikes = _history_is_present_text(strikes_json)
                    if not (has_symbol and has_strategy and has_strikes):
                        required_missing["symbol_strategy_strikes"] += 1

                    if not _history_is_present_text(regime_at_entry):
                        required_missing["regime_at_entry"] += 1
                    if score_at_entry is None:
                        required_missing["score_at_entry"] += 1
                    if kelly_fraction is None:
                        required_missing["kelly_fraction"] += 1
                    if not _history_is_present_text(exit_reason):
                        required_missing["exit_reason"] += 1
                    if not _history_is_present_text(note):
                        required_missing["note_operational"] += 1

                    try:
                        trade_violation_sum += int(violations or 0)
                    except (TypeError, ValueError):
                        pass

            if _history_table_exists(con, "operator_opportunity_decisions"):
                row = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM operator_opportunity_decisions
                    WHERE profile = ? AND created_at IS NOT NULL
                      AND CAST(created_at AS DATE) >= ? AND CAST(created_at AS DATE) <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchone()
                decision_events = int(row[0]) if row and row[0] is not None else 0
                rows = con.execute(
                    """
                    SELECT DISTINCT CAST(created_at AS DATE)
                    FROM operator_opportunity_decisions
                    WHERE profile = ? AND created_at IS NOT NULL
                      AND CAST(created_at AS DATE) >= ? AND CAST(created_at AS DATE) <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchall()
                for r in rows:
                    day_key = _history_to_day_key(r[0] if r else None)
                    if day_key:
                        days_seen.add(day_key)

            if _history_table_exists(con, "compliance_events"):
                row = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM compliance_events
                    WHERE profile = ? AND ts_utc IS NOT NULL
                      AND CAST(ts_utc AS DATE) >= ? AND CAST(ts_utc AS DATE) <= ?
                    """,
                    (profile, d1_iso, d0_iso),
                ).fetchone()
                compliance_events_window = int(row[0]) if row and row[0] is not None else 0
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        if logger is not None:
            logger.debug("SYSTEM_STATUS_HISTORY_READINESS_FALLBACK reason=%s", exc)

    for misses in required_missing.values():
        missing_cells += misses
    fields_count = len(required_missing)
    denom = trade_rows_in_window * fields_count
    if denom > 0:
        quality_completeness = max(0.0, min(1.0, 1.0 - (missing_cells / denom)))

    days_observed = len(days_seen)
    days_remaining = max(0, target_days - days_observed)

    events_observed = trade_events + decision_events
    events_remaining = max(0, target_events - events_observed)

    pace_events_per_day = round(events_observed / days_observed, 2) if days_observed > 0 else 0.0
    quality_gap = round(max(0.0, quality_target - quality_completeness), 4)
    compliance_violations_window = max(0, compliance_events_window + trade_violation_sum)

    blockers: list[str] = []
    if days_remaining > 0:
        blockers.append(f"coverage_days {days_observed}/{target_days}")
    if events_remaining > 0:
        blockers.append(f"events {events_observed}/{target_events}")
    if quality_gap > 0:
        blockers.append(
            f"journal_quality {(quality_completeness * 100):.1f}% < {(quality_target * 100):.1f}%"
        )
    if compliance_violations_window > 0:
        blockers.append(f"compliance_violations_window={compliance_violations_window}")

    ready = len(blockers) == 0

    eta_events_days: Optional[int] = None
    if events_remaining <= 0:
        eta_events_days = 0
    elif pace_events_per_day > 0:
        eta_events_days = int(math.ceil(events_remaining / pace_events_per_day))

    if ready:
        eta_days: Optional[int] = 0
    elif events_remaining > 0 and eta_events_days is None:
        eta_days = None
    else:
        eta_days = max(days_remaining, eta_events_days or 0)

    eta_date_utc = (d0 + timedelta(days=eta_days)).isoformat() if eta_days is not None else None

    day_score = min(1.0, (days_observed / target_days) if target_days > 0 else 0.0)
    event_score = min(1.0, (events_observed / target_events) if target_events > 0 else 0.0)
    quality_score = min(1.0, (quality_completeness / quality_target) if quality_target > 0 else 0.0)
    compliance_score = 1.0 if compliance_violations_window == 0 else 0.0
    score_pct = round((0.35 * day_score + 0.35 * event_score + 0.20 * quality_score + 0.10 * compliance_score) * 100.0, 1)

    return {
        "profile": profile,
        "window_days": window_days,
        "target_days": target_days,
        "days_observed": days_observed,
        "days_remaining": days_remaining,
        "target_events": target_events,
        "events_observed": events_observed,
        "events_remaining": events_remaining,
        "event_breakdown": {
            "equity_snapshots": snapshot_events,
            "paper_trades": trade_events,
            "opportunity_decisions": decision_events,
        },
        "quality_completeness": round(quality_completeness, 4),
        "quality_target": round(quality_target, 4),
        "quality_gap": quality_gap,
        "compliance_violations_window": compliance_violations_window,
        "pace_events_per_day": pace_events_per_day,
        "eta_days": eta_days,
        "eta_date_utc": eta_date_utc,
        "blockers": blockers,
        "ready": ready,
        "score_pct": score_pct,
    }
