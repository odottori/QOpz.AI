from __future__ import annotations

import json
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from execution.storage import _connect, _prov, init_execution_schema, utc_now

DEFAULT_FORWARD_HORIZONS: tuple[int, ...] = (1, 5, 20)
DEFAULT_SCORECARD_WINDOW_DAYS = 90


def _as_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        txt = value.strip()
        if not txt:
            raise ValueError("empty date string")
        if "T" in txt:
            return datetime.fromisoformat(txt.replace("Z", "+00:00")).date()
        return date.fromisoformat(txt)
    raise TypeError(f"cannot convert to date: {type(value)!r}")


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(value, str):
        txt = value.strip()
        if not txt:
            raise ValueError("empty datetime string")
        if "T" in txt:
            return datetime.fromisoformat(txt.replace("Z", "+00:00"))
        return datetime.combine(date.fromisoformat(txt), datetime.min.time(), tzinfo=timezone.utc)
    raise TypeError(f"cannot convert to datetime: {type(value)!r}")


def _round_or_none(value: Any, ndigits: int = 4) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), ndigits)
    except Exception:
        return None


def infer_signal_direction(strategy: Optional[str]) -> str:
    name = (strategy or "").strip().upper()
    if not name:
        return "unknown"
    bullish_tokens = ("BULL", "CSP", "COVERED_CALL", "WHEEL_PUT")
    bearish_tokens = ("BEAR",)
    neutral_names = {"IRON_CONDOR", "STRADDLE", "STRANGLE", "WHEEL", "WHEEL_CALL"}
    if any(tok in name for tok in bullish_tokens):
        return "bullish"
    if any(tok in name for tok in bearish_tokens):
        return "bearish"
    if name in neutral_names:
        return "neutral"
    return "neutral"


def classify_signal_success(*, signal_direction: str, spot_return_pct: float, within_expected_move: Optional[bool]) -> tuple[Optional[bool], str]:
    direction = (signal_direction or "unknown").strip().lower()
    if direction == "bullish":
        return (spot_return_pct > 0.0, "favorable" if spot_return_pct > 0.0 else "adverse")
    if direction == "bearish":
        return (spot_return_pct < 0.0, "favorable" if spot_return_pct < 0.0 else "adverse")
    if direction == "neutral":
        if within_expected_move is None:
            return (None, "unclassified")
        return (within_expected_move, "contained" if within_expected_move else "breached")
    return (None, "unclassified")


def _insert_signal_observation(con: Any, *, profile: str, batch_id: Optional[str], candidate_id: Optional[str], scan_ts: Any, regime: Optional[str], data_mode: Optional[str], candidate: Any) -> str:
    ts = _as_datetime(scan_ts)
    obs_id = str(uuid.uuid4())
    payload: dict[str, Any] = asdict(candidate) if is_dataclass(candidate) else dict(candidate)
    prov = _prov(profile, ts)
    strategy = payload.get("strategy")
    context = {
        "score_breakdown": payload.get("score_breakdown") or {},
        "events_flag": payload.get("events_flag"),
        "human_review_required": bool(payload.get("human_review_required")),
        "credit_or_debit": payload.get("credit_or_debit"),
        "sizing_suggested": payload.get("sizing_suggested"),
        "kelly_fraction": payload.get("kelly_fraction"),
        "stress_base": payload.get("stress_base"),
        "stress_shock": payload.get("stress_shock"),
    }
    con.execute(
        """
        INSERT INTO signal_observations (
            observation_id, candidate_id, batch_id, profile,
            observed_at, observed_date, regime, data_mode,
            symbol, strategy, signal_direction, score,
            expiry, dte, strikes_json,
            underlying_price, expected_move_pct, signal_vs_em_ratio,
            max_loss, max_loss_pct,
            data_quality, source, observation_context_json,
            source_system, source_mode, source_quality, asof_ts, received_ts
        ) VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
        """,
        (
            obs_id,
            candidate_id,
            batch_id,
            profile,
            ts,
            ts.date().isoformat(),
            regime,
            data_mode,
            payload.get("symbol"),
            strategy,
            infer_signal_direction(strategy),
            payload.get("score"),
            payload.get("expiry"),
            payload.get("dte"),
            json.dumps(payload.get("strikes") or []),
            payload.get("underlying_price"),
            payload.get("expected_move"),
            payload.get("signal_vs_em_ratio"),
            payload.get("max_loss"),
            payload.get("max_loss_pct"),
            payload.get("data_quality"),
            payload.get("source"),
            json.dumps(context, ensure_ascii=False),
            *prov,
        ),
    )
    return obs_id


