from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
RUNTIME_ENV_UPDATES: dict[str, str] = {}


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
    env.update(RUNTIME_ENV_UPDATES)
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
    p.add_argument("--skip-preflight", action="store_true")
    return p.parse_args(argv)


def _emit_output(stdout: str, stderr: str) -> None:
    if stdout.strip():
        print(stdout.rstrip())
    if stderr.strip():
        print(stderr.rstrip())


def _probe_temp_dir(py_exec: str, temp_dir: Path) -> tuple[bool, str]:
    temp_dir.mkdir(parents=True, exist_ok=True)
    env = _gate_env()
    env["TEMP"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    cmd = [
        py_exec,
        "-c",
        (
            "import tempfile, pathlib; "
            "d = tempfile.mkdtemp(); "
            "p = pathlib.Path(d) / 'probe.txt'; "
            "p.write_text('ok', encoding='utf-8'); "
            "print(p)"
        ),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
    if proc.returncode == 0:
        return True, (proc.stdout or "").strip()
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    detail = f"{out}\n{err}".strip()
    return False, detail


def _probe_pandas(py_exec: str) -> tuple[bool, str]:
    rc, out, err = run([py_exec, "-c", "import pandas as pd; print(pd.__version__)"])
    detail = (out or err or "").strip()
    return rc == 0, detail


def _run_preflight(py_exec: str) -> tuple[bool, str]:
    lines: list[str] = []

    temp_candidates: list[Path] = []
    forced = os.environ.get("OPZ_GATES_TEMP", "").strip()
    if forced:
        temp_candidates.append(Path(forced))
    temp_candidates.extend(
        [
            ROOT / ".tmp" / "gate_temp",
            ROOT / ".tmp" / "temp",
            ROOT,
        ]
    )

    temp_ok = False
    for temp_dir in temp_candidates:
        ok, detail = _probe_temp_dir(py_exec, temp_dir)
        if ok:
            RUNTIME_ENV_UPDATES["TEMP"] = str(temp_dir)
            RUNTIME_ENV_UPDATES["TMP"] = str(temp_dir)
            lines.append(f"TEMP_OK {temp_dir}")
            temp_ok = True
            break
        lines.append(f"TEMP_FAIL {temp_dir} :: {detail}")

    if not temp_ok:
        lines.append("TEMP_FIX_REQUIRED run outside sandbox restrictions")
        return False, "\n".join(lines)

    pandas_ok, pandas_detail = _probe_pandas(py_exec)
    if pandas_ok:
        lines.append(f"PANDAS_OK {pandas_detail}")
        return True, "\n".join(lines)

    lines.append(f"PANDAS_FAIL {pandas_detail}")
    rc, out, err = run(
        [
            py_exec,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--force-reinstall",
            "pandas==3.0.1",
        ]
    )
    if rc != 0:
        lines.append("PANDAS_REINSTALL_FAIL")
        if out.strip():
            lines.append(out.strip())
        if err.strip():
            lines.append(err.strip())
        return False, "\n".join(lines)

    pandas_ok, pandas_detail = _probe_pandas(py_exec)
    if not pandas_ok:
        lines.append(f"PANDAS_STILL_FAIL {pandas_detail}")
        return False, "\n".join(lines)

    lines.append(f"PANDAS_REPAIRED {pandas_detail}")
    return True, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    py_exec = _gate_python()

    if not args.skip_preflight:
        print("== PREFLIGHT ==")
        ok, detail = _run_preflight(py_exec)
        if detail.strip():
            print(detail.rstrip())
        if not ok:
            print("FAIL PREFLIGHT rc=97")
            return 97
        print("OK PREFLIGHT")

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
