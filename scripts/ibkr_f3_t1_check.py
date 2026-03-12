r"""Convenience wrapper for F3-T1 IBKR connectivity.

PowerShell examples:
  py scripts\ibkr_f3_t1_check.py --profile paper
  py scripts\ibkr_f3_t1_check.py --profile paper --host 127.0.0.1 --port 4002
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure repo root on sys.path when run as a script
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.f3_t1_ibkr_connectivity import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