def record_signal_observation(*, profile: str, batch_id: Optional[str], candidate_id: Optional[str], scan_ts: Any, regime: Optional[str], data_mode: Optional[str], candidate: Any) -> str:
    init_execution_schema()
    con = _connect()
    try:
        obs_id = _insert_signal_observation(
            con,
            profile=profile,
            batch_id=batch_id,
            candidate_id=candidate_id,
            scan_ts=scan_ts,
            regime=regime,
            data_mode=data_mode,
            candidate=candidate,
        )
        if hasattr(con, "commit"):
            con.commit()
        return obs_id
    finally:
        con.close()


def _get_market_close(con: Any, *, symbol: str, on_or_after: date) -> tuple[Optional[date], Optional[float]]:
    row = con.execute(
        """
        SELECT dt, COALESCE(adj_close, close) AS px
        FROM market_data
        WHERE symbol = ?
          AND dt >= ?
          AND COALESCE(adj_close, close) IS NOT NULL
        ORDER BY dt ASC
        LIMIT 1
        """,
        (symbol, on_or_after.isoformat()),
    ).fetchone()
    if not row:
        return None, None
    return _as_date(row[0]), float(row[1])


def recompute_forward_outcomes(*, profile: str = "paper", asof_date: Any | None = None, horizons: Iterable[int] = DEFAULT_FORWARD_HORIZONS, symbol: Optional[str] = None) -> dict[str, Any]:
    init_execution_schema()
    con = _connect()
    now = utc_now()
    prov = _prov(profile, now)
    asof_d = _as_date(asof_date) if asof_date is not None else now.date()
    horizon_list = sorted({int(h) for h in horizons if int(h) > 0})
    if not horizon_list:
        raise ValueError("at least one positive horizon is required")
    params: list[Any] = [profile]
    where = ["profile = ?"]
    if symbol:
        where.append("symbol = ?")
        params.append(symbol.strip().upper())
    rows = con.execute(
        f"""
        SELECT observation_id, observed_date, symbol, strategy, signal_direction,
               underlying_price, expected_move_pct, score
        FROM signal_observations
        WHERE {' AND '.join(where)}
        ORDER BY observed_at ASC, observation_id ASC
        """,
        params,
    ).fetchall()
    computed = 0
    pending = 0
    missing_market_data = 0
    observations_touched = 0
    try:
        for row in rows:
            observation_id = str(row[0])
            observed_date = _as_date(row[1])
            obs_symbol = str(row[2])
            strategy = row[3]
            direction = row[4] or infer_signal_direction(strategy)
            entry_price = _round_or_none(row[5], 6)
            expected_move_pct = _round_or_none(row[6], 6)
            score = _round_or_none(row[7], 4)
            if entry_price is None or entry_price <= 0.0:
                _, entry_price = _get_market_close(con, symbol=obs_symbol, on_or_after=observed_date)
            if entry_price is None or entry_price <= 0.0:
                missing_market_data += len(horizon_list)
                continue
            observations_touched += 1
            for horizon_days in horizon_list:
                target_date = observed_date + timedelta(days=horizon_days)
                outcome_id = f"{observation_id}:{horizon_days}"
                base_values = [
                    outcome_id, observation_id, profile, obs_symbol, strategy,
                    direction, horizon_days, observed_date.isoformat(), target_date.isoformat(),
                    entry_price,
                ]
                if target_date > asof_d:
                    con.execute(
                        """
                        INSERT OR REPLACE INTO signal_forward_outcomes (
                            outcome_id, observation_id, profile, symbol, strategy,
                            signal_direction, horizon_days, observation_date, target_date,
                            entry_price, outcome_date, outcome_price,
                            spot_return_pct, realized_move_abs_pct,
                            expected_move_pct, within_expected_move, success,
                            outcome_label, status, score_at_observation,
                            computed_at, source_system, source_mode, source_quality, asof_ts, received_ts
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        tuple(base_values + [None, None, None, None, expected_move_pct, None, None, "pending", "pending_horizon", score, now, *prov]),
                    )
                    pending += 1
                    continue
                px_date, outcome_price = _get_market_close(con, symbol=obs_symbol, on_or_after=target_date)
                if outcome_price is None or px_date is None:
                    con.execute(
                        """
                        INSERT OR REPLACE INTO signal_forward_outcomes (
                            outcome_id, observation_id, profile, symbol, strategy,
                            signal_direction, horizon_days, observation_date, target_date,
                            entry_price, outcome_date, outcome_price,
                            spot_return_pct, realized_move_abs_pct,
                            expected_move_pct, within_expected_move, success,
                            outcome_label, status, score_at_observation,
                            computed_at, source_system, source_mode, source_quality, asof_ts, received_ts
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        tuple(base_values + [None, None, None, None, expected_move_pct, None, None, "missing_market_data", "missing_market_data", score, now, *prov]),
                    )
                    missing_market_data += 1
                    continue
                spot_return_pct = round(((outcome_price - entry_price) / entry_price) * 100.0, 4)
                realized_move_abs_pct = round(abs(spot_return_pct), 4)
                within_expected_move = None if expected_move_pct is None else realized_move_abs_pct <= round(expected_move_pct * 100.0, 4)
                success, label = classify_signal_success(signal_direction=str(direction), spot_return_pct=spot_return_pct, within_expected_move=within_expected_move)
                con.execute(
                    """
                    INSERT OR REPLACE INTO signal_forward_outcomes (
                        outcome_id, observation_id, profile, symbol, strategy,
                        signal_direction, horizon_days, observation_date, target_date,
                        entry_price, outcome_date, outcome_price,
                        spot_return_pct, realized_move_abs_pct,
                        expected_move_pct, within_expected_move, success,
                        outcome_label, status, score_at_observation,
                        computed_at, source_system, source_mode, source_quality, asof_ts, received_ts
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    tuple(base_values + [px_date.isoformat(), outcome_price, spot_return_pct, realized_move_abs_pct, expected_move_pct, within_expected_move, success, label, "computed", score, now, *prov]),
                )
                computed += 1
        if hasattr(con, "commit"):
            con.commit()
    finally:
        con.close()
    return {
        "ok": True,
        "profile": profile,
        "asof_date": asof_d.isoformat(),
        "horizons": horizon_list,
        "observations_touched": observations_touched,
        "computed": computed,
        "pending": pending,
        "missing_market_data": missing_market_data,
    }


def rebuild_signal_scorecards(*, profile: str = "paper", asof_date: Any | None = None, window_days: int = DEFAULT_SCORECARD_WINDOW_DAYS, horizons: Iterable[int] = DEFAULT_FORWARD_HORIZONS) -> dict[str, Any]:
    init_execution_schema()
    con = _connect()
    now = utc_now()
    prov = _prov(profile, now)
    asof_d = _as_date(asof_date) if asof_date is not None else now.date()
    window_days = max(1, int(window_days))
    start_d = asof_d - timedelta(days=window_days - 1)
    horizon_list = sorted({int(h) for h in horizons if int(h) > 0})
    if not horizon_list:
        raise ValueError("at least one positive horizon is required")
    created_rows = 0
    scorecards: list[dict[str, Any]] = []
    try:
        for horizon_days in horizon_list:
            base_params = (profile, horizon_days, start_d.isoformat(), asof_d.isoformat())
            agg_rows = list(con.execute(
                """
                SELECT
                    strategy AS strategy_key,
                    COUNT(*) AS observations_count,
                    SUM(CASE WHEN status = 'computed' THEN 1 ELSE 0 END) AS outcomes_ready_count,
                    AVG(CASE WHEN status = 'computed' THEN spot_return_pct END) AS avg_forward_return_pct,
                    MEDIAN(CASE WHEN status = 'computed' THEN spot_return_pct END) AS median_forward_return_pct,
                    AVG(CASE WHEN status = 'computed' THEN CAST(success AS DOUBLE) END) AS hit_rate,
                    AVG(CASE WHEN status = 'computed' THEN CAST(within_expected_move AS DOUBLE) END) AS containment_rate,
                    AVG(score_at_observation) AS avg_score
                FROM signal_forward_outcomes
                WHERE profile = ?
                  AND horizon_days = ?
                  AND observation_date >= ?
                  AND observation_date <= ?
                GROUP BY strategy
                ORDER BY strategy_key ASC
                """,
                base_params,
            ).fetchall())
            overall_row = con.execute(
                """
                SELECT
                    'ALL' AS strategy_key,
                    COUNT(*) AS observations_count,
                    SUM(CASE WHEN status = 'computed' THEN 1 ELSE 0 END) AS outcomes_ready_count,
                    AVG(CASE WHEN status = 'computed' THEN spot_return_pct END) AS avg_forward_return_pct,
                    MEDIAN(CASE WHEN status = 'computed' THEN spot_return_pct END) AS median_forward_return_pct,
                    AVG(CASE WHEN status = 'computed' THEN CAST(success AS DOUBLE) END) AS hit_rate,
                    AVG(CASE WHEN status = 'computed' THEN CAST(within_expected_move AS DOUBLE) END) AS containment_rate,
                    AVG(score_at_observation) AS avg_score
                FROM signal_forward_outcomes
                WHERE profile = ?
                  AND horizon_days = ?
                  AND observation_date >= ?
                  AND observation_date <= ?
                """,
                base_params,
            ).fetchone()
            if overall_row is not None:
                agg_rows.append(overall_row)
            for row in agg_rows:
                strategy_key = row[0] if row[0] not in (None, "") else "ALL"
                observations_count = int(row[1] or 0)
                outcomes_ready_count = int(row[2] or 0)
                payload = {
                    "strategy": None if strategy_key == "ALL" else strategy_key,
                    "observations_count": observations_count,
                    "outcomes_ready_count": outcomes_ready_count,
                    "pending_count": max(observations_count - outcomes_ready_count, 0),
                    "hit_rate_pct": _round_or_none(None if row[5] is None else float(row[5]) * 100.0, 2),
                    "containment_rate_pct": _round_or_none(None if row[6] is None else float(row[6]) * 100.0, 2),
                    "avg_forward_return_pct": _round_or_none(row[3], 4),
                    "median_forward_return_pct": _round_or_none(row[4], 4),
                    "avg_score": _round_or_none(row[7], 2),
                }
                scorecards.append(payload)
                con.execute(
                    """
                    INSERT OR REPLACE INTO signal_scorecards (
                        scorecard_id, profile, asof_date, window_days, horizon_days,
                        strategy, observations_count, outcomes_ready_count, pending_count,
                        hit_rate_pct, containment_rate_pct,
                        avg_forward_return_pct, median_forward_return_pct, avg_score,
                        summary_json, computed_at,
                        source_system, source_mode, source_quality, asof_ts, received_ts
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        f"{profile}:{asof_d.isoformat()}:{window_days}:{horizon_days}:{strategy_key}",
                        profile,
                        asof_d.isoformat(),
                        window_days,
                        horizon_days,
                        None if strategy_key == "ALL" else strategy_key,
                        observations_count,
                        outcomes_ready_count,
                        max(observations_count - outcomes_ready_count, 0),
                        payload["hit_rate_pct"],
                        payload["containment_rate_pct"],
                        payload["avg_forward_return_pct"],
                        payload["median_forward_return_pct"],
                        payload["avg_score"],
                        json.dumps(payload, ensure_ascii=False),
                        now,
                        *prov,
                    ),
                )
                created_rows += 1
        if hasattr(con, "commit"):
            con.commit()
    finally:
        con.close()
    return {
        "ok": True,
        "profile": profile,
        "asof_date": asof_d.isoformat(),
        "window_days": window_days,
        "horizons": horizon_list,
        "scorecards_created": created_rows,
        "scorecards": scorecards,
    }


def list_signal_observations(*, profile: str = "paper", symbol: Optional[str] = None, strategy: Optional[str] = None, limit: int = 100, include_outcomes: bool = True) -> list[dict[str, Any]]:
    init_execution_schema()
    con = _connect()
    params: list[Any] = [profile]
    where = ["profile = ?"]
    if symbol:
        where.append("symbol = ?")
        params.append(symbol.strip().upper())
    if strategy:
        where.append("strategy = ?")
        params.append(strategy.strip().upper())
    params.append(max(1, min(int(limit), 500)))
    try:
        rows = con.execute(
            f"""
            SELECT observation_id, candidate_id, batch_id, profile,
                   observed_at, observed_date, regime, data_mode,
                   symbol, strategy, signal_direction, score,
                   expiry, dte, strikes_json,
                   underlying_price, expected_move_pct, signal_vs_em_ratio,
                   max_loss, max_loss_pct,
                   data_quality, source, observation_context_json
            FROM signal_observations
            WHERE {' AND '.join(where)}
            ORDER BY observed_at DESC, observation_id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            observation_id = str(row[0])
            item = {
                "observation_id": observation_id,
                "candidate_id": row[1],
                "batch_id": row[2],
                "profile": row[3],
                "observed_at": str(row[4]) if row[4] is not None else None,
                "observed_date": str(row[5]) if row[5] is not None else None,
                "regime": row[6],
                "data_mode": row[7],
                "symbol": row[8],
                "strategy": row[9],
                "signal_direction": row[10],
                "score": _round_or_none(row[11], 2),
                "expiry": row[12],
                "dte": row[13],
                "strikes": json.loads(row[14]) if row[14] else [],
                "underlying_price": _round_or_none(row[15], 6),
                "expected_move_pct": _round_or_none(None if row[16] is None else float(row[16]) * 100.0, 4),
                "signal_vs_em_ratio": _round_or_none(row[17], 4),
                "max_loss": _round_or_none(row[18], 4),
                "max_loss_pct": _round_or_none(row[19], 4),
                "data_quality": row[20],
                "source": row[21],
                "context": json.loads(row[22]) if row[22] else {},
            }
            if include_outcomes:
                o_rows = con.execute(
                    """
                    SELECT horizon_days, target_date, outcome_date, outcome_price,
                           spot_return_pct, realized_move_abs_pct,
                           expected_move_pct, within_expected_move, success,
                           outcome_label, status
                    FROM signal_forward_outcomes
                    WHERE observation_id = ?
                    ORDER BY horizon_days ASC
                    """,
                    (observation_id,),
                ).fetchall()
                item["forward_outcomes"] = [
                    {
                        "horizon_days": int(orow[0]),
                        "target_date": str(orow[1]) if orow[1] is not None else None,
                        "outcome_date": str(orow[2]) if orow[2] is not None else None,
                        "outcome_price": _round_or_none(orow[3], 6),
                        "spot_return_pct": _round_or_none(orow[4], 4),
                        "realized_move_abs_pct": _round_or_none(orow[5], 4),
                        "expected_move_pct": _round_or_none(None if orow[6] is None else float(orow[6]) * 100.0, 4),
                        "within_expected_move": None if orow[7] is None else bool(orow[7]),
                        "success": None if orow[8] is None else bool(orow[8]),
                        "outcome_label": orow[9],
                        "status": orow[10],
                    }
                    for orow in o_rows
                ]
            out.append(item)
        return out
    finally:
        con.close()


def list_signal_scorecards(*, profile: str = "paper", asof_date: Any | None = None, window_days: int | None = None, horizon_days: int | None = None, strategy: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    init_execution_schema()
    con = _connect()
    params: list[Any] = [profile]
    where = ["profile = ?"]
    if asof_date is not None:
        where.append("asof_date = ?")
        params.append(_as_date(asof_date).isoformat())
    if window_days is not None:
        where.append("window_days = ?")
        params.append(int(window_days))
    if horizon_days is not None:
        where.append("horizon_days = ?")
        params.append(int(horizon_days))
    if strategy:
        where.append("strategy = ?")
        params.append(strategy.strip().upper())
    params.append(max(1, min(int(limit), 500)))
    try:
        rows = con.execute(
            f"""
            SELECT asof_date, window_days, horizon_days, strategy,
                   observations_count, outcomes_ready_count, pending_count,
                   hit_rate_pct, containment_rate_pct,
                   avg_forward_return_pct, median_forward_return_pct, avg_score,
                   computed_at, summary_json
            FROM signal_scorecards
            WHERE {' AND '.join(where)}
            ORDER BY asof_date DESC, horizon_days ASC, COALESCE(strategy, 'ALL') ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            {
                "asof_date": str(row[0]) if row[0] is not None else None,
                "window_days": int(row[1]),
                "horizon_days": int(row[2]),
                "strategy": row[3],
                "observations_count": int(row[4] or 0),
                "outcomes_ready_count": int(row[5] or 0),
                "pending_count": int(row[6] or 0),
                "hit_rate_pct": _round_or_none(row[7], 2),
                "containment_rate_pct": _round_or_none(row[8], 2),
                "avg_forward_return_pct": _round_or_none(row[9], 4),
                "median_forward_return_pct": _round_or_none(row[10], 4),
                "avg_score": _round_or_none(row[11], 2),
                "computed_at": str(row[12]) if row[12] is not None else None,
                "summary": json.loads(row[13]) if row[13] else {},
            }
            for row in rows
        ]
    finally:
        con.close()
