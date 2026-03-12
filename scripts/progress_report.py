"""Progress reporter (D2.24, enhanced D2.42).

Provides a dual view of advancement:
- per phase (F1..F6) derived from completed steps (prefix mapping)
- per phase (F1..F6) against the *canonical task plan* (from .canonici/02_TEST.md)
- per D2 track (Domain2 timeline) completion (steps/target)

Supports JSON, Markdown, and single-line heartbeat output.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_TASK_ID_RE = re.compile(r"\b(F[1-6]-T[A-Za-z0-9_]+)\b")


_ALIAS_PATH_DEFAULT = Path("config/progress_task_aliases.json")


def _load_task_aliases(path: Path | None = None) -> dict[str, list[str]]:
    p = path or _ALIAS_PATH_DEFAULT
    try:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                out: dict[str, list[str]] = {}
                for k, v in data.items():
                    if isinstance(k, str) and isinstance(v, list) and all(isinstance(x, str) for x in v):
                        out[k] = v
                return out
    except Exception:
        pass
    return {}


@dataclass
class PhaseProgress:
    phase: str
    completed_steps: int
    latest_step: str | None


@dataclass
class PhasePlanProgress:
    phase: str
    completed_tasks: int
    total_tasks: int
    latest_task: str | None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_step_id(entry: dict[str, Any]) -> str | None:
    return entry.get("step") or entry.get("id")


def _phase_from_step(step_id: str) -> str | None:
    sid = (step_id or "").upper()
    if sid.startswith("F1"):
        return "F1"
    if sid.startswith("F2"):
        return "F2"
    if sid.startswith("F3") or sid.startswith("D2"):
        return "F3"
    if sid.startswith("F4"):
        return "F4"
    if sid.startswith("F5"):
        return "F5"
    if sid.startswith("F6"):
        return "F6"
    return None


def _compute_phase_completion(per_phase: list[dict[str, Any]]) -> dict[str, Any]:
    completed = sum(1 for r in per_phase if (r.get("completed_steps") or 0) > 0)
    total = len(per_phase)
    pct = round((completed / total) * 100, 1) if total else 0.0
    return {"completed": completed, "total": total, "percent": pct}


def _phase_order_index(phase: str | None) -> tuple[int, int]:
    order = ["F1", "F2", "F3", "F4", "F5", "F6"]
    if phase not in order:
        return 0, len(order)
    return order.index(phase) + 1, len(order)


def _resolve_project_target_steps(state: dict[str, Any], cli_target_steps: int | None = None) -> tuple[int, str]:
    """Resolve the D2 track target steps (legacy 'project target steps')."""
    if cli_target_steps is not None:
        return max(1, int(cli_target_steps)), "cli"

    progress = state.get("progress", {})
    if "project_target_steps" in progress:
        source = "progress.project_target_steps"
        state_value = progress.get("project_target_steps")
    elif "project_target_steps" in state:
        source = "project_target_steps"
        state_value = state.get("project_target_steps")
    else:
        source = "default"
        state_value = 30

    try:
        target = int(state_value)
    except (TypeError, ValueError):
        return 30, "default"
    return max(1, target), source


def _compute_project_completion(total_steps: int, target_steps: int = 30) -> dict[str, Any]:
    """Compute D2 track completion (steps/target)."""
    pct = round((total_steps / target_steps) * 100, 1) if target_steps else 0.0
    if pct > 100:
        pct = 100.0
    return {"completed_steps": total_steps, "target_steps": target_steps, "percent": pct}


def _load_phase_plan_tasks(canon_test_path: Path) -> dict[str, list[str]]:
    """Parse canonical task IDs (F*-T*) from canonici/02_TEST.md.

    Returns: phase -> sorted unique task IDs
    """
    if not canon_test_path.exists():
        return {p: [] for p in ("F1", "F2", "F3", "F4", "F5", "F6")}
    txt = canon_test_path.read_text(encoding="utf-8", errors="replace")
    ids = sorted(set(_TASK_ID_RE.findall(txt)))
    out: dict[str, list[str]] = {p: [] for p in ("F1", "F2", "F3", "F4", "F5", "F6")}
    for tid in ids:
        phase = tid.split("-", 1)[0]
        if phase in out:
            out[phase].append(tid)
    return out


def _extract_completed_task_ids(
    steps: list[dict[str, Any]],
    *,
    aliases: dict[str, list[str]] | None = None,
) -> tuple[set[str], dict[str, str]]:
    """Extract canonical task IDs mentioned in step summaries/titles/notes.

    Also supports alias mapping from legacy step ids (e.g., D2.3A) to canonical task ids (e.g., F3-T3).

    Returns:
      - completed task id set
      - latest task id per phase (based on step order)
    """
    completed: set[str] = set()
    latest_by_phase: dict[str, str] = {}
    aliases = aliases or {}

    for row in steps:
        # robust: stringify the whole entry (includes title/summary/notes etc.)
        blob = json.dumps(row, ensure_ascii=False)

        # 1) Canonical IDs mentioned directly in the log row
        for tid in _TASK_ID_RE.findall(blob):
            completed.add(tid)
            phase = tid.split("-", 1)[0]
            latest_by_phase[phase] = tid

        # 2) Alias IDs mapped from the step id itself
        step_id = (_extract_step_id(row) or "").strip()
        if step_id:
            for tid in aliases.get(step_id) or aliases.get(step_id.upper()) or []:
                completed.add(tid)
                phase = tid.split("-", 1)[0]
                latest_by_phase[phase] = tid

    return completed, latest_by_phase


def _compute_phase_plan_progress(
    plan: dict[str, list[str]],
    completed_tasks: set[str],
    latest_task_by_phase: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    per_phase: list[dict[str, Any]] = []
    total_tasks = 0
    total_completed = 0

    for phase in ("F1", "F2", "F3", "F4", "F5", "F6"):
        tasks = plan.get(phase, [])
        total = len(tasks)
        done = len([t for t in tasks if t in completed_tasks])
        total_tasks += total
        total_completed += done
        per_phase.append(
            asdict(
                PhasePlanProgress(
                    phase=phase,
                    completed_tasks=done,
                    total_tasks=total,
                    latest_task=latest_task_by_phase.get(phase),
                )
            )
        )

    pct = round((total_completed / total_tasks) * 100, 1) if total_tasks else 0.0
    completion = {
        "completed_tasks_total": total_completed,
        "total_tasks_total": total_tasks,
        "percent": pct,
    }
    return per_phase, completion


def build_progress_payload(state: dict[str, Any], *, project_target_steps: int | None = None) -> dict[str, Any]:
    progress = state.get("progress", {})
    steps = progress.get("steps_completed", [])

    # Phase progress by step prefix (legacy)
    by_phase: dict[str, list[str]] = {p: [] for p in ("F1", "F2", "F3", "F4", "F5", "F6")}
    for row in steps:
        step_id = _extract_step_id(row)
        if not step_id:
            continue
        phase = _phase_from_step(step_id)
        if phase:
            by_phase[phase].append(step_id)

    per_phase = [
        asdict(
            PhaseProgress(
                phase=phase,
                completed_steps=len(ids),
                latest_step=(ids[-1] if ids else None),
            )
        )
        for phase, ids in by_phase.items()
    ]

    total_steps = len([_extract_step_id(s) for s in steps if _extract_step_id(s)])

    phase_completion = _compute_phase_completion(per_phase)
    target_steps, target_source = _resolve_project_target_steps(state, project_target_steps)
    project_completion = _compute_project_completion(total_steps, target_steps)
    current_phase = _phase_from_step(progress.get("next_step", ""))
    current_idx, phase_total = _phase_order_index(current_phase)

    # Canonical plan progress (tasks)
    plan = _load_phase_plan_tasks(Path(".canonici/02_TEST.md"))
    aliases = _load_task_aliases()
    completed_tasks, latest_task_by_phase = _extract_completed_task_ids(steps, aliases=aliases)
    plan_per_phase, plan_completion = _compute_phase_plan_progress(plan, completed_tasks, latest_task_by_phase)

    return {
        "ts_utc": _utc_now_iso(),
        "project": state.get("project", "QuantOptionAI"),
        "next_step": progress.get("next_step"),
        # Legacy keys kept to avoid breaking healthcheck + existing tooling.
        "project_progress": {
            "steps_completed_total": total_steps,
            "latest_step": _extract_step_id(steps[-1]) if steps else None,
            "last_validation": progress.get("last_validation", {}),
            "completion": project_completion,
            "completion_target_source": target_source,
        },
        "phase_progress": per_phase,
        "phase_completion": phase_completion,
        "current_phase": {
            "phase": current_phase,
            "index": current_idx,
            "total": phase_total,
            "percent": round((current_idx / phase_total) * 100, 1) if phase_total and current_idx else 0.0,
        },
        # New: canonical plan completion
        "phase_plan_progress": plan_per_phase,
        "phase_plan_completion": plan_completion,
    }


def to_markdown(payload: dict[str, Any], *, compact: bool = False) -> str:
    lines: list[str] = []

    # Canonical plan (what the operator expects as "the project")
    plan_completion = payload.get("phase_plan_completion") or {"completed_tasks_total": 0, "total_tasks_total": 0, "percent": 0.0}
    lines.append("## PER FASI (piano canonico)")
    lines.append(
        f"- Avanzamento piano: `{plan_completion.get('completed_tasks_total', 0)}/{plan_completion.get('total_tasks_total', 0)}` task ({plan_completion.get('percent', 0)}%)"
    )

    if not compact:
        lines.append("| Fase | Task completate | Totale task | Ultimo task |")
        lines.append("|---|---:|---:|---|")
        for row in payload.get("phase_plan_progress", []):
            lines.append(f"| {row['phase']} | {row['completed_tasks']} | {row['total_tasks']} | {row['latest_task'] or '-'} |")

    # Legacy per-phase (prefix steps) — still useful
    phase_completion = payload.get("phase_completion") or _compute_phase_completion(payload.get("phase_progress", []))
    lines.append("")
    lines.append("## PER FASE (steps loggati)")
    if phase_completion:
        lines.append(
            f"- Fasi coperte: `{phase_completion.get('completed', 0)}/{phase_completion.get('total', 0)}` ({phase_completion.get('percent', 0)}%)"
        )

    current_phase = payload.get("current_phase") or {}
    if current_phase and current_phase.get("index"):
        lines.append(
            f"- Fase corrente: `{current_phase.get('index')}/{current_phase.get('total')}` ({current_phase.get('percent')}%) · `{current_phase.get('phase')}`"
        )

    if not compact:
        lines.append("| Fase | Steps completati | Ultimo step |")
        lines.append("|---|---:|---|")
        for row in payload.get("phase_progress", []):
            lines.append(f"| {row['phase']} | {row['completed_steps']} | {row['latest_step'] or '-'} |")

    # D2 track completion (was previously labeled as "project")
    proj = payload.get("project_progress", {})
    lines.append("")
    lines.append("## PER TRACK D2")
    completion = proj.get("completion") or _compute_project_completion(proj.get("steps_completed_total", 0))
    if completion:
        lines.append(
            f"- Avanzamento D2: `{completion.get('percent', 0)}%` ({completion.get('completed_steps', 0)}/{completion.get('target_steps', 0)} step)"
        )
    lines.append(f"- Project: `{payload.get('project', 'QuantOptionAI')}`")
    lines.append(f"- Next step: `{payload.get('next_step')}`")
    lines.append(f"- Target source: `{proj.get('completion_target_source', 'unknown')}`")
    if not compact:
        lines.append(f"- Steps completed total: `{proj.get('steps_completed_total')}`")
        lines.append(f"- Latest step: `{proj.get('latest_step')}`")
        last_val = proj.get("last_validation", {})
        if last_val:
            lines.append(f"- Last validation ts: `{last_val.get('ts_utc')}`")

    return "\n".join(lines)


def to_line(payload: dict[str, Any]) -> str:
    plan = payload.get("phase_plan_completion") or {}
    project_progress = payload.get("project_progress") or {}
    completion = project_progress.get("completion") or _compute_project_completion(project_progress.get("steps_completed_total", 0))
    target_source = project_progress.get("completion_target_source", "unknown")
    next_step = payload.get("next_step")

    return (
        f"PER FASI(plan) {plan.get('completed_tasks_total', 0)}/{plan.get('total_tasks_total', 0)} "
        f"({plan.get('percent', 0)}%) | "
        f"PER TRACK D2 {completion.get('percent', 0)}% ({completion.get('completed_steps', 0)}/{completion.get('target_steps', 0)}) "
        f"target_source={target_source} next={next_step}"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="progress_report")
    p.add_argument("--state", default=".qoaistate.json")
    p.add_argument("--format", choices=["json", "md", "line"], default="md")
    p.add_argument("--compact", action="store_true")
    p.add_argument("--project-target-steps", type=int, default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    payload = build_progress_payload(state, project_target_steps=args.project_target_steps)

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.format == "line":
        print(to_line(payload))
        return 0

    print(to_markdown(payload, compact=bool(args.compact)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
