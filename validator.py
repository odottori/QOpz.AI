from __future__ import annotations

import platform
import sys
import os
import datetime as dt
#!/usr/bin/env python
import argparse, dataclasses, datetime as dt, hashlib, json, os, re, time
from pathlib import Path
from typing import Any, Dict, List, Callable, Optional

try:
    import tomllib
except Exception:
    tomllib = None


def _utc_tz() -> dt.tzinfo:
    """Return a UTC tzinfo compatible with Python 3.10+."""
    return getattr(dt, "UTC", dt.timezone.utc)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(_utc_tz())


@dataclasses.dataclass
class CheckResult:
    id: str
    area: str
    severity: str
    status: str
    details: str = ""

def _run_id() -> str:
    return _utc_now().strftime("%Y%m%d_%H%M%S")

def _sha256(b: bytes) -> str:
    h = hashlib.sha256(); h.update(b); return h.hexdigest()

def _load_cfg(p: Path) -> Dict[str, Any]:
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")
    if p.suffix.lower()==".toml":
        if tomllib is None:
            raise RuntimeError("Python 3.11+ required for TOML config (tomllib).")
        return tomllib.loads(p.read_text(encoding="utf-8"))
    if p.suffix.lower()==".json":
        return json.loads(p.read_text(encoding="utf-8"))
    raise RuntimeError("Unsupported config format (use .toml or .json).")

def _has_secret(text: str) -> bool:
    pats = [
        r"(?i)api[_-]?key\s*=\s*['\"][^'\"]{8,}['\"]",
        r"(?i)token\s*=\s*['\"][^'\"]{8,}['\"]",
        r"(?i)secret\s*=\s*['\"][^'\"]{8,}['\"]",
        r"(?i)password\s*=\s*['\"][^'\"]{4,}['\"]",
    ]
    return any(re.search(p, text) for p in pats)

def _md(results: List[CheckResult], run_id: str, profile: str, blocked: bool, exit_code: int) -> str:
    lines = ["# Phase 0 Validation Report",
             f"- run_id: `{run_id}`",
             f"- profile: `{profile}`",
             f"- blocked: `{blocked}`",
             f"- exit_code: `{exit_code}`",
             "",
             "| ID | Area | Severity | Status | Details |",
             "|---|---|---|---|---|"]
    for r in results:
        d = r.details.replace("\n"," ").strip()
        lines.append(f"| {r.id} | {r.area} | {r.severity} | {r.status} | {d} |")
    lines.append("")
    return "\n".join(lines)

def _exit_code(results: List[CheckResult]) -> int:
    if any(r.severity=="CRITICAL" and r.status=="FAIL" for r in results):
        return 10
    if any(r.severity=="WARNING" and r.status=="FAIL" for r in results):
        return 2
    return 0

def _sev(profile: str, live_or_paper: bool) -> str:
    # Policy requested by user:
    # dev => WARNING, paper => CRITICAL, live => CRITICAL
    if profile.lower()=="dev":
        return "WARNING"
    return "CRITICAL" if live_or_paper else "WARNING"

def _check_dirs() -> Callable[[Dict[str,Any], str], CheckResult]:
    def run(cfg, profile):
        req = ["db","data","logs","reports","config"]
        miss = [d for d in req if not Path(d).exists()]
        return CheckResult("P0-A1","BASE","CRITICAL","FAIL",f"Missing dirs: {miss}") if miss else CheckResult("P0-A1","BASE","CRITICAL","PASS","OK")
    return run

def _check_lock() -> Callable[[Dict[str,Any], str], CheckResult]:
    def run(cfg, profile):
        lock = cfg.get("phase0",{}).get("requirements_lock","requirements.lock")
        p = Path(lock)
        return CheckResult("P0-A2","BASE","CRITICAL","FAIL",f"Missing lockfile: {p}") if not p.exists() else CheckResult("P0-A2","BASE","CRITICAL","PASS",str(p))
    return run


def _import_status(module: str) -> Dict[str,str]:
    """Return dict with keys: module, present, version (if present)."""
    out = {"module": module, "present": "no", "version": ""}
    try:
        spec = __import__("importlib").util.find_spec(module)  # type: ignore[attr-defined]
        if spec is None:
            return out
        out["present"] = "yes"
        try:
            out["version"] = __import__("importlib").metadata.version(module)  # type: ignore[attr-defined]
        except Exception:
            out["version"] = ""
        return out
    except Exception:
        return out

