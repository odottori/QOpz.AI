"""
quick_audit.py — Audit rapido dei moduli critici di QOpz.AI

Esegue un set di check automatici (AST + regex) sui file di execution e strategy
per rilevare pattern problematici noti: bare except, datetime naive, globals non
thread-safe, mancanza di Kelly gate, mancanza di provenance fields.

Uso:
    python scripts/quick_audit.py
    python scripts/quick_audit.py --module execution/state_machine.py
    python scripts/quick_audit.py --severity CRITICAL

Exit codes:
    0  = nessun CRITICAL
    10 = almeno un CRITICAL trovato
"""

import ast
import re
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent

SEVERITY = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]

PRIORITY_MODULES = [
    "execution/state_machine.py",
    "execution/boundary_adapter.py",
    "execution/storage.py",
    "execution/paper_metrics.py",
    "execution/reconcile.py",
    "execution/order_reducer.py",
    "execution/client_id.py",
    "execution/ack_taxonomy.py",
    "execution/config_loader.py",
    "execution/dry_run_adapter.py",
    "execution/providers/router.py",
    "execution/providers/external_delayed_provider.py",
    "execution/providers/_row_utils.py",
    "strategy/scoring.py",
    "api/opz_api.py",
]


@dataclass
class Issue:
    severity: str
    file: str
    line: int
    category: str
    message: str
    suggestion: str


@dataclass
class AuditResult:
    file: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(i.severity == "CRITICAL" for i in self.issues)

    @property
    def status(self) -> str:
        if not self.issues:
            return "PASS"
        if self.has_critical:
            return "FAIL"
        if any(i.severity == "HIGH" for i in self.issues):
            return "WARN"
        return "INFO"


# ──────────────────────────────────────────────
# Check functions (regex-based, fast)
# ──────────────────────────────────────────────

def check_bare_except_pass(src: str, filepath: str) -> list[Issue]:
    issues = []
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if re.match(r"except\s*Exception\s*:", stripped) or stripped == "except:":
            # Intentional broad catch marked with an inline explanation comment
            comment = re.search(r"#\s*(.+)", stripped)
            if comment and re.search(r"safe to ignore|already exists|best.effort|do not propagate", comment.group(1), re.I):
                continue
            issues.append(Issue(
                severity="HIGH",
                file=filepath,
                line=i,
                category="Exception handling",
                message=f"Bare/broad except found: `{stripped}`",
                suggestion="Use specific exception types; log before pass"
            ))
    return issues


def check_naive_datetime(src: str, filepath: str) -> list[Issue]:
    issues = []
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        # datetime.now() without tz argument
        if re.search(r"datetime\.now\s*\(\s*\)", stripped):
            issues.append(Issue(
                severity="CRITICAL",
                file=filepath,
                line=i,
                category="Timezone",
                message="datetime.now() produces naive datetime (no timezone)",
                suggestion="Use datetime.now(tz=timezone.utc)"
            ))
        # .replace(tzinfo=...) on potentially aware datetime
        if re.search(r"\.replace\s*\(\s*tzinfo\s*=\s*timezone\.utc\s*\)", stripped):
            lines_list = src.splitlines()
            # Check current line AND the previous 3 lines for an "if ... is None:" guard
            context_before = "\n".join(lines_list[max(0, i - 4):i])
            on_same_line = "if" in stripped.lower() and "none" in stripped.lower()
            guarded = on_same_line or re.search(r"if\b.+\btzinfo\b.+\bNone\b", context_before, re.I)
            if not guarded:
                issues.append(Issue(
                    severity="HIGH",
                    file=filepath,
                    line=i,
                    category="Timezone",
                    message=".replace(tzinfo=timezone.utc) may corrupt already-aware datetimes",
                    suggestion="Check tzinfo is None before replacing; use .astimezone(timezone.utc) for aware DTs"
                ))
    return issues


