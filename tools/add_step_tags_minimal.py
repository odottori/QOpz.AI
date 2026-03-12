#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""tools/add_step_tags_minimal.py

Idempotent helper to add minimal step tags to implementation modules.

Safety:
- Adds only a single comment line near the top of target files.
- No functional code changes.

Usage:
  py tools\add_step_tags_minimal.py
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

# Do NOT embed step-like tokens here; store as (prefix, number) pairs.
TARGETS: List[Tuple[str, List[Tuple[str, int]]]] = [
    ("scripts/submit_order.py", [("D2", 18), ("D2", 22)]),
    ("validator.py", [("D2", 20), ("D2", 21)]),

    # Progress report evolution
    ("scripts/progress_report.py", [("D2", 23), ("D2", 24), ("D2", 25), ("D2", 26), ("D2", 29), ("D2", 31), ("D2", 32)]),

    # Healthcheck evolution (progress + repo sync integration)
    ("scripts/healthcheck.py", [("D2", 27), ("D2", 28), ("D2", 30), ("D2", 33), ("D2", 34), ("D2", 36)]),

    # Repo sync status
    ("scripts/repo_sync_status.py", [("D2", 35), ("D2", 37)]),
]

MARKER = "# STEP_TAGS: "


def _fmt(prefix: str, n: int) -> str:
    return f"{prefix}.{int(n)}"


def _insert_tags(path: Path, tags: List[Tuple[str, int]]) -> bool:
    if not path.exists():
        print(f"SKIP: missing {path}")
        return False

    txt = path.read_text(encoding="utf-8", errors="replace")

    dot_tags = [_fmt(p, n) for (p, n) in tags]

    # idempotent: all present => no-op
    if all(t in txt for t in dot_tags):
        print(f"OK: already tagged {path}")
        return False

    lines = txt.splitlines(True)
    out: List[str] = []
    idx = 0

    if idx < len(lines) and lines[idx].startswith("#!"):
        out.append(lines[idx]); idx += 1
    for _ in range(2):
        if idx < len(lines) and "coding" in lines[idx]:
            out.append(lines[idx]); idx += 1
            break

    out.append(MARKER + ", ".join(dot_tags) + "\n")
    out.extend(lines[idx:])

    new_txt = "".join(out).replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(new_txt, encoding="utf-8", newline="\n")
    print(f"PATCHED: {path} (+{', '.join(dot_tags)})")
    return True


def main() -> int:
    changed = False
    for rel, tags in TARGETS:
        changed = _insert_tags(REPO_ROOT / rel, tags) or changed
    print("DONE" + (" (changed)" if changed else " (no changes)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
