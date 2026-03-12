"""Project healthcheck runner (D2.19).

Provides a single command for local stability checks with explicit exit semantics.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence, Any


@dataclass
class CheckResult:
    name: str
    command: list[str]
    exit_code: int


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(cmd: Sequence[str]) -> int:
    proc = subprocess.run(list(cmd), check=False)
    return int(proc.returncode)


def _build_progress_report_command(
    *,
    progress_state: str,
    progress_compact: bool,
    progress_target_steps: int | None,
    output_format: str,
) -> list[str]:
    cmd = [
        sys.executable,
        "scripts/progress_report.py",
        "--format",
        output_format,
        "--state",
        progress_state,
    ]
    if progress_compact and output_format == "md":
        cmd.append("--compact")
    if progress_target_steps is not None:
        cmd.extend(["--project-target-steps", str(progress_target_steps)])
    return cmd


def _build_repo_sync_command(*, repo_sync_no_fetch: bool, output_format: str = "line") -> list[str]:
    cmd = [sys.executable, "scripts/repo_sync_status.py", "--format", output_format]
    if repo_sync_no_fetch:
        cmd.append("--no-fetch")
    return cmd


def build_plan(
    include_validator: bool,
    validator_profile: str,
    validator_config: str,
    include_progress_report: bool = False,
    progress_compact: bool = False,
    progress_target_steps: int | None = None,
    progress_state: str = ".qoaistate.json",
    include_repo_sync: bool = False,
    repo_sync_no_fetch: bool = False,
) -> list[tuple[str, list[str]]]:
    plan: list[tuple[str, list[str]]] = [
        ("unit_tests", [sys.executable, "-m", "unittest", "-v"]),
    ]
    if include_validator:
        plan.append(
            (
                "validator",
                [sys.executable, "validator.py", "--profile", validator_profile, "--config", validator_config],
            )
        )
    if include_progress_report:
        plan.append(
            (
                "progress_report",
                _build_progress_report_command(
                    progress_state=progress_state,
                    progress_compact=progress_compact,
                    progress_target_steps=progress_target_steps,
                    output_format="md",
                ),
            )
        )
    if include_repo_sync:
        plan.append(("repo_sync", _build_repo_sync_command(repo_sync_no_fetch=repo_sync_no_fetch, output_format="line")))
    return plan


def healthcheck(
    *,
    include_validator: bool,
    validator_profile: str,
    validator_config: str,
    include_progress_report: bool = False,
    progress_compact: bool = False,
    progress_target_steps: int | None = None,
    progress_state: str = ".qoaistate.json",
    include_repo_sync: bool = False,
    repo_sync_no_fetch: bool = False,
    runner: Callable[[Sequence[str]], int] = run_command,
) -> tuple[int, list[CheckResult]]:
    results: list[CheckResult] = []
    final_code = 0

    for name, cmd in build_plan(
        include_validator,
        validator_profile,
        validator_config,
        include_progress_report,
        progress_compact,
        progress_target_steps,
        progress_state,
        include_repo_sync,
        repo_sync_no_fetch,
    ):
        code = runner(cmd)
        results.append(CheckResult(name=name, command=list(cmd), exit_code=code))
        if code != 0:
            final_code = 10

    return final_code, results


def get_progress_snapshot(state_path: str = ".qoaistate.json", project_target_steps: int | None = None) -> dict[str, Any]:
    """Return compact phase/project advancement snapshot for operator heartbeat."""
    cmd = _build_progress_report_command(
        progress_state=state_path,
        progress_compact=False,
        progress_target_steps=project_target_steps,
        output_format="json",
    )
    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"progress_report failed with exit {proc.returncode}")

    payload = json.loads((proc.stdout or "").strip())
    project_progress = payload.get("project_progress", {})
    return {
        "next_step": payload.get("next_step"),
        "phase_completion": payload.get("phase_completion", {}),
        "current_phase": payload.get("current_phase", {}),
        "project_completion": project_progress.get("completion", {}),
        "project_target_source": project_progress.get("completion_target_source", "unknown"),
    }


def get_repo_sync_snapshot(repo_sync_no_fetch: bool = False) -> dict[str, Any]:
    cmd = _build_repo_sync_command(repo_sync_no_fetch=repo_sync_no_fetch, output_format="json")
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"repo_sync_status failed with exit {proc.returncode}")
    payload = json.loads((proc.stdout or "").strip())
    return payload


def validate_progress_snapshot_source(snapshot: dict[str, Any], expected_source: str | None) -> tuple[bool, str | None]:
    if not expected_source:
        return True, None
    actual_source = snapshot.get("project_target_source")
    if actual_source == expected_source:
        return True, None
    return False, f"progress target source mismatch: expected={expected_source} actual={actual_source}"


def validate_args(args: argparse.Namespace) -> tuple[bool, str | None]:
    if args.expected_progress_target_source and not args.include_progress_report:
        return (
            False,
            "--expected-progress-target-source requires --include-progress-report so source can be verified",
        )
    if args.fail_on_repo_behind and not args.include_repo_sync:
        return (
            False,
            "--fail-on-repo-behind requires --include-repo-sync so behind status can be evaluated",
        )
    return True, None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="healthcheck")
    p.add_argument("--include-validator", action="store_true", help="Include phase0 validator in the run")
    p.add_argument("--validator-profile", default="dev", choices=["dev", "paper", "live"])
    p.add_argument("--validator-config", default="config/dev.toml")
    p.add_argument("--include-progress-report", action="store_true", help="Include markdown progress heartbeat report")
    p.add_argument("--progress-compact", action="store_true", help="Use compact markdown heartbeat format")
    p.add_argument("--progress-target-steps", type=int, default=None, help="Override project target step count")
    p.add_argument("--progress-state", default=".qoaistate.json", help="Progress report state file path")
    p.add_argument("--include-repo-sync", action="store_true", help="Include repository sync status step")
    p.add_argument("--repo-sync-no-fetch", action="store_true", help="Skip fetch in repo-sync step")
    p.add_argument("--fail-on-repo-behind", action="store_true", help="Fail healthcheck if repo is behind upstream")
    p.add_argument(
        "--expected-progress-target-source",
        default=None,
        help="Optional guard: fail healthcheck if progress target source differs (e.g. progress.project_target_steps)",
    )
    p.add_argument("--out", default=None, help="Optional JSON output path")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args_ok, args_error = validate_args(args)
    if not args_ok:
        payload = {
            "ts_utc": _utc_now_iso(),
            "final_exit_code": 10,
            "argument_error": args_error,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 10

    code, results = healthcheck(
        include_validator=args.include_validator,
        validator_profile=args.validator_profile,
        validator_config=args.validator_config,
        include_progress_report=args.include_progress_report,
        progress_compact=args.progress_compact,
        progress_target_steps=args.progress_target_steps,
        progress_state=args.progress_state,
        include_repo_sync=args.include_repo_sync,
        repo_sync_no_fetch=args.repo_sync_no_fetch,
    )

    payload = {
        "ts_utc": _utc_now_iso(),
        "include_validator": args.include_validator,
        "include_progress_report": args.include_progress_report,
        "progress_compact": args.progress_compact,
        "progress_target_steps": args.progress_target_steps,
        "progress_state": args.progress_state,
        "include_repo_sync": args.include_repo_sync,
        "repo_sync_no_fetch": args.repo_sync_no_fetch,
        "fail_on_repo_behind": args.fail_on_repo_behind,
        "expected_progress_target_source": args.expected_progress_target_source,
        "final_exit_code": code,
        "results": [asdict(r) for r in results],
    }
    if args.include_progress_report:
        try:
            snapshot = get_progress_snapshot(
                state_path=args.progress_state,
                project_target_steps=args.progress_target_steps,
            )
            payload["progress_snapshot"] = snapshot
            ok, error = validate_progress_snapshot_source(snapshot, args.expected_progress_target_source)
            if not ok:
                payload["progress_snapshot_validation_error"] = error
                payload["final_exit_code"] = 10
        except Exception as e:
            payload["progress_snapshot_error"] = str(e)
            payload["final_exit_code"] = 10

    if args.include_repo_sync:
        try:
            repo_snapshot = get_repo_sync_snapshot(repo_sync_no_fetch=args.repo_sync_no_fetch)
            payload["repo_sync_snapshot"] = repo_snapshot
            if args.fail_on_repo_behind and (repo_snapshot.get("behind") or 0) > 0:
                payload["repo_sync_validation_error"] = (
                    f"repository behind upstream: behind={repo_snapshot.get('behind')}"
                )
                payload["final_exit_code"] = 10
        except Exception as e:
            payload["repo_sync_error"] = str(e)
            payload["final_exit_code"] = 10

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False))
    return int(payload["final_exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
