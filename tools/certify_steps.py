from __future__ import annotations

import argparse
import json
from pathlib import Path

# When executed as "py tools\certify_steps.py", Python sets sys.path[0] = "tools/"
# so we import sibling module directly.
from reconcile_step_index import compute_step_index  # type: ignore


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="certify_steps")
    p.add_argument("--state", default=".qoaistate.json")
    p.add_argument("--step-index", default=".step_index.json")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sp = Path(args.state)
    ip = Path(args.step_index)

    if not sp.exists():
        print(f"CERTIFY_STEPS FAIL missing state: {sp}")
        return 2

    state = json.loads(sp.read_text(encoding="utf-8"))
    desired = compute_step_index(state)

    drift: list[str] = []
    if not ip.exists():
        drift.append(f"missing step index: {ip}")
        current = None
    else:
        try:
            current = json.loads(ip.read_text(encoding="utf-8"))
        except Exception:
            current = None
            drift.append(f"invalid JSON: {ip}")

    if current is not None and current != desired:
        for k in ["canonical_version", "next_step", "project_target_steps", "steps_completed"]:
            if current.get(k) != desired.get(k):
                drift.append(f"drift:{k} current={current.get(k)!r} desired={desired.get(k)!r}")

    # Basic state sanity
    progress = state.get("progress", {})
    next_step = progress.get("next_step")
    completed = set(desired.get("steps_completed") or [])
    if isinstance(next_step, str) and next_step in completed:
        drift.append(f"invalid state: next_step {next_step!r} is already in steps_completed")

    if drift:
        print("CERTIFY_STEPS DRIFT")
        for d in drift:
            print(f"- {d}")
        print("Hint: run py tools\\reconcile_step_index.py then py tools\\rebuild_manifest.py and py tools\\verify_manifest.py")
        return 10

    print(
        f"CERTIFY_STEPS OK next_step={desired.get('next_step')} "
        f"steps_completed={len(desired.get('steps_completed') or [])} "
        f"target_steps={desired.get('project_target_steps')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
