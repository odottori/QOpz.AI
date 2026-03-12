from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _extract_step_ids(steps_completed: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for item in steps_completed:
        if isinstance(item, str):
            out.append(item)
            continue
        if isinstance(item, dict):
            if "id" in item and isinstance(item["id"], str):
                out.append(item["id"])
                continue
            if "step" in item and isinstance(item["step"], str):
                out.append(item["step"])
                continue
    return out


def compute_step_index(state: dict[str, Any]) -> dict[str, Any]:
    progress = state.get("progress", {})
    steps_completed = progress.get("steps_completed", [])
    if not isinstance(steps_completed, list):
        steps_completed = []
    step_ids = _extract_step_ids(steps_completed)  # stable order as declared

    return {
        "project": state.get("project"),
        "canonical_version": state.get("canonical_version"),
        "next_step": progress.get("next_step"),
        "project_target_steps": progress.get("project_target_steps"),
        "steps_completed": step_ids,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="reconcile_step_index")
    p.add_argument("--state", default=".qoaistate.json")
    p.add_argument("--out", default=".step_index.json")
    p.add_argument("--check-only", action="store_true", help="Exit non-zero if drift is detected; do not write.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sp = Path(args.state)
    op = Path(args.out)

    if not sp.exists():
        print(f"ERROR: missing state: {sp}")
        return 2

    state = json.loads(sp.read_text(encoding="utf-8"))
    desired = compute_step_index(state)

    if op.exists():
        try:
            current = json.loads(op.read_text(encoding="utf-8"))
        except Exception:
            current = None
        if current == desired:
            print("RECONCILE_STEP_INDEX OK (already aligned)")
            return 0
        if args.check_only:
            print("RECONCILE_STEP_INDEX DRIFT")
            return 10

    if args.check_only:
        print("RECONCILE_STEP_INDEX DRIFT (missing index)")
        return 10

    op.write_text(json.dumps(desired, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RECONCILE_STEP_INDEX WROTE {op.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
