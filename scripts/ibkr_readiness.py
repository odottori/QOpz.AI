from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.ibkr_readiness import run_ibkr_readiness, readiness_to_json


EXIT_OK = 0
EXIT_FAILURE = 10


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="IBKR readiness probe (read-only)")
    p.add_argument("--profile", default="paper")
    p.add_argument("--timeout", type=float, default=2.0)
    p.add_argument("--account", default=None)
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--no-option-chain", action="store_true")
    return p



def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    payload_dict = run_ibkr_readiness(
        profile=args.profile,
        timeout_sec=args.timeout,
        account=args.account,
        symbol=args.symbol,
        include_option_chain=not bool(args.no_option_chain),
    )
    print(
        readiness_to_json(
            profile=args.profile,
            timeout_sec=args.timeout,
            account=args.account,
            symbol=args.symbol,
            include_option_chain=not bool(args.no_option_chain),
        )
    )
    return EXIT_OK if bool(payload_dict.get("ok")) else EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
