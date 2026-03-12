from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Callable

GitRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


DESIRED = {
    "core.autocrlf": "true",
    "core.safecrlf": "false",
    "core.eol": "crlf",
}


def _default_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *cmd], check=False, capture_output=True, text=True)


def _in_git_repo() -> bool:
    return Path(".git").exists()


def get_config(run: GitRunner = _default_run) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for k in DESIRED:
        cp = run(["config", "--local", "--get", k])
        val = (cp.stdout or "").strip() if cp.returncode == 0 else None
        out[k] = val if val != "" else None
    return out


def enforce(run: GitRunner = _default_run) -> dict[str, str | None]:
    # Apply desired settings locally
    for k, v in DESIRED.items():
        run(["config", "--local", k, v])
    return get_config(run=run)


def _compliant(current: dict[str, str | None]) -> bool:
    for k, v in DESIRED.items():
        if (current.get(k) or "").lower() != v.lower():
            return False
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="git_eol_policy")
    p.add_argument("--format", choices=["line", "json"], default="line")
    p.add_argument("--apply", action="store_true", help="Apply desired EOL policy to repo-local git config.")
    p.add_argument("--check-only", action="store_true", help="Only check policy; exit 20 if drift.")
    p.add_argument("--no-git-ok", action="store_true", help="If not a git repo, exit 0 (default).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not _in_git_repo():
        if args.format == "json":
            print(json.dumps({"ok": True, "skipped": True, "reason": "not a git repo"}, indent=2, sort_keys=True))
        else:
            print("GIT_EOL SKIP not-a-git-repo")
        return 0 if args.no_git_ok or True else 2

    current = get_config()

    if args.apply and not _compliant(current):
        current = enforce()

    ok = _compliant(current)

    payload = {
        "ok": ok,
        "desired": DESIRED,
        "current": current,
    }

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if ok:
            print(f"GIT_EOL OK autocrlf={current.get('core.autocrlf')} safecrlf={current.get('core.safecrlf')} eol={current.get('core.eol')}")
        else:
            print(f"GIT_EOL DRIFT autocrlf={current.get('core.autocrlf')} safecrlf={current.get('core.safecrlf')} eol={current.get('core.eol')}")
            if not args.apply:
                print("Hint: run python scripts/git_eol_policy.py --apply")
    if args.check_only and not ok:
        return 20
    return 0 if ok else 20


if __name__ == "__main__":
    raise SystemExit(main())