def _check_env_deps() -> Callable[[Dict[str,Any], str], CheckResult]:
    """Environment & dependency preflight.

    Policy:
      - core deps must be present for all profiles (currently none external)
      - broker deps required only for paper/live
      - in dev, missing optional deps are SKIP (do not downgrade to FAIL)
    """
    def run(cfg, profile):
        # Python version invariant
        py = sys.version_info
        if (py.major, py.minor) < (3, 11):
            return CheckResult("P0-A4","BASE","CRITICAL","FAIL",f"Python 3.11+ required for TOML config. Detected: {py.major}.{py.minor}.{py.micro}")
        if tomllib is None:
            return CheckResult("P0-A4","BASE","CRITICAL","FAIL","tomllib not available (Python 3.11+ required).")
        sev_py = "CRITICAL"
        msg_py = f"Python detected: {py.major}.{py.minor}.{py.micro}"
        if (py.major, py.minor) < (3, 13):
            sev_py = "WARNING"
            msg_py += " | NOTE: Python 3.13 recommended for the validated runtime baseline."

        live_or_paper = profile in ("paper","live")

        required_modules: List[str] = []
        optional_modules: List[str] = []

        # broker dependency: ib_insync
        if live_or_paper:
            required_modules.append("ib_insync")
        else:
            optional_modules.append("ib_insync")

        missing_required = []
        miss_opt = []
        present = []

        for mod in required_modules:
            st = _import_status(mod)
            if st["present"] != "yes":
                missing_required.append(mod)
            else:
                present.append(f'{mod}{("=="+st["version"]) if st["version"] else ""}')

        for mod in optional_modules:
            st = _import_status(mod)
            if st["present"] != "yes":
                miss_opt.append(mod)
            else:
                present.append(f'{mod}{("=="+st["version"]) if st["version"] else ""}')

        if missing_required:
            return CheckResult("P0-A4","BASE","CRITICAL","FAIL",f"Missing required deps for profile={profile}: {missing_required}. Install: py -m pip install -r requirements-broker-ib.txt")
        # If only optional missing, keep PASS (and let downstream checks skip)
        detail = msg_py
        if present:
            detail += f" | present={present}"
        if miss_opt:
            detail += f" | optional_missing={miss_opt} (dev profile: skipped)"
        return CheckResult("P0-A4","BASE",sev_py,"PASS",detail)
    return run
def _check_secrets() -> Callable[[Dict[str,Any], str], CheckResult]:
    def run(cfg, profile):
        missing = [k for k in cfg.get("secrets",{}).get("required_env",[]) if not os.environ.get(k)]
        if missing:
            return CheckResult("P0-A5","BASE","CRITICAL","FAIL",f"Missing env vars: {missing}")
        flagged = []
        cfg_dir = Path("config")
        if cfg_dir.exists():
            for p in cfg_dir.glob("**/*"):
                if p.is_file() and p.suffix.lower() in [".toml",".json",".yml",".yaml",".env",".txt",".md"]:
                    t = p.read_text(encoding="utf-8", errors="ignore")
                    if _has_secret(t):
                        flagged.append(str(p))
        if flagged:
            return CheckResult("P0-A5","BASE","CRITICAL","FAIL",f"Possible hardcoded secrets: {flagged}")
        return CheckResult("P0-A5","BASE","CRITICAL","PASS","OK")
    return run