def check_thread_unsafe_globals(src: str, filepath: str) -> list[Issue]:
    issues = []
    # Look for global mutable state modified without lock.
    # Skip if the file already imports threading AND uses a lock variable for the mutation.
    has_lock = "threading.Lock()" in src or "threading.RLock()" in src
    dangerous_patterns = [
        (r"^_SCHEMA_READY\s*=\s*True", "CRITICAL", "_SCHEMA_READY set without threading.Lock"),
        (r"^_counter\s*[+\-]=", "CRITICAL", "_counter mutated without threading.Lock"),
        (r"_TTS_FALLBACK.*=", "HIGH", "TTS global state mutated — not thread-safe in FastAPI"),
    ]
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        line_indent = len(line) - len(line.lstrip())
        for pattern, severity, message in dangerous_patterns:
            if re.search(pattern, stripped):
                # Skip module-level declarations/initializations (indent == 0 and not inside a function)
                if line_indent == 0:
                    continue
                # Context-aware: find the enclosing function body and check if it contains a lock
                # Walk backwards to find 'def ' that starts the current function
                func_start = 0
                for j in range(i - 2, -1, -1):
                    if re.match(r"def\s+\w+", lines[j].strip()):
                        func_start = j
                        break
                func_body = "\n".join(lines[func_start:i])
                if has_lock and re.search(r"with\s+\w*[Ll][Oo][Cc][Kk]", func_body):
                    continue  # mutation is inside a lock block — safe
                issues.append(Issue(
                    severity=severity,
                    file=filepath,
                    line=i,
                    category="Thread safety",
                    message=message,
                    suggestion="Use threading.Lock() or threading.local() to protect mutable globals"
                ))
    return issues


def check_run_id_filter(src: str, filepath: str) -> list[Issue]:
    issues = []
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        # if run_id: without strip check
        if re.match(r"if\s+run_id\s*:", stripped) or re.match(r"if\s+run_id\s+and\s+not\s+run_id\.", stripped):
            issues.append(Issue(
                severity="MEDIUM",
                file=filepath,
                line=i,
                category="Data integrity",
                message="if run_id: does not handle empty string case",
                suggestion="Use: if run_id and run_id.strip():"
            ))
    return issues


def check_tomllib_none_guard(src: str, filepath: str) -> list[Issue]:
    issues = []
    lines = src.splitlines()
    has_tomllib_fallback = any("tomllib = None" in l for l in lines)
    if not has_tomllib_fallback:
        return issues
    for i, line in enumerate(lines, 1):
        if "tomllib.loads(" in line or "tomllib.load(" in line:
            # Check if there's a guard somewhere before this call
            issues.append(Issue(
                severity="HIGH",
                file=filepath,
                line=i,
                category="Import",
                message="tomllib.loads() called but tomllib may be None (fallback not guarded)",
                suggestion="Add: if tomllib is None: raise RuntimeError('tomllib not available')"
            ))
            break
    return issues


def check_kelly_gate(src: str, filepath: str) -> list[Issue]:
    issues = []
    if "kelly" not in src.lower():
        return issues
    # Check that Kelly calls/definitions have DATA_MODE guard.
    # Skip function definitions (def kelly_fractional) — the guard lives inside the function body.
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.search(r"kelly_fractional\s*\(", stripped):
            # Skip: this is a function definition
            if stripped.startswith("def kelly_fractional"):
                continue
            # Skip: this is a comment or string
            if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                continue
            # Look for DATA_MODE check in nearby lines (10 lines before — wider context)
            context = "\n".join(lines[max(0, i - 10):i + 2])
            if "VENDOR_REAL_CHAIN" not in context and "DATA_MODE" not in context and "_data_mode" not in context:
                issues.append(Issue(
                    severity="CRITICAL",
                    file=filepath,
                    line=i,
                    category="Kelly gate",
                    message="kelly_fractional() called without visible DATA_MODE guard",
                    suggestion="Ensure DATA_MODE == 'VENDOR_REAL_CHAIN' AND N_closed_trades >= 50"
                ))
    return issues


def check_duckdb_connection_leak(src: str, filepath: str) -> list[Issue]:
    issues = []
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.search(r"=\s*_connect\s*\(\s*\)|=\s*duckdb\.connect\s*\(", stripped):
            # Skip if it's inside a with-statement on the same line
            if re.match(r"with\s+", stripped):
                continue
            # Scan forward to next top-level function/class def (same or less indentation)
            # to stay within the enclosing function body
            call_indent = len(line) - len(line.lstrip())
            end = len(lines)
            for j in range(i, len(lines)):
                jline = lines[j]
                if not jline.strip():
                    continue
                jind = len(jline) - len(jline.lstrip())
                if jind <= call_indent and re.match(r"(def |class |\@)", jline.strip()):
                    end = j
                    break
            func_body = "\n".join(lines[i:end])
            if "finally:" not in func_body and "con.close()" not in func_body:
                issues.append(Issue(
                    severity="HIGH",
                    file=filepath,
                    line=i,
                    category="Resource leak",
                    message="DuckDB connection opened without try/finally or context manager",
                    suggestion="Wrap in try/finally: con.close() or use context manager"
                ))
    return issues


