from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"


def _gate_python() -> str:
    forced = os.environ.get("OPZ_GATES_PYTHON", "").strip()
    if forced:
        return forced
    if VENV_PY.exists():
        return str(VENV_PY)
    return sys.executable


def _gate_env() -> dict[str, str]:
    env = dict(os.environ)
    py_path = env.get("PYTHONPATH", "")
    prefix = str(SCRIPTS_DIR)
    env["PYTHONPATH"] = f"{prefix}{os.pathsep}{py_path}" if py_path else prefix
    return env


def run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, env=_gate_env())
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="run_gates")
    p.add_argument("--skip-planner", action="store_true")
    p.add_argument("--skip-unittest", action="store_true")
    p.add_argument("--skip-manifest", action="store_true")
    p.add_argument("--skip-certify", action="store_true")
    return p.parse_args(argv)


def _emit_output(stdout: str, stderr: str) -> None:
    if stdout.strip():
        print(stdout.rstrip())
    if stderr.strip():
        print(stderr.rstrip())


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    py_exec = _gate_python()

    stages: list[tuple[str, list[str]]] = []
    if not args.skip_planner:
        planner_cmd = [py_exec, "tools/planner_guard.py", "check", "--check-target", "index"]
        stages.append(("PLANNER_GUARD", planner_cmd))

    if not args.skip_unittest:
        stages.append(("UNITTEST", [py_exec, "-m", "unittest", "-q"]))
    if not args.skip_manifest:
        stages.append(("VERIFY_MANIFEST", [py_exec, "tools/verify_manifest.py"]))
    if not args.skip_certify:
        stages.append(("CERTIFY_STEPS", [py_exec, "tools/certify_steps.py"]))

    print(f"GATES_PYTHON {py_exec}")
    for name, cmd in stages:
        print(f"== {name} ==")
        rc, out, err = run(cmd)
        _emit_output(out, err)
        if rc != 0:
            print(f"FAIL {name} rc={rc}")
            return rc
        print(f"OK {name}")

    print("GATES OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
