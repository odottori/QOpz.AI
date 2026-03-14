from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from scripts.metrics import annualized_sharpe, max_drawdown
from .storage import _connect, init_execution_schema


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
) -> str:
    init_execution_schema()
    con = _connect()
    sid = str(uuid.uuid4())
    backend = type(con).__module__.split(".")[0]
    created = _utc_now_iso()
    if backend == "duckdb":
        con.execute(
            "INSERT INTO paper_equity_snapshots (snapshot_id, profile, asof_date, equity, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (sid, profile, asof_date.isoformat(), float(equity), note, created),
        )
        con.close()
        return sid

    con.execute(
        "INSERT INTO paper_equity_snapshots (snapshot_id, profile, asof_date, equity, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (sid, profile, asof_date.isoformat(), float(equity), note, created),
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
) -> str:
    init_execution_schema()
    con = _connect()
    tid = str(uuid.uuid4())
    created = _utc_now_iso()

    entry_s = _norm_ts_utc(entry_ts_utc)
    exit_s = _norm_ts_utc(exit_ts_utc)
    strikes_json = json.dumps(strikes, ensure_ascii=False) if strikes is not None else None

    try:
        con.execute(
            """
            INSERT INTO paper_trades (
                trade_id, profile, symbol, strategy, entry_ts_utc, exit_ts_utc,
                strikes_json, regime_at_entry, score_at_entry, kelly_fraction, exit_reason,
                pnl, pnl_pct, slippage_ticks, violations, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                created,
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

    try:
        con.execute(
            "INSERT INTO compliance_events (event_id, profile, ts_utc, code, severity, details_json) VALUES (?, ?, ?, ?, ?, ?)",
            (eid, profile, ts, code, severity, details_json),
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
            except Exception:
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
                except Exception:
                    pnl_ok = False
            if not pnl_ok:
                required_missing["pnl_realized"] += 1

            slip_ok = False
            if slip is not None:
                try:
                    sv = float(slip)
                    slippages.append(sv)
                    slip_ok = True
                except Exception:
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
            except Exception:
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