def check_provenance_fields(src: str, filepath: str) -> list[Issue]:
    """Check that files with INSERT statements include the mandatory provenance watermark fields.

    run_id is required for execution tables (orders, order_events) but optional for observation
    tables (paper_metrics, compliance, opportunity_decisions) which use their own IDs.
    The four cross-table required fields are: source_system, source_mode, asof_ts, received_ts.
    """
    issues = []
    if "INSERT INTO" not in src.upper() and "insert into" not in src:
        return issues
    required_fields = ["source_mode", "source_system", "asof_ts", "received_ts"]
    missing = [f for f in required_fields if f not in src]
    if missing:
        issues.append(Issue(
            severity="MEDIUM",
            file=filepath,
            line=0,
            category="Data provenance",
            message=f"File contains INSERT but may lack provenance fields: {missing}",
            suggestion="Every DB insert must include: source_system, source_mode, source_quality, asof_ts, received_ts (+ run_id for execution tables)"
        ))
    return issues


# ──────────────────────────────────────────────
# Main audit runner
# ──────────────────────────────────────────────

CHECKS = [
    check_bare_except_pass,
    check_naive_datetime,
    check_thread_unsafe_globals,
    check_run_id_filter,
    check_tomllib_none_guard,
    check_kelly_gate,
    check_duckdb_connection_leak,
    check_provenance_fields,
]


def audit_file(path: Path) -> AuditResult:
    result = AuditResult(file=str(path.relative_to(ROOT)))
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        result.issues.append(Issue("HIGH", str(path), 0, "IO", f"Cannot read file: {e}", "Check file permissions"))
        return result

    for check in CHECKS:
        result.issues.extend(check(src, result.file))

    return result


def print_result(result: AuditResult, min_severity: str = "LOW") -> None:
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    min_level = sev_order.get(min_severity, 3)

    filtered = [i for i in result.issues if sev_order.get(i.severity, 3) <= min_level]
    if not filtered and result.status == "PASS":
        print(f"  ✅ {result.file}  — PASS (no issues)")
        return

    status_icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "INFO": "ℹ️"}.get(result.status, "?")
    print(f"\n{status_icon} {result.file}  [{result.status}]")
    if not filtered:
        print("   (no issues at this severity level)")
        return

    for issue in sorted(filtered, key=lambda x: sev_order.get(x.severity, 3)):
        icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}.get(issue.severity, "⚪")
        line_ref = f":{issue.line}" if issue.line > 0 else ""
        print(f"   {icon} [{issue.severity}] line{line_ref} | {issue.category}")
        print(f"      Problem : {issue.message}")
        print(f"      Fix     : {issue.suggestion}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Quick audit of QOpz.AI critical modules")
    parser.add_argument("--module", help="Audit a specific module (relative path from project root)")
    parser.add_argument("--severity", default="LOW", choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                        help="Minimum severity to report (default: LOW)")
    parser.add_argument("--summary", action="store_true", help="Print summary table only")
    args = parser.parse_args()

    if args.module:
        modules = [ROOT / args.module]
    else:
        modules = [ROOT / m for m in PRIORITY_MODULES if (ROOT / m).exists()]

    results = [audit_file(m) for m in modules]

    print("\n" + "="*60)
    print("QOpz.AI — Quick Audit Report")
    print("="*60)

    if args.summary:
        for r in results:
            counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
            for issue in r.issues:
                counts[issue.severity] = counts.get(issue.severity, 0) + 1
            icon = "✅" if r.status == "PASS" else ("❌" if r.has_critical else "⚠️")
            print(f"{icon} {r.file:<50} C:{counts['CRITICAL']} H:{counts['HIGH']} M:{counts['MEDIUM']} L:{counts['LOW']}")
    else:
        for r in results:
            print_result(r, args.severity)

    # Summary stats
    total_critical = sum(1 for r in results for i in r.issues if i.severity == "CRITICAL")
    total_high = sum(1 for r in results for i in r.issues if i.severity == "HIGH")
    total_medium = sum(1 for r in results for i in r.issues if i.severity == "MEDIUM")
    total_low = sum(1 for r in results for i in r.issues if i.severity == "LOW")

    print("\n" + "="*60)
    print(f"TOTALI: 🔴 CRITICAL={total_critical}  🟠 HIGH={total_high}  🟡 MEDIUM={total_medium}  🔵 LOW={total_low}")
    print(f"Moduli analizzati: {len(results)}")
    if total_critical > 0:
        print("❌ CRITICAL issues trovati — intervento richiesto prima di avanzare milestone")
    else:
        print("✅ Nessun CRITICAL — continua con HIGH/MEDIUM secondo priorità")
    print("="*60 + "\n")

    return 10 if total_critical > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
