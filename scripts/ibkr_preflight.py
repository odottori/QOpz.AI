from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from execution.ibkr_preflight import preflight_to_json, run_broker_preflight


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="ibkr_preflight")
    ap.add_argument("--profile", default="paper", choices=["dev", "paper", "live"])
    ap.add_argument("--probe", action="store_true", help="Run readonly broker connectivity probe")
    ap.add_argument("--timeout", type=float, default=2.0)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_broker_preflight(profile=args.profile, do_probe=args.probe, timeout_sec=args.timeout)
    print(preflight_to_json(profile=args.profile, do_probe=args.probe, timeout_sec=args.timeout))
    return 0 if payload.get("ok") else 10


if __name__ == "__main__":
    raise SystemExit(main())
