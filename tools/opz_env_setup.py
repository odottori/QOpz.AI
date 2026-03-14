#!/usr/bin/env python
"""OPZ environment setup (Windows-first, idempotent).

Creates .venv in repo root and installs requirements files if present.

Usage (PowerShell):
  py tools\opz_env_setup.py
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    # tools/ -> repo root
    return Path(__file__).resolve().parents[1]


def _venv_python(root: Path) -> Path:
    return root / ".venv" / "Scripts" / "python.exe"


def _run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(cwd))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-pip-upgrade", action="store_true", help="Do not upgrade pip")
    ap.add_argument("--only", choices=["core", "broker", "web", "all"], default="all",
                    help="Which requirements to install (default: all)")
    args = ap.parse_args()

    root = _repo_root()
    venv_dir = root / ".venv"
    py_exe = _venv_python(root)

    if not py_exe.exists():
        print(f"OPZ_ENV: creating venv at {venv_dir}")
        _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=root)
    else:
        print(f"OPZ_ENV: venv already exists at {venv_dir}")

    if not py_exe.exists():
        print("OPZ_ENV: CRITICAL_FAIL could not find venv python:", py_exe)
        return 2

    if not args.skip_pip_upgrade:
        _run([str(py_exe), "-m", "pip", "install", "-U", "pip"], cwd=root)

    req_map = {
        "core": ["requirements-core.txt", "requirements-dev.txt"],
        "broker": ["requirements-broker-ib.txt"],
        "web": ["requirements-web.txt"],
        "all": ["requirements-core.txt", "requirements-dev.txt", "requirements-broker-ib.txt", "requirements-web.txt"],
    }

    installed_any = False
    for req in req_map[args.only]:
        p = root / req
        if p.exists():
            _run([str(py_exe), "-m", "pip", "install", "-r", str(p)], cwd=root)
            installed_any = True
        else:
            print(f"OPZ_ENV: skip missing {req}")

    if not installed_any:
        print("OPZ_ENV: NOTE no requirements files found; venv created only.")

    print("OPZ_ENV: OK")
    print("HINT: activate with: .\\OPZ_ENV_ACTIVATE.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
