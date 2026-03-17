from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN_PATH = ROOT / "planner" / "master_plan.json"
DEFAULT_ACTIVE_PATH = ROOT / "planner" / "active_step.json"
DEFAULT_STATE_PATH = ROOT / ".qoaistate.json"


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    step_id: str
    scope_profile: str
    checked_files: List[str]
    violations: List[str]
    message: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _dump_json(path: Path, payload: Dict[str, Any]) -> None:
    """Scrive JSON in modo atomico (write-then-rename) per prevenire corruzione su SIGKILL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _normalize_rel_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./").strip()


def _extract_completed_step_ids(state: Dict[str, Any]) -> set[str]:
    progress = state.get("progress", {})
    raw = progress.get("steps_completed", [])
    out: set[str] = set()
    if not isinstance(raw, list):
        return out

    for item in raw:
        if isinstance(item, str):
            sid = item.strip()
            if sid:
                out.add(sid)
            continue
        if isinstance(item, dict):
            sid = item.get("id") or item.get("step")
            if isinstance(sid, str) and sid.strip():
                out.add(sid.strip())
    return out


def _state_next_step(state: Dict[str, Any]) -> Optional[str]:
    progress = state.get("progress", {})
    v = progress.get("next_step")
    if isinstance(v, str) and v.strip():
        return v.strip()
    rv = state.get("next_step")
    if isinstance(rv, str) and rv.strip():
        return rv.strip()
    return None


def _infer_scope_profile(step_id: str) -> str:
    s = (step_id or "").upper()
    if s.startswith("F1"):
        return "F1"
    if s.startswith("F2"):
        return "F2"
    if s.startswith("F3"):
        return "F3"
    if s.startswith("F4"):
        return "F4"
    if s.startswith("F5"):
        return "F5"
    if s.startswith("F6"):
        return "F6"
    if s.startswith("D2"):
        return "D2"
    return "PLAN"


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatchcase(path, _normalize_rel_path(pattern)):
            return True
    return False


def _run_git(args: Sequence[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(["git", *args], check=False, capture_output=True, text=True)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _changed_files_index() -> List[str]:
    code, out, err = _run_git(["diff", "--name-only", "--cached"])
    if code != 0:
        raise RuntimeError(err.strip() or f"git diff --cached failed with code {code}")
    return sorted({_normalize_rel_path(line) for line in out.splitlines() if line.strip()})


def _changed_files_worktree() -> List[str]:
    files: set[str] = set()

    for git_args in (["diff", "--name-only"], ["diff", "--name-only", "--cached"], ["ls-files", "--others", "--exclude-standard"]):
        code, out, err = _run_git(git_args)
        if code != 0:
            raise RuntimeError(err.strip() or f"git {' '.join(git_args)} failed with code {code}")
        for line in out.splitlines():
            if line.strip():
                files.add(_normalize_rel_path(line))
    return sorted(files)


def evaluate_guard(
    *,
    plan: Dict[str, Any],
    state: Dict[str, Any],
    active_step: Dict[str, Any],
    changed_files: List[str],
    enforce_next_step: bool = True,
) -> GuardResult:
    steps = plan.get("steps", {})
    scopes = plan.get("scope_profiles", {})
    always_allowed = [str(p) for p in plan.get("always_allowed_paths", []) if isinstance(p, str)]
    policy = plan.get("policy", {})

    step_id_raw = active_step.get("step_id")
    if not isinstance(step_id_raw, str) or not step_id_raw.strip():
        return GuardResult(
            ok=False,
            step_id="-",
            scope_profile="-",
            checked_files=changed_files,
            violations=[],
            message="active step payload missing valid step_id",
        )
    step_id = step_id_raw.strip()

    step_cfg = steps.get(step_id, {})
    if step_id not in steps:
        return GuardResult(
            ok=False,
            step_id=step_id,
            scope_profile="-",
            checked_files=changed_files,
            violations=[],
            message=f"step '{step_id}' not found in planner/master_plan.json",
        )

    completed = _extract_completed_step_ids(state)
    if step_id in completed:
        return GuardResult(
            ok=False,
            step_id=step_id,
            scope_profile="-",
            checked_files=changed_files,
            violations=[],
            message=f"active step '{step_id}' is already completed in state",
        )

    if enforce_next_step and policy.get("state_next_step_must_match_active", True):
        state_next = _state_next_step(state)
        if state_next != step_id:
            return GuardResult(
                ok=False,
                step_id=step_id,
                scope_profile="-",
                checked_files=changed_files,
                violations=[],
                message=f"state next_step mismatch: state={state_next!r} active={step_id!r}",
            )

    scope_profile = str(step_cfg.get("scope_profile") or _infer_scope_profile(step_id))
    allowed_patterns = [str(p) for p in scopes.get(scope_profile, []) if isinstance(p, str)] + always_allowed

    violations: List[str] = []
    for rel in changed_files:
        norm = _normalize_rel_path(rel)
        if not _matches_any(norm, allowed_patterns):
            violations.append(norm)

    if violations:
        return GuardResult(
            ok=False,
            step_id=step_id,
            scope_profile=scope_profile,
            checked_files=changed_files,
            violations=violations,
            message=f"scope violation: {len(violations)} file(s) outside profile {scope_profile}",
        )

    return GuardResult(
        ok=True,
        step_id=step_id,
        scope_profile=scope_profile,
        checked_files=changed_files,
        violations=[],
        message="ok",
    )


def _build_lock_payload(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "step_id": args.step_id.strip(),
        "owner": args.owner,
        "started_ts_utc": _utc_now_iso(),
        "note": args.note or "",
    }


def cmd_start(args: argparse.Namespace) -> int:
    plan = _load_json(Path(args.plan))
    step_id = args.step_id.strip()
    steps = plan.get("steps", {})
    if step_id not in steps:
        print(f"PLANNER_GUARD FAIL unknown step_id={step_id}")
        return 10

    payload = _build_lock_payload(args)
    _dump_json(Path(args.active), payload)
    print(f"PLANNER_GUARD START step={step_id} owner={args.owner}")
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    ap = Path(args.active)
    if ap.exists():
        ap.unlink()
        print("PLANNER_GUARD CLEAR removed active lock")
    else:
        print("PLANNER_GUARD CLEAR no active lock")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    ap = Path(args.active)
    active = _load_json(ap) if ap.exists() else None
    has_active = isinstance(active, dict)

    if args.format == "json":
        print(json.dumps({"has_active_step": has_active, "active_step": active}, ensure_ascii=False, indent=2))
    else:
        step = active.get("step_id") if has_active else None
        print(f"PLANNER_GUARD STATUS has_active_step={has_active} step={step}")
    return 0


def _resolve_changed_files(args: argparse.Namespace, plan: Dict[str, Any]) -> List[str]:
    if args.files:
        return sorted({_normalize_rel_path(p) for p in args.files if str(p).strip()})

    target = args.check_target
    if not target:
        policy = plan.get("policy", {})
        target = str(policy.get("default_check_target", "index"))

    if target == "index":
        return _changed_files_index()
    if target == "worktree":
        return _changed_files_worktree()
    raise ValueError(f"unsupported check target: {target}")


def cmd_check(args: argparse.Namespace) -> int:
    plan = _load_json(Path(args.plan))
    state = _load_json(Path(args.state))

    # When all targets are complete there is no active step and no scope to enforce.
    state_next = _state_next_step(state)
    if state_next == "COMPLETE":
        print("PLANNER_GUARD OK step=COMPLETE (all targets achieved, no scope restrictions)")
        return 0

    active_path = Path(args.active)
    if not active_path.exists():
        print(f"PLANNER_GUARD FAIL missing {args.active}")
        return 10
    active = _load_json(active_path)

    try:
        files = _resolve_changed_files(args, plan)
    except Exception as exc:
        print(f"PLANNER_GUARD FAIL cannot list changed files: {exc}")
        return 10

    result = evaluate_guard(
        plan=plan,
        state=state,
        active_step=active,
        changed_files=files,
        enforce_next_step=True,
    )

    if args.format == "json":
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "step_id": result.step_id,
                    "scope_profile": result.scope_profile,
                    "checked_files": result.checked_files,
                    "violations": result.violations,
                    "message": result.message,
                    "active_source": "legacy",
                    "enforce_next_step": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if result.ok:
            print(
                f"PLANNER_GUARD OK step={result.step_id} "
                f"scope={result.scope_profile} files={len(result.checked_files)} source=legacy"
            )
        else:
            print(f"PLANNER_GUARD FAIL step={result.step_id} reason={result.message} source=legacy")
            for v in result.violations[:50]:
                print(f"- {v}")
            if len(result.violations) > 50:
                print(f"... ({len(result.violations) - 50} more)")

    return 0 if result.ok else 10


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="planner_guard")
    p.add_argument("--plan", default=str(DEFAULT_PLAN_PATH))
    p.add_argument("--active", default=str(DEFAULT_ACTIVE_PATH))
    p.add_argument("--state", default=str(DEFAULT_STATE_PATH))

    sp = p.add_subparsers(dest="command", required=True)

    p_start = sp.add_parser("start")
    p_start.add_argument("--step-id", required=True)
    p_start.add_argument("--owner", default="codex")
    p_start.add_argument("--note", default="")

    sp.add_parser("clear")

    p_status = sp.add_parser("status")
    p_status.add_argument("--format", choices=["line", "json"], default="line")

    p_check = sp.add_parser("check")
    p_check.add_argument("--check-target", choices=["index", "worktree"], default=None)
    p_check.add_argument("--files", nargs="*", default=None)
    p_check.add_argument("--format", choices=["line", "json"], default="line")

    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.command == "start":
        return cmd_start(args)
    if args.command == "clear":
        return cmd_clear(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "check":
        return cmd_check(args)
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
