r"""QuantOptionAI — Domain 2 (D2.2)
Reconcile stub for execution DB.

PowerShell-friendly:
  py .\scripts\reconcile_execution.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from execution.reconcile import reconcile


def main() -> int:
    r = reconcile()
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r.get("ok") else 10


if __name__ == "__main__":
    raise SystemExit(main())
