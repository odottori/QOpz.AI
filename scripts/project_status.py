"""Project status aggregator (D2.41).

Single entry-point to summarize:
- repository sync status (git)
- per-phase + per-project progress (from .qoaistate.json)
- planner progress (PT targets + secondary milestones)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _import_sibling(name: str):
    """Import a sibling module when executed as 'py scripts\\*.py'."""
    return __import__(name)


def build_payload(state: dict[str, Any], *, do_fetch: bool = False) -> dict[str, Any]:
    repo_sync_status = _import_sibling("repo_sync_status")
    progress_report = _import_sibling("progress_report")

    repo = repo_sync_status.collect_sync_status(do_fetch=do_fetch)
    prog = progress_report.build_progress_payload(state)

    planner_payload: dict[str, Any] | None = None
    planner_error: str | None = None
    try:
        planner_status = _import_sibling("planner_status")
        plan_path = Path("planner/master_plan.json")
        active_path = Path("planner/active_step.json")
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
            active = json.loads(active_path.read_text(encoding="utf-8-sig")) if active_path.exists() else None
            planner_payload = planner_status.build_payload(plan=plan, state=state, active=active)
    except Exception as exc:
        planner_error = str(exc)

    return {
        "ts_utc": prog.get("ts_utc"),
        "project": prog.get("project", state.get("project", "QuantOptionAI")),
        "next_step": prog.get("next_step"),
        "repo_sync": repo,
        "progress": prog,
        "planner": planner_payload,
        "planner_error": planner_error,
    }


def to_line(payload: dict[str, Any]) -> str:
    repo_sync_status = _import_sibling("repo_sync_status")
    progress_report = _import_sibling("progress_report")
    repo_line = repo_sync_status.to_line(payload.get("repo_sync") or {})
    prog_line = progress_report.to_line(payload.get("progress") or {})

    planner = payload.get("planner") or {}
    targets = planner.get("primary_targets") or []
    done_targets = sum(1 for t in targets if t.get("is_done")) if targets else 0
    planner_line = f"PLANNER targets={done_targets}/{len(targets)} active={planner.get('active_step')}"
    return f"{repo_line} | {prog_line} | {planner_line}"


def to_markdown(payload: dict[str, Any], *, compact: bool = False) -> str:
    repo_sync_status = _import_sibling("repo_sync_status")
    progress_report = _import_sibling("progress_report")
    lines: list[str] = []
    lines.append("## REPO")
    lines.append(f"- {repo_sync_status.to_line(payload.get('repo_sync') or {})}")
    lines.append("")
    lines.append(progress_report.to_markdown(payload.get("progress") or {}, compact=compact))

    planner = payload.get("planner")
    planner_error = payload.get("planner_error")
    if isinstance(planner, dict):
        lines.append("")
        lines.append("## PLANNER")
        lines.append(f"- Active step: `{planner.get('active_step')}`")
        lines.append(f"- Lock aligned: `{planner.get('lock_matches_next_step')}`")
        lines.append("- Primary targets:")
        for t in planner.get("primary_targets", []):
            lines.append(f"  - {t['id']}: {t['done']}/{t['total']} (missing={len(t['missing'])})")
    elif planner_error:
        lines.append("")
        lines.append("## PLANNER")
        lines.append(f"- Error: `{planner_error}`")

    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="project_status")
    p.add_argument("--state", default=".qoaistate.json")
    p.add_argument("--format", choices=["json", "md", "line"], default="line")
    p.add_argument("--fetch", action="store_true", help="Run git fetch --prune (slower).")
    p.add_argument("--compact", action="store_true", help="Compact markdown output")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sp = Path(args.state)
    state = json.loads(sp.read_text(encoding="utf-8"))
    payload = build_payload(state, do_fetch=bool(args.fetch))

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.format == "md":
        print(to_markdown(payload, compact=bool(args.compact)))
    else:
        print(to_line(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
