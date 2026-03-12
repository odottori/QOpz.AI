from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set


ROOT = Path(__file__).resolve().parents[1]
STEP_INDEX_PATH = ROOT / ".step_index.json"
STATE_JSON_PATH = ROOT / ".qoaistate.json"
PLAN_PATH = ROOT / "config" / "release_plan_go_nogo.json"


@dataclass(frozen=True)
class MilestoneStatus:
    id: str
    name: str
    required_steps: List[str]
    done_steps: List[str]
    missing_steps: List[str]
    is_done: bool


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _completed_step_ids(step_index: Dict[str, Any]) -> Set[str]:
    """Return the set of completed step ids from .step_index.json.

    The repo supports legacy formats where steps_completed is a list[str]
    as well as newer formats where it is a list[dict].
    """
    ids: Set[str] = set()
    for item in step_index.get("steps_completed", []):
        if isinstance(item, str):
            s = item.strip()
            if s:
                ids.add(s)
            continue
        if isinstance(item, dict):
            sid = item.get("id") or item.get("step")
            if isinstance(sid, str) and sid.strip():
                ids.add(sid.strip())
    return ids


def _blocked_steps(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    progress = state.get("progress", {})
    raw = progress.get("blocked_steps", [])
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            out.append(item)
        elif isinstance(item, str) and item.strip():
            out.append({"id": item.strip()})
    return out


def _milestone_status(m: Dict[str, Any], completed: Set[str]) -> MilestoneStatus:
    req = [s for s in m.get("required_steps", []) if isinstance(s, str)]
    done = [s for s in req if s in completed]
    missing = [s for s in req if s not in completed]
    return MilestoneStatus(
        id=m.get("id", "?"),
        name=m.get("name", "?"),
        required_steps=req,
        done_steps=done,
        missing_steps=missing,
        is_done=(len(req) > 0 and len(missing) == 0),
    )


def _fmt_md(milestones: List[MilestoneStatus], blocked: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("## RELEASE STATUS (GO/NO-GO)\n")
    lines.append("| Milestone | Done | Missing |")
    lines.append("|---|---:|---:|")
    for ms in milestones:
        lines.append(f"| {ms.id} — {ms.name} | {len(ms.done_steps)}/{len(ms.required_steps)} | {len(ms.missing_steps)} |")
    lines.append("")

    if blocked:
        lines.append("### Blocked steps")
        for b in blocked:
            sid = b.get("id", "?")
            reason = b.get("reason", "")
            ts = b.get("ts_utc", "")
            suffix = ""
            if reason:
                suffix += f" — {reason}"
            if ts:
                suffix += f" ({ts})"
            lines.append(f"- {sid}{suffix}".rstrip())
        lines.append("")
    return "\n".join(lines)


def _fmt_line(milestones: List[MilestoneStatus]) -> str:
    done = sum(1 for m in milestones if m.is_done)
    total = len(milestones)
    cur = next((m for m in milestones if not m.is_done), milestones[-1] if milestones else None)
    cur_id = cur.id if cur else "-"
    return f"RELEASE_STATUS milestones_done={done}/{total} next_milestone={cur_id}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=["md", "line", "json"], default="md")
    args = ap.parse_args()

    step_index = _load_json(STEP_INDEX_PATH)
    plan = _load_json(PLAN_PATH)
    completed = _completed_step_ids(step_index)

    state = _load_json(STATE_JSON_PATH) if STATE_JSON_PATH.exists() else {}
    blocked = _blocked_steps(state) if isinstance(state, dict) else []

    milestones_raw = plan.get("milestones", [])
    milestones = [_milestone_status(m, completed) for m in milestones_raw if isinstance(m, dict)]

    if args.format == "md":
        print(_fmt_md(milestones, blocked))
        return 0
    if args.format == "line":
        print(_fmt_line(milestones))
        return 0

    payload = {
        "milestones": [
            {
                "id": m.id,
                "name": m.name,
                "required_steps": m.required_steps,
                "done_steps": m.done_steps,
                "missing_steps": m.missing_steps,
                "is_done": m.is_done,
            }
            for m in milestones
        ],
        "blocked_steps": blocked,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
