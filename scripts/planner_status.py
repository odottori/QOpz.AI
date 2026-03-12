from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN_PATH = ROOT / "planner" / "master_plan.json"
DEFAULT_STATE_PATH = ROOT / ".qoaistate.json"
DEFAULT_ACTIVE_PATH = ROOT / "planner" / "active_step.json"


@dataclass(frozen=True)
class MilestoneStatus:
    id: str
    required_steps: List[str]
    done_steps: List[str]
    missing_steps: List[str]


@dataclass(frozen=True)
class PrimaryTargetStatus:
    id: str
    required_secondary_milestones: List[str]
    done_secondary_milestones: List[str]
    missing_secondary_milestones: List[str]


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _extract_completed_step_ids(state: Dict[str, Any]) -> Set[str]:
    progress = state.get("progress", {})
    raw = progress.get("steps_completed", [])
    out: Set[str] = set()

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


def _build_milestone_status(plan: Dict[str, Any], completed: Set[str]) -> List[MilestoneStatus]:
    out: List[MilestoneStatus] = []
    for m in plan.get("secondary_milestones", []):
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id", "?"))
        required = [s for s in m.get("required_steps", []) if isinstance(s, str)]
        done = [s for s in required if s in completed]
        missing = [s for s in required if s not in completed]
        out.append(
            MilestoneStatus(
                id=mid,
                required_steps=required,
                done_steps=done,
                missing_steps=missing,
            )
        )
    return out


def _build_primary_status(plan: Dict[str, Any], milestones: List[MilestoneStatus]) -> List[PrimaryTargetStatus]:
    done_milestones = {m.id for m in milestones if len(m.required_steps) > 0 and not m.missing_steps}
    out: List[PrimaryTargetStatus] = []

    for t in plan.get("primary_targets", []):
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id", "?"))
        required = [m for m in t.get("required_secondary_milestones", []) if isinstance(m, str)]
        done = [m for m in required if m in done_milestones]
        missing = [m for m in required if m not in done_milestones]
        out.append(
            PrimaryTargetStatus(
                id=tid,
                required_secondary_milestones=required,
                done_secondary_milestones=done,
                missing_secondary_milestones=missing,
            )
        )

    return out


def build_payload(
    plan: Dict[str, Any],
    state: Dict[str, Any],
    active: Dict[str, Any] | None,
) -> Dict[str, Any]:
    completed = _extract_completed_step_ids(state)
    milestones = _build_milestone_status(plan, completed)
    primary = _build_primary_status(plan, milestones)

    next_step = state.get("progress", {}).get("next_step")
    active_step = active.get("step_id") if isinstance(active, dict) else None

    return {
        "project": plan.get("project", state.get("project", "QuantOptionAI")),
        "next_step": next_step,
        "active_step": active_step,
        "lock_matches_next_step": bool(active_step == next_step) if active_step and next_step else None,
        "secondary_milestones": [
            {
                "id": m.id,
                "done": len(m.done_steps),
                "total": len(m.required_steps),
                "missing": m.missing_steps,
                "is_done": len(m.required_steps) > 0 and not m.missing_steps,
            }
            for m in milestones
        ],
        "primary_targets": [
            {
                "id": t.id,
                "done": len(t.done_secondary_milestones),
                "total": len(t.required_secondary_milestones),
                "missing": t.missing_secondary_milestones,
                "is_done": len(t.required_secondary_milestones) > 0 and not t.missing_secondary_milestones,
            }
            for t in primary
        ],
    }


def to_markdown(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("## PLANNER STATUS")
    lines.append(f"- Project: `{payload.get('project')}`")
    lines.append(f"- Next step: `{payload.get('next_step')}`")
    lines.append(f"- Active step lock: `{payload.get('active_step')}`")
    match = payload.get("lock_matches_next_step")
    if match is not None:
        lines.append(f"- Lock aligned to next_step: `{match}`")

    lines.append("")
    lines.append("## PRIMARY TARGETS")
    lines.append("| Target | Done | Missing |")
    lines.append("|---|---:|---:|")
    for t in payload.get("primary_targets", []):
        lines.append(f"| {t['id']} | {t['done']}/{t['total']} | {len(t['missing'])} |")

    lines.append("")
    lines.append("## SECONDARY MILESTONES")
    lines.append("| Milestone | Done | Missing |")
    lines.append("|---|---:|---:|")
    for m in payload.get("secondary_milestones", []):
        lines.append(f"| {m['id']} | {m['done']}/{m['total']} | {len(m['missing'])} |")

    return "\n".join(lines)


def to_line(payload: Dict[str, Any]) -> str:
    targets = payload.get("primary_targets", [])
    done_targets = sum(1 for t in targets if t.get("is_done"))
    return (
        f"PLANNER_STATUS targets={done_targets}/{len(targets)} "
        f"next={payload.get('next_step')} active={payload.get('active_step')}"
    )


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="planner_status")
    p.add_argument("--plan", default=str(DEFAULT_PLAN_PATH))
    p.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    p.add_argument("--active", default=str(DEFAULT_ACTIVE_PATH))
    p.add_argument("--format", choices=["line", "md", "json"], default="md")
    return p.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    plan = _load_json(Path(args.plan))
    state = _load_json(Path(args.state))
    active_path = Path(args.active)
    active = _load_json(active_path) if active_path.exists() else None
    payload = build_payload(plan=plan, state=state, active=active)

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.format == "line":
        print(to_line(payload))
    else:
        print(to_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
