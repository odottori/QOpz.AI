"""
scripts/session_runner.py — Orchestratore sessioni morning / EOD

Morning session (--type morning):
  1. Regime check     → GET /opz/regime/current
  2. IV history       → fetch_iv_history() per simboli universe
  3. Events calendar  → check_events() per simboli universe
  4. Universe scan    → GET /opz/universe/scan (source=auto)
  5. Briefing         → POST /opz/briefing/generate (no_telegram opzionale)

EOD session (--type eod):
  1. Paper summary    → GET /opz/paper/summary
  2. Exit candidates  → GET /opz/opportunity/exit_candidates
  3. Log EOD snapshot in output JSON

Nessun Ollama. Nessun HTML capture. Nessun LLM.

CLI:
    python scripts/session_runner.py --type morning --profile paper
    python scripts/session_runner.py --type eod    --profile paper --format json
    python scripts/session_runner.py --check-day                   # stampa se oggi è giorno di trading
"""
from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ── Costanti ─────────────────────────────────────────────────────────────────

DEFAULT_API_BASE = "http://localhost:8765"
DEFAULT_PROFILE  = "paper"
MAX_SYMBOLS      = 8   # max simboli per IV history + events
CONNECT_TIMEOUT  = 10  # s
READ_TIMEOUT     = 60  # s


# ─────────────────────────────────────────────────────────────────────────────
# NYSE holiday calendar (algoritmico, no dipendenze esterne)
# ─────────────────────────────────────────────────────────────────────────────

