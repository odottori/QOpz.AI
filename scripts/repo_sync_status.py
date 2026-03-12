"""Repository sync status helper (D2.35).

Reports whether local branch is aligned with its upstream to decide if a GitHub realignment
(fetch/rebase) is recommended before continuing implementation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from typing import Callable


GitRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_git(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *cmd], check=False, capture_output=True, text=True)


def _list_remotes(run: GitRunner) -> list[str]:
    proc = run(["remote"])
    if proc.returncode != 0:
        return []
    return [r.strip() for r in (proc.stdout or "").splitlines() if r.strip()]


def _parse_ahead_behind(value: str) -> tuple[int, int]:
    parts = value.strip().split()
    if len(parts) != 2:
        raise ValueError(f"invalid ahead/behind payload: {value!r}")
    behind = int(parts[0])
    ahead = int(parts[1])
    return ahead, behind


def collect_sync_status(run: GitRunner = run_git, do_fetch: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {"ts_utc": _utc_now_iso(), "ok": True}

    branch_proc = run(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch_proc.returncode != 0:
        return {
            **payload,
            "ok": False,
            "error": "unable to determine current branch",
            "stderr": branch_proc.stderr.strip(),
        }
    payload["branch"] = branch_proc.stdout.strip()
    payload["remotes"] = _list_remotes(run)

    if do_fetch:
        fetch_proc = run(["fetch", "--prune"])
        payload["fetch_return_code"] = fetch_proc.returncode
        if fetch_proc.returncode != 0:
            payload["fetch_warning"] = (fetch_proc.stderr or "").strip()

    upstream_proc = run(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if upstream_proc.returncode != 0:
        payload.update(
            {
                "upstream": None,
                "ahead": 0,
                "behind": 0,
                "needs_realign": False,
                "push_ready": False,
                "warning": "no upstream configured for current branch",
                "push_hint": "set upstream before push: git push -u <remote> <branch>",
            }
        )
        return payload

    upstream = upstream_proc.stdout.strip()
    payload["upstream"] = upstream

    delta_proc = run(["rev-list", "--left-right", "--count", "HEAD...@{u}"])
    if delta_proc.returncode != 0:
        return {
            **payload,
            "ok": False,
            "error": "unable to compute ahead/behind",
            "stderr": delta_proc.stderr.strip(),
        }

    ahead, behind = _parse_ahead_behind(delta_proc.stdout)
    payload.update(
        {
            "ahead": ahead,
            "behind": behind,
            "needs_realign": bool(behind > 0),
            "status": "realign_recommended" if behind > 0 else "aligned_or_ahead",
            "push_ready": True,
            "push_hint": "git push",
        }
    )
    return payload


def to_line(payload: dict[str, object]) -> str:
    if not payload.get("ok"):
        return f"REPO_SYNC error: {payload.get('error')}"
    if payload.get("warning"):
        return f"REPO_SYNC warning: {payload.get('warning')}"
    return (
        f"REPO_SYNC branch={payload.get('branch')} upstream={payload.get('upstream')} "
        f"ahead={payload.get('ahead')} behind={payload.get('behind')} "
        f"needs_realign={payload.get('needs_realign')} push_ready={payload.get('push_ready')}"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="repo_sync_status")
    p.add_argument("--format", choices=["json", "line"], default="json")
    p.add_argument("--no-fetch", action="store_true", help="Skip git fetch --prune")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = collect_sync_status(do_fetch=not args.no_fetch)
    if args.format == "line":
        print(to_line(payload))
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
