from __future__ import annotations

import argparse
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


def wait_for_http(url: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2.0) as response:
                status = int(getattr(response, "status", 0))
                if 200 <= status < 400:
                    return True
        except URLError:
            pass
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--label", default="service")
    args = parser.parse_args()

    ok = wait_for_http(args.url, args.timeout)
    if ok:
        print(f"LAUNCHER_OK {args.label} url={args.url}")
        return 0
    print(f"LAUNCHER_FAIL {args.label} url={args.url}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