def _nth_weekday(year: int, month: int, n: int, weekday: int) -> date:
    """n-esima occorrenza (1-based) di weekday (0=Lun) nel mese."""
    d = date(year, month, 1)
    diff = (weekday - d.weekday()) % 7
    first = d.replace(day=1 + diff)
    return first.replace(day=first.day + (n - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Ultima occorrenza di weekday nel mese."""
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    diff = (d.weekday() - weekday) % 7
    return d.replace(day=last_day - diff)


def _easter_sunday(year: int) -> date:
    """Algoritmo di Gauss per la Pasqua gregoriana."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _observed(d: date) -> date:
    """Holiday su weekend → sposta al venerdì precedente o lunedì successivo."""
    if d.weekday() == 5:   # Sabato → Venerdì
        return d - timedelta(days=1)
    if d.weekday() == 6:   # Domenica → Lunedì
        return d + timedelta(days=1)
    return d


def nyse_holidays(year: int) -> frozenset[date]:
    """Restituisce l'insieme dei giorni di chiusura NYSE per l'anno dato."""
    good_friday = _easter_sunday(year) - timedelta(days=2)
    # Memorial Day = ultimo lunedì di maggio
    try:
        memorial = _nth_weekday(year, 5, 5, 0)
    except ValueError:
        memorial = _nth_weekday(year, 5, 4, 0)

    holidays: set[date] = {
        _observed(date(year, 1, 1)),          # New Year's Day
        _nth_weekday(year, 1, 3, 0),          # MLK Day (3° lunedì gennaio)
        _nth_weekday(year, 2, 3, 0),          # Presidents Day (3° lunedì febbraio)
        good_friday,                           # Good Friday
        memorial,                              # Memorial Day
        _nth_weekday(year, 9, 1, 0),          # Labor Day (1° lunedì settembre)
        _nth_weekday(year, 11, 4, 3),         # Thanksgiving (4° giovedì novembre)
        _observed(date(year, 12, 25)),         # Christmas
        _observed(date(year, 7, 4)),           # Independence Day
    }
    if year >= 2022:
        holidays.add(_observed(date(year, 6, 19)))  # Juneteenth

    return frozenset(holidays)


def is_trading_day(d: Optional[date] = None) -> bool:
    """True se d è un giorno di trading NYSE (lunedì–venerdì, non festivo)."""
    if d is None:
        d = date.today()
    if d.weekday() >= 5:   # sabato=5, domenica=6
        return False
    return d not in nyse_holidays(d.year)


def _next_session_dt(
    now: datetime,
    morning_time: "time_cls",
    eod_time: "time_cls",
    tz_name: str,
) -> "tuple[datetime, str]":
    """
    Calcola (datetime_prossima_sessione, tipo) a partire da now (timezone-aware).
    Considera skip weekend e holiday NYSE.
    """
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    now_local = now.astimezone(tz)
    today = now_local.date()

    def _make_dt(d: date, t: "time_cls") -> datetime:
        return datetime(d.year, d.month, d.day, t.hour, t.minute, 0, tzinfo=tz)

    candidates: list[tuple[datetime, str]] = []
    for offset in range(0, 8):   # cerca nei prossimi 7 giorni
        d = today + timedelta(days=offset)
        if not is_trading_day(d):
            continue
        morning_dt = _make_dt(d, morning_time)
        eod_dt = _make_dt(d, eod_time)
        if morning_dt > now_local:
            candidates.append((morning_dt, "morning"))
        if eod_dt > now_local:
            candidates.append((eod_dt, "eod"))

    if not candidates:
        # fallback: domani mattina
        tomorrow = today + timedelta(days=1)
        return _make_dt(tomorrow, morning_time), "morning"

    candidates.sort(key=lambda x: x[0])
    return candidates[0]


# ─────────────────────────────────────────────────────────────────────────────
# Helper HTTP
# ─────────────────────────────────────────────────────────────────────────────

def _get(api_base: str, path: str, params: Optional[dict] = None) -> tuple[bool, Any]:
    """GET con timeout. Restituisce (ok, data)."""
    try:
        import httpx
        r = httpx.get(
            f"{api_base}{path}",
            params=params or {},
            timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT),
        )
        r.raise_for_status()
        return True, r.json()
    except Exception as exc:
        return False, {"error": str(exc)}


def _post(api_base: str, path: str, params: Optional[dict] = None) -> tuple[bool, Any]:
    """POST con timeout. Restituisce (ok, data)."""
    try:
        import httpx
        r = httpx.post(
            f"{api_base}{path}",
            params=params or {},
            timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT),
        )
        r.raise_for_status()
        return True, r.json()
    except Exception as exc:
        return False, {"error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Universe symbols
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_SYMBOLS = ["SPY", "QQQ", "IWM", "GLD", "TLT"]


def _get_universe_symbols(api_base: str) -> list[str]:
    """Recupera i simboli universe dalle impostazioni IBKR o usa fallback."""
    ok, ctx = _get(api_base, "/opz/universe/ibkr_context")
    if ok:
        syms = ctx.get("quote_symbols") or []
        if syms:
            return [str(s).upper() for s in syms[:MAX_SYMBOLS]]
    return _FALLBACK_SYMBOLS[:MAX_SYMBOLS]


# ─────────────────────────────────────────────────────────────────────────────
# Morning session
# ─────────────────────────────────────────────────────────────────────────────

def run_morning(profile: str = DEFAULT_PROFILE, api_base: str = DEFAULT_API_BASE) -> dict[str, Any]:
    """
    Esegue la sessione mattutina completa.
    Restituisce un dict con i risultati di ogni step.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    steps: dict[str, Any] = {}
    errors: list[str] = []

    # ── Step 1: Regime ────────────────────────────────────────────────────────
    ok, data = _get(api_base, "/opz/regime/current", {"window": 30})
    steps["regime"] = {
        "ok": ok,
        "regime": data.get("regime", "UNKNOWN") if ok else None,
        "n_recent": data.get("n_recent", 0) if ok else 0,
        "error": data.get("error") if not ok else None,
    }
    if not ok:
        errors.append(f"regime: {data.get('error')}")

    # ── Step 2: Universe symbols ──────────────────────────────────────────────
    symbols = _get_universe_symbols(api_base)
    steps["symbols"] = {"ok": True, "symbols": symbols, "count": len(symbols)}

    # ── Step 3: IV history ────────────────────────────────────────────────────
    iv_results: dict[str, Any] = {}
    try:
        from scripts.fetch_iv_history import fetch_iv_history, save_iv_history
        for sym in symbols:
            try:
                hist = fetch_iv_history(sym)
                save_iv_history(sym, hist)
                iv_results[sym] = {"ok": True, "points": len(hist)}
            except Exception as exc:
                iv_results[sym] = {"ok": False, "error": str(exc)}
                errors.append(f"iv_history[{sym}]: {exc}")
    except ImportError as exc:
        iv_results = {"import_error": str(exc)}
        errors.append(f"iv_history import: {exc}")
    steps["iv_history"] = {"ok": not errors or all(v.get("ok") for v in iv_results.values() if isinstance(v, dict)), "symbols": iv_results}

    # ── Step 4: Events calendar ───────────────────────────────────────────────
    events_results: dict[str, Any] = {}
    try:
        from scripts.events_calendar import check_events
        for sym in symbols:
            try:
                ev = check_events(sym)
                events_results[sym] = {
                    "ok": True,
                    "block_trade": ev.block_trade,
                    "earnings_flag": ev.earnings_flag,
                    "dividend_flag": ev.dividend_flag,
                    "days_to_earnings": ev.days_to_earnings,
                }
            except Exception as exc:
                events_results[sym] = {"ok": False, "error": str(exc)}
                errors.append(f"events[{sym}]: {exc}")
    except ImportError as exc:
        events_results = {"import_error": str(exc)}
        errors.append(f"events import: {exc}")
    steps["events"] = {"ok": True, "symbols": events_results}

    # ── Step 5: Universe scan (tramite API) ───────────────────────────────────
    ok, data = _get(api_base, "/opz/universe/scan", {
        "profile": profile,
        "source": "auto",
        "regime": steps["regime"].get("regime") or "NORMAL",
        "top_n": 6,
    })
    steps["universe_scan"] = {
        "ok": ok,
        "universe_size": data.get("universe_size", 0) if ok else 0,
        "error": data.get("error") if not ok else None,
    }
    if not ok:
        errors.append(f"universe_scan: {data.get('error')}")

    # ── Step 6: Briefing ──────────────────────────────────────────────────────
    ok, data = _post(api_base, "/opz/briefing/generate", {"no_telegram": "true"})
    steps["briefing"] = {
        "ok": ok,
        "mp3_path": data.get("mp3_path") if ok else None,
        "error": data.get("error") if not ok else None,
    }
    if not ok:
        errors.append(f"briefing: {data.get('error')}")

    finished_at = datetime.now(timezone.utc).isoformat()
    return {
        "type": "morning",
        "profile": profile,
        "started_at": started_at,
        "finished_at": finished_at,
        "trading_day": is_trading_day(),
        "errors": errors,
        "ok": len(errors) == 0,
        "steps": steps,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EOD session
# ─────────────────────────────────────────────────────────────────────────────

def run_eod(profile: str = DEFAULT_PROFILE, api_base: str = DEFAULT_API_BASE) -> dict[str, Any]:
    """
    Esegue la sessione di fine giornata.
    Restituisce un dict con i risultati di ogni step.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    steps: dict[str, Any] = {}
    errors: list[str] = []

    # ── Step 1: Paper summary ─────────────────────────────────────────────────
    ok, data = _get(api_base, "/opz/paper/summary", {"profile": profile, "window_days": 60})
    steps["paper_summary"] = {
        "ok": ok,
        "trades": data.get("trades", 0) if ok else 0,
        "sharpe": data.get("sharpe_annualized") if ok else None,
        "max_dd": data.get("max_drawdown") if ok else None,
        "win_rate": data.get("win_rate") if ok else None,
        "error": data.get("error") if not ok else None,
    }
    if not ok:
        errors.append(f"paper_summary: {data.get('error')}")

    # ── Step 2: Exit candidates ───────────────────────────────────────────────
    ok, data = _get(api_base, "/opz/opportunity/exit_candidates", {"min_score": 1, "top_n": 10})
    candidates = data.get("candidates", []) if ok else []
    urgent = [c for c in candidates if c.get("exit_score", 0) >= 5]
    steps["exit_candidates"] = {
        "ok": ok,
        "total": len(candidates),
        "urgent": len(urgent),
        "urgent_symbols": [c.get("symbol") for c in urgent],
        "error": data.get("error") if not ok else None,
    }
    if not ok:
        errors.append(f"exit_candidates: {data.get('error')}")

    # ── Step 3: Regime snapshot EOD ───────────────────────────────────────────
    ok, data = _get(api_base, "/opz/regime/current", {"window": 30})
    steps["regime_eod"] = {
        "ok": ok,
        "regime": data.get("regime", "UNKNOWN") if ok else None,
    }

    # ── Step 4: System status ─────────────────────────────────────────────────
    ok, data = _get(api_base, "/opz/system/status")
    steps["system_status"] = {
        "ok": ok,
        "data_mode": data.get("data_mode") if ok else None,
        "kelly_enabled": data.get("kelly_enabled") if ok else None,
        "kill_switch_active": data.get("kill_switch_active") if ok else None,
    }

    finished_at = datetime.now(timezone.utc).isoformat()
    return {
        "type": "eod",
        "profile": profile,
        "started_at": started_at,
        "finished_at": finished_at,
        "trading_day": is_trading_day(),
        "errors": errors,
        "ok": len(errors) == 0,
        "steps": steps,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Session runner morning/EOD")
    parser.add_argument("--type", choices=["morning", "eod"], default="morning",
                        help="Tipo di sessione da eseguire")
    parser.add_argument("--profile", default=DEFAULT_PROFILE,
                        help="Profilo configurazione (dev|paper|live)")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE,
                        help="Base URL dell'API (default: http://localhost:8765)")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                        help="Formato output")
    parser.add_argument("--check-day", action="store_true",
                        help="Stampa solo se oggi è giorno di trading e termina")
    parser.add_argument("--force", action="store_true",
                        help="Esegui anche se non è giorno di trading")
    args = parser.parse_args()

    if args.check_day:
        today = date.today()
        trading = is_trading_day(today)
        result = {
            "date": today.isoformat(),
            "is_trading_day": trading,
            "weekday": today.strftime("%A"),
            "holidays_this_year": [d.isoformat() for d in sorted(nyse_holidays(today.year))],
        }
        if args.format == "json":
            print(json.dumps(result))
        else:
            status = "TRADING DAY [OK]" if trading else "NO TRADING (weekend/festivo)"
            print(f"{today.isoformat()} ({today.strftime('%A')}): {status}")
        return 0

    # Controllo giorno di trading (skip se --force)
    if not args.force and not is_trading_day():
        today = date.today()
        result = {
            "ok": True,
            "skipped": True,
            "reason": f"non è un giorno di trading NYSE ({today.isoformat()} {today.strftime('%A')})",
            "type": args.type,
        }
        if args.format == "json":
            print(json.dumps(result))
        else:
            print(f"[SKIP] {result['reason']}")
        return 0

    if args.type == "morning":
        result = run_morning(profile=args.profile, api_base=args.api_base)
    else:
        result = run_eod(profile=args.profile, api_base=args.api_base)

    if args.format == "json":
        print(json.dumps(result, default=str))
    else:
        _print_result(result)

    return 0 if result.get("ok") else 1


def _print_result(result: dict[str, Any]) -> None:
    """Output human-readable."""
    session_type = result.get("type", "?").upper()
    ok_str = "OK" if result.get("ok") else "WARN"
    skipped = result.get("skipped", False)
    print(f"\n{'='*60}")
    print(f"  SESSION {session_type} — {ok_str}")
    print(f"  Profile : {result.get('profile', '?')}")
    print(f"  Started : {result.get('started_at', '?')}")
    print(f"  Finished: {result.get('finished_at', '?')}")
    if skipped:
        print(f"  [SKIPPED] {result.get('reason')}")
        return
    print(f"{'='*60}")
    for step_name, step_data in result.get("steps", {}).items():
        if isinstance(step_data, dict):
            status = "OK" if step_data.get("ok") else "FAIL"
            err = f" → {step_data.get('error')}" if step_data.get("error") else ""
            print(f"  {status:4s}  {step_name}{err}")
    errors = result.get("errors", [])
    if errors:
        print(f"\n  Errori ({len(errors)}):")
        for e in errors:
            print(f"    · {e}")
    print()


if __name__ == "__main__":
    sys.exit(main())
