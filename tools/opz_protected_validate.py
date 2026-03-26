#!/usr/bin/env python
"""Protected pre-release validation for QOpz.AI (Windows-first).

Creates/uses an isolated venv (default: .venv_protected), then runs
planner-aware checks and gates before code release.

Usage (PowerShell):
  py tools\\opz_protected_validate.py --setup
  py tools\\opz_protected_validate.py --setup --venv-name .venv_release
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> int:
    print("+", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(ROOT), check=False, env=env)
    return int(proc.returncode)


def _venv_python(venv_name: str) -> Path:
    return ROOT / venv_name / "Scripts" / "python.exe"


def _check_vm_sync() -> tuple[bool, str]:
    base = (os.environ.get("OPZ_VM_API_BASE") or "").strip().rstrip("/")
    api_key = (os.environ.get("OPZ_API_TOKEN") or "").strip()
    if not base:
        return True, "VM_SYNC skip (OPZ_VM_API_BASE non impostato)"
    if not api_key:
        return True, "VM_SYNC skip (OPZ_API_TOKEN non impostato)"

    url = f"{base}/opz/admin/vm_update?dry_run=true"
    req = urllib.request.Request(url=url, method="POST")
    req.add_header("X-API-Key", api_key)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            ok = bool(data.get("ok"))
            return ok, f"VM_SYNC dry_run ok={ok} rc={data.get('returncode')}"
    except urllib.error.HTTPError as exc:
        return False, f"VM_SYNC HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        return False, f"VM_SYNC error: {exc}"


def _setup_env(venv_name: str, skip_pip_upgrade: bool, only: str) -> int:
    cmd = [sys.executable, "tools/opz_env_setup.py", "--venv-name", venv_name, "--only", only]
    if skip_pip_upgrade:
        cmd.append("--skip-pip-upgrade")
    return _run(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(prog="opz_protected_validate")
    ap.add_argument("--venv-name", default=".venv_protected", help="Protected venv directory name")
    ap.add_argument("--setup", action="store_true", help="Bootstrap protected venv before checks")
    ap.add_argument("--skip-pip-upgrade", action="store_true", help="Pass-through to opz_env_setup")
    ap.add_argument("--only", choices=["core", "broker", "web", "all"], default="all",
                    help="Requirements set to install when --setup is enabled")
    ap.add_argument("--skip-gates", action="store_true", help="Skip tools/run_gates.py execution")
    ap.add_argument("--skip-vm-sync", action="store_true",
                    help="Skip optional VM dry-run alignment check (uses OPZ_VM_API_BASE + OPZ_API_TOKEN)")
    ap.add_argument("--check-target", choices=["index", "worktree"], default="index",
                    help="planner_guard check target (default: index)")
    args = ap.parse_args()

    venv_name = (args.venv_name or ".venv_protected").strip() or ".venv_protected"
    if args.setup:
        rc = _setup_env(venv_name, skip_pip_upgrade=args.skip_pip_upgrade, only=args.only)
        if rc != 0:
            print(f"PROTECTED_VALIDATE FAIL env_setup rc={rc}")
            return rc

    py_exec = _venv_python(venv_name)
    if not py_exec.exists():
        print(f"PROTECTED_VALIDATE FAIL missing venv python: {py_exec}")
        print("Hint: run with --setup first.")
        return 2

    env = dict(os.environ)
    env["OPZ_GATES_PYTHON"] = str(py_exec)

    checks: list[tuple[str, list[str]]] = [
        ("REPO_SYNC", [str(py_exec), "scripts/repo_sync_status.py", "--format", "json", "--no-fetch"]),
        ("PLANNER_STATUS", [str(py_exec), "scripts/planner_status.py", "--format", "line"]),
        ("ADVANCEMENT", [str(py_exec), "scripts/advancement_matrix.py", "--format", "line"]),
        ("PLANNER_GUARD", [str(py_exec), "tools/planner_guard.py", "check", "--check-target", args.check_target]),
        ("UNITTEST_CORE", [str(py_exec), "-m", "unittest", "-v",
                           "tests.test_d2_44_planner_guard", "tests.test_d2_45_planner_status"]),
    ]

    for name, cmd in checks:
        print(f"== {name} ==")
        rc = _run(cmd, env=env)
        if rc != 0:
            print(f"PROTECTED_VALIDATE FAIL {name} rc={rc}")
            return rc
        print(f"OK {name}")

    if not args.skip_vm_sync:
        print("== VM_SYNC ==")
        ok, msg = _check_vm_sync()
        print(msg)
        if not ok:
            print("PROTECTED_VALIDATE FAIL VM_SYNC")
            return 90
        print("OK VM_SYNC")

    if not args.skip_gates:
        print("== GATES ==")
        rc = _run(
            [str(py_exec), "tools/run_gates.py", "--skip-manifest", "--skip-certify"],
            env=env,
        )
        if rc != 0:
            print(f"PROTECTED_VALIDATE FAIL GATES rc={rc}")
            return rc
        print("OK GATES")

    print(f"PROTECTED_VALIDATE OK venv={venv_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
