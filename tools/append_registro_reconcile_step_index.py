#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""tools/append_registro_reconcile_step_index.py

Append a single, idempotent entry to .canonici/REGISTRO_INTEGRITA.md documenting
the step-index reconciliation (state vs certification report).

- No manual editing required.
- Safe on Windows (forces LF).
- Idempotent via a marker.

Usage (PowerShell):
  py tools\append_registro_reconcile_step_index.py
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
REG_PATH = REPO_ROOT / ".canonici" / "REGISTRO_INTEGRITA.md"
STATE_PATH = REPO_ROOT / ".qoaistate.json"

MARKER = "<!-- QOAI_STEP_RECONCILE_D2_66 -->"

# Canonical summaries (human-readable)
UNVERIFIED_SUMMARY = "D2.38–D2.59, D2.61"
BACKFILL_SUMMARY = "D2.1–D2.3, D2.11–D2.14, F4.3"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(cmd: List[str]) -> Optional[str]:
    try:
        r = subprocess.run(["git", *cmd], cwd=str(REPO_ROOT), capture_output=True, text=True)
        if r.returncode != 0:
            return None
        return (r.stdout or "").strip() or None
    except Exception:
        return None


def _read_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _extract_steps(arr: Any) -> List[str]:
    out: List[str] = []
    if not isinstance(arr, list):
        return out
    for e in arr:
        if isinstance(e, str):
            s = e.strip()
        elif isinstance(e, dict):
            s = str(e.get("step") or e.get("id") or "").strip()
        else:
            s = ""
        if s:
            out.append(s)
    return out


def main() -> int:
    if not REG_PATH.exists():
        raise SystemExit(f"FAIL: missing {REG_PATH}")

    reg_txt = REG_PATH.read_text(encoding="utf-8", errors="replace")
    if MARKER in reg_txt:
        print("OK: registro already contains reconciliation entry (marker present).")
        return 0

    branch = _git(["branch", "--show-current"]) or "unknown"
    commit = _git(["rev-parse", "--short", "HEAD"]) or "unknown"

    st = _read_state()
    prog = st.get("progress", {}) if isinstance(st, dict) else {}
    unverified = _extract_steps(prog.get("unverified_completed"))

    unverified_note = UNVERIFIED_SUMMARY if unverified else UNVERIFIED_SUMMARY + " (unverified list not found in state)"
    backfill_note = BACKFILL_SUMMARY

    entry = f"""\n{MARKER}
## Step-index reconciliation (repo-centrica) · {_utc_now()}
- git: {branch}@{commit}
- azione: riallineato `.qoaistate.json` al report `reports/step_certification.md`
- esito:
  - spostati in `progress.unverified_completed`: {unverified_note}
  - backfill in `progress.steps_completed`: {backfill_note}
- nota: label/milestone (es. D2.NORM, F4.1.HF1) non sono step canonici e non entrano nel conteggio GAP
"""

    new_txt = reg_txt.rstrip() + entry + "\n"
    new_txt = new_txt.replace("\r\n", "\n").replace("\r", "\n")
    REG_PATH.write_text(new_txt, encoding="utf-8", newline="\n")
    print("OK: appended reconciliation entry to REGISTRO_INTEGRITA.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
