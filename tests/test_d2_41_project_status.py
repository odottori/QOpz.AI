from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(args: list[str]) -> str:
    proc = subprocess.run(args, check=True, capture_output=True, text=True)
    return (proc.stdout or "").strip()


def test_project_status_line_smoke() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "project_status.py"
    out = _run([sys.executable, str(script), "--format", "line"])
    assert "REPO_SYNC" in out
    assert "PER FASI(plan)" in out
    assert "PER TRACK D2" in out


def test_project_status_md_smoke() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "project_status.py"
    out = _run([sys.executable, str(script), "--format", "md"])
    assert "## REPO" in out
    assert "## PER FASI (piano canonico)" in out
    assert "## PER TRACK D2" in out