def _check_duckdb_schema() -> Callable[[Dict[str,Any], str], CheckResult]:
    def run(cfg, profile):
        db_path = Path(cfg.get("storage",{}).get("duckdb_path","db/quantoptionai.duckdb"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not db_path.exists():
                db_path.write_bytes(b"")
        except Exception as e:
            return CheckResult("P0-B1","STORAGE","CRITICAL","FAIL",f"DuckDB not writable: {e}")
        marker = Path("db/schema_applied.ok")
        return CheckResult("P0-B2","STORAGE","CRITICAL","FAIL","Missing db/schema_applied.ok (run scripts/init_db.py)") if not marker.exists() else CheckResult("P0-B2","STORAGE","CRITICAL","PASS","OK")
    return run

def _check_parquet_convention() -> Callable[[Dict[str,Any], str], CheckResult]:
    def run(cfg, profile):
        conv = cfg.get("storage",{}).get("parquet_convention")
        return CheckResult("P0-B3","STORAGE","WARNING","FAIL","parquet_convention not set") if conv is None else CheckResult("P0-B3","STORAGE","WARNING","PASS",f"{conv}")
    return run

def _check_synth() -> Callable[[Dict[str,Any], str], CheckResult]:
    def run(cfg, profile):
        dataset = cfg.get("dataset", {})
        seed = dataset.get("seed")
        mode = str(dataset.get("mode", "synthetic")).lower()

        if mode == "synthetic" and profile.lower() in {"paper", "live"}:
            return CheckResult(
                "P0-C1",
                "DATASET",
                "CRITICAL",
                "FAIL",
                "dataset.mode=synthetic is not allowed on paper/live (set dataset.mode to paper/live or real-historical mode)",
            )

        if seed is None:
            return CheckResult("P0-C1", "DATASET", "CRITICAL", "FAIL", "dataset.seed missing")

        import random

        random.seed(int(seed))
        smp = [random.random() for _ in range(3)]
        return CheckResult("P0-C1", "DATASET", "CRITICAL", "PASS", f"mode={mode}; sample={smp}")

    return run


def _check_dataset_mode_profile() -> Callable[[Dict[str, Any], str], CheckResult]:
    def run(cfg, profile):
        mode = str(cfg.get("dataset", {}).get("mode", "synthetic")).lower()
        prof = profile.lower()

        if prof == "dev":
            if mode != "synthetic":
                return CheckResult(
                    "P0-C2",
                    "DATASET",
                    "WARNING",
                    "FAIL",
                    f"dev profile expects dataset.mode=synthetic for engineering reproducibility (found: {mode})",
                )
            return CheckResult("P0-C2", "DATASET", "WARNING", "PASS", f"profile={prof}; mode={mode}")

        if prof == "paper" and mode != "paper":
            return CheckResult("P0-C2", "DATASET", "CRITICAL", "FAIL", f"paper profile requires dataset.mode=paper (found: {mode})")

        if prof == "live" and mode != "live":
            return CheckResult("P0-C2", "DATASET", "CRITICAL", "FAIL", f"live profile requires dataset.mode=live (found: {mode})")

        return CheckResult("P0-C2", "DATASET", "CRITICAL", "PASS", f"profile={prof}; mode={mode}")

    return run

def _ib_connect(cfg: Dict[str,Any]):
    from ib_insync import IB
    ib = IB()
    b = cfg.get("broker",{})
    host = b.get("host","127.0.0.1")
    port = int(b.get("port",7497))
    client_id = int(b.get("client_id",7))
    timeout = int(cfg.get("phase0",{}).get("ibkr_timeout_sec",10))
    ib.connect(host, port, clientId=client_id, timeout=timeout)
    return ib

def _check_ibkr_connectivity() -> Callable[[Dict[str,Any], str], CheckResult]:
    def run(cfg, profile):
        sev = _sev(profile, live_or_paper=(profile.lower() in ["paper","live"]))
        try:
            import ib_insync  # noqa: F401
        except Exception as e:
            status = "FAIL"
            live_or_paper = profile.lower() in ["paper","live"]
            if not live_or_paper:
                return CheckResult("P0-D1","BROKER",sev,"PASS",f"SKIP: ib_insync not installed (optional in dev). {e}")
            return CheckResult("P0-D1","BROKER",sev,status,f"ib_insync missing: {e}. Install: py -m pip install -r requirements-broker-ib.txt")
        # For dev: if not configured, allow warning fail; else try connect.
        try:
            ib = _ib_connect(cfg)
            # lightweight calls
            acc = ib.accountSummary()
            ib.disconnect()
            if not acc:
                return CheckResult("P0-D1","BROKER",sev,"FAIL","Connected but accountSummary empty")
            return CheckResult("P0-D1","BROKER",sev,"PASS",f"Connected; accountSummary items={len(acc)}")
        except Exception as e:
            return CheckResult("P0-D1","BROKER",sev,"FAIL",f"IBKR connectivity failed: {e}")
    return run

def _check_marketdata_options() -> Callable[[Dict[str,Any], str], CheckResult]:
    def run(cfg, profile):
        sev = _sev(profile, live_or_paper=(profile.lower() in ["paper","live"]))
        try:
            import ib_insync  # noqa: F401
            from ib_insync import Stock, Option
        except Exception as e:
            live_or_paper = profile.lower() in ["paper","live"]
            if not live_or_paper:
                return CheckResult("P0-D2","MKT_DATA",sev,"PASS",f"SKIP: ib_insync not installed (optional in dev). {e}")
            return CheckResult("P0-D2","MKT_DATA",sev,"FAIL",f"ib_insync missing: {e}. Install: py -m pip install -r requirements-broker-ib.txt")
        sym = cfg.get("phase0",{}).get("md_symbol","SPY")
        exch = cfg.get("phase0",{}).get("md_exchange","SMART")
        ccy = cfg.get("phase0",{}).get("md_currency","USD")
        right = cfg.get("phase0",{}).get("md_right","P")
        md_timeout = int(cfg.get("phase0",{}).get("md_timeout_sec",10))
        dte_min = int(cfg.get("phase0",{}).get("md_dte_min",30))
        dte_max = int(cfg.get("phase0",{}).get("md_dte_max",60))
        try:
            ib = _ib_connect(cfg)
            # Get underlying price snapshot
            stk = Stock(sym, exch, ccy)
            ib.qualifyContracts(stk)
            t = ib.reqMktData(stk, "", False, False)
            ib.sleep(1)
            px = t.marketPrice()
            ib.cancelMktData(stk)
            if px is None or px != px:
                ib.disconnect()
                return CheckResult("P0-D2","MKT_DATA",sev,"FAIL",f"Underlying market price unavailable for {sym}")
            # Option chain params
            params = ib.reqSecDefOptParams(stk.symbol, "", stk.secType, stk.conId)
            if not params:
                ib.disconnect()
                return CheckResult("P0-D2","MKT_DATA",sev,"FAIL",f"No option params for {sym}")
            p0 = params[0]
            # pick expiry in window
            expiries = sorted(list(p0.expirations))
            target_exp = None
            today = _utc_now().date()
            for ex in expiries:
                try:
                    d = dt.datetime.strptime(ex, "%Y%m%d").date()
                except Exception:
                    continue
                dte = (d - today).days
                if dte_min <= dte <= dte_max:
                    target_exp = ex
                    break
            if target_exp is None:
                target_exp = expiries[0]
            # pick strike near px
            strikes = sorted([float(s) for s in p0.strikes if s and float(s)>0])
            if not strikes:
                ib.disconnect()
                return CheckResult("P0-D2","MKT_DATA",sev,"FAIL",f"No strikes for {sym}")
            nearest = min(strikes, key=lambda s: abs(s - float(px)))
            opt = Option(sym, target_exp, nearest, right, exch)
            ib.qualifyContracts(opt)
            tick = ib.reqMktData(opt, "", False, False)
            # wait for bid/ask
            t0 = time.time()
            bid = ask = None
            while time.time() - t0 < md_timeout:
                bid = tick.bid
                ask = tick.ask
                if bid is not None and ask is not None and bid==bid and ask==ask and bid>0 and ask>0:
                    break
                ib.sleep(0.2)
            ib.cancelMktData(opt)
            ib.disconnect()
            if bid is None or ask is None or bid<=0 or ask<=0:
                return CheckResult("P0-D2","MKT_DATA",sev,"FAIL",f"Option bid/ask not received ({sym} {target_exp} {nearest}{right}) within {md_timeout}s")
            return CheckResult("P0-D2","MKT_DATA",sev,"PASS",f"Option bid/ask ok ({sym} {target_exp} {nearest}{right}) bid={bid} ask={ask}")
        except Exception as e:
            return CheckResult("P0-D2","MKT_DATA",sev,"FAIL",f"Market data check failed: {e}")
    return run

def _check_logging() -> Callable[[Dict[str,Any], str], CheckResult]:
    def run(cfg, profile):
        log_dir = Path(cfg.get("ops",{}).get("log_dir","logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            (log_dir/"phase0_smoke.jsonl").write_text('{"event":"phase0"}\n', encoding="utf-8")
        except Exception as e:
            return CheckResult("P0-E1","OPS","CRITICAL","FAIL",f"logs not writable: {e}")
        days = cfg.get("ops",{}).get("log_rotation_days")
        if days is None:
            return CheckResult("P0-E1","OPS","WARNING","FAIL","ops.log_rotation_days not set")
        return CheckResult("P0-E1","OPS","CRITICAL","PASS",f"rotation_days={days}")
    return run

def _check_killswitch() -> Callable[[Dict[str,Any], str], CheckResult]:
    def run(cfg, profile):
        ks = cfg.get("ops",{}).get("kill_switch",{})
        if not ks:
            return CheckResult("P0-E2","OPS","CRITICAL","FAIL","ops.kill_switch missing")
        fpath = Path(ks.get("manual_trigger_file","ops/kill_switch.trigger"))
        fpath.parent.mkdir(parents=True, exist_ok=True)
        return CheckResult("P0-E2","OPS","CRITICAL","PASS",f"file={fpath}")
    return run

def checklist() -> List[Callable[[Dict[str,Any], str], CheckResult]]:
    return [
        _check_dirs(),
        _check_lock(),
        _check_env_deps(),
        _check_secrets(),
        _check_duckdb_schema(),
        _check_parquet_convention(),
        _check_synth(),
        _check_dataset_mode_profile(),
        _check_ibkr_connectivity(),
        _check_marketdata_options(),
        _check_logging(),
        _check_killswitch(),
    ]

def emit(run_id: str, profile: str, blocked: bool, exit_code: int, results: List[CheckResult], execution_mode: str, fail_fast_reason: str = ""):
    rep_dir = Path("reports"); rep_dir.mkdir(parents=True, exist_ok=True)

    def _as_row(r: CheckResult) -> Dict[str, Any]:
        # Preserve existing fields for backward compatibility.
        base = dataclasses.asdict(r)
        # Report hygiene: separate the "impact if fail" from the effective severity.
        base["severity_on_fail"] = base.get("severity", "")
        base["severity_effective"] = "" if base.get("status") == "PASS" else base.get("severity", "")
        return base

    payload: Dict[str, Any] = {
        "run_id": run_id,
        "profile": profile,
        "blocked": blocked,
        "exit_code": exit_code,
        "generated_at_utc": _utc_now().isoformat(),
        "results_count": len(results),
        "execution_mode": execution_mode,
        "fail_fast_reason": fail_fast_reason,
        "results": [_as_row(r) for r in results],
    }

    jb = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    (rep_dir / f"phase0_validation_{run_id}.json").write_bytes(jb)
    (rep_dir / f"phase0_validation_{run_id}.md").write_text(_md(results, run_id, profile, blocked, exit_code), encoding="utf-8")
    (rep_dir / f"phase0_validation_{run_id}.sha256").write_text(_sha256(jb), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="QuantOptionAI Phase 0 validator (Gate 0)")
    ap.add_argument("--profile", required=True, choices=["dev","paper","live"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--capital", type=float, default=None)
    args = ap.parse_args()

    run_id = _run_id()
    try:
        cfg = _load_cfg(Path(args.config))
    except Exception as e:
        res = [CheckResult("P0-A3","BASE","CRITICAL","FAIL",str(e))]
        emit(run_id,args.profile,True,10,res,execution_mode="fail_fast_critical",fail_fast_reason="P0-A3")
        return 10

    results: List[CheckResult] = []
    blocked = False
    fail_fast_reason = ""
    for chk in checklist():
        r = chk(cfg, args.profile)
        results.append(r)
        if r.severity == "CRITICAL" and r.status == "FAIL":
            blocked = True
            fail_fast_reason = r.id
            break

    if blocked:
        # Classify the fail-fast mode for clearer operator/audit reporting.
        if fail_fast_reason == "P0-A4" and results and "Missing required deps" in results[-1].details:
            execution_mode = "fail_fast_deps"
        else:
            execution_mode = "fail_fast_critical"
        code = 10
    else:
        execution_mode = "full"
        code = _exit_code(results)

    emit(run_id, args.profile, blocked, code, results, execution_mode=execution_mode, fail_fast_reason=fail_fast_reason)
    return code

if __name__=="__main__":
    raise SystemExit(main())
