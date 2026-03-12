#!/usr/bin/env python
"""OPZ F3-T2 runner entrypoint (human-confirmed wrapper called by OPZ_F3_T2_RUN.bat)."""
from __future__ import annotations

import os
import sys


def _bootstrap_repo_root() -> None:
    here = os.path.abspath(os.path.dirname(__file__))
    repo_root = os.path.abspath(os.path.join(here, os.pardir))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


_bootstrap_repo_root()

from tools.opz_f3_t2_runner import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
