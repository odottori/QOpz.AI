#!/usr/bin/env python
"""OPZ environment setup (Windows-first, idempotent).

Creates .venv in repo root and installs requirements files if present.

Usage (PowerShell):
  py tools\\opz_env_setup.py
"""
from __future__ import annotations

import argparse
import os
import subprocess
import shutil
import sys
from pathlib import Path


def _repo_root() -> Path:
    # tools/ -> repo root
    return Path(__file__).resolve().parents[1]


def _venv_python(root: Path, venv_name: str) -> Path:
    return root / venv_name / "Scripts" / "python.exe"


def _run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(cwd))


def _has_pip(py_exe: Path, cwd: Path) -> bool:
    proc = subprocess.run(
        [str(py_exe), "-m", "pip", "--version"],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-pip-upgrade", action="store_true", help="Do not upgrade pip")
    ap.add_argument("--only", choices=["core", "broker", "web", "all"], default="all",
                    help="Which requirements to install (default: all)")
    ap.add_argument("--venv-name", default=".venv", help="Virtual environment directory name (default: .venv)")
    args = ap.parse_args()

    root = _repo_root()
    venv_name = (args.venv_name or ".venv").strip()
    if not venv_name:
        venv_name = ".venv"
    venv_dir = root / venv_name
    py_exe = _venv_python(root, venv_name)

    if not py_exe.exists():
        print(f"OPZ_ENV: creating venv at {venv_dir}")
        proc = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print("OPZ_ENV: WARN venv creation returned non-zero")
            if proc.stdout.strip():
                print(proc.stdout.strip())
            if proc.stderr.strip():
                print(proc.stderr.strip())
    else:
        print(f"OPZ_ENV: venv already exists at {venv_dir}")

    if not py_exe.exists():
        print("OPZ_ENV: CRITICAL_FAIL could not find venv python:", py_exe)
        return 2

    if not _has_pip(py_exe, root):
        fallback = root / ".venv"
        fallback_py = fallback / "Scripts" / "python.exe"
        if venv_name != ".venv" and fallback_py.exists() and _has_pip(fallback_py, root):
            print(f"OPZ_ENV: WARN pip missing in {venv_name}, cloning from {fallback.name}")
            if venv_dir.exists():
                shutil.rmtree(venv_dir, ignore_errors=True)
            shutil.copytree(fallback, venv_dir)
            if not _has_pip(py_exe, root):
                print("OPZ_ENV: CRITICAL_FAIL pip missing after fallback clone")
                return 3
        else:
            print("OPZ_ENV: CRITICAL_FAIL pip not available in selected venv and no fallback source")
            return 3

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
    print(f"HINT: activate with: {venv_name}\\Scripts\\activate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
