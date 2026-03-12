from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _has_step(steps_completed: list[Any], step_id: str) -> bool:
    for it in steps_completed:
        if isinstance(it, str) and it == step_id:
            return True
        if isinstance(it, dict):
            if it.get("id") == step_id or it.get("step") == step_id:
                return True
    return False


def main() -> int:
    sp = Path(".qoaistate.json")
    if not sp.exists():
        print("ERROR missing .qoaistate.json")
        return 2

    state = json.loads(sp.read_text(encoding="utf-8"))
    progress = state.get("progress", {})
    next_step = progress.get("next_step")

    # If we've already moved past F2-T3, do nothing.
    if isinstance(next_step, str) and next_step not in ("F2-T3", "F2-T2"):
        print(f"OK F2-T3 finalize noop next_step={next_step}")
        return 0

    steps_completed = progress.get("steps_completed", [])
    if not isinstance(steps_completed, list):
        steps_completed = []

    if not _has_step(steps_completed, "F2-T3"):
        steps_completed.append(
            {
                "id": "F2-T3",
                "title": "Regime-weighted risk scalar (classifier+HMM, hysteresis, EMA)",
                "ts_utc": _now_utc(),
            }
        )

    progress["steps_completed"] = steps_completed
    progress["next_step"] = "F2-T4"
    state["progress"] = progress

    sp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK F2-T3 finalize wrote .qoaistate.json next_step=F2-T4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
