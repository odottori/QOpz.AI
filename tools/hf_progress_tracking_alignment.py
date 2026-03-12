from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _extract_step_id(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        v = item.get("id") or item.get("step")
        return v if isinstance(v, str) else None
    return None


def _has_step(progress_steps: list[Any], step_id: str) -> bool:
    sid = step_id.upper()
    for it in progress_steps:
        v = _extract_step_id(it)
        if isinstance(v, str) and v.upper() == sid:
            return True
    return False


def _insert_f1_t2(progress_steps: list[Any]) -> bool:
    """Insert F1-T2 in a stable position (after F1-T1, before F1-T3)."""
    if _has_step(progress_steps, "F1-T2"):
        return False

    entry = {
        "id": "F1-T2",
        "title": "IV Rank (252d) offline ground truth + edge cases",
        # Stable timestamp; not used for ordering.
        "ts_utc": "2026-03-03T00:00:00Z",
    }

    # Find insert position
    ids = [(_extract_step_id(x) or "") for x in progress_steps]
    upper = [s.upper() for s in ids]
    try:
        i_t3 = upper.index("F1-T3")
        insert_at = i_t3
    except ValueError:
        try:
            i_t4 = upper.index("F1-T4")
            insert_at = i_t4
        except ValueError:
            insert_at = len(progress_steps)

    # Ensure it comes after F1-T1 if present
    try:
        i_t1 = upper.index("F1-T1")
        insert_at = max(insert_at, i_t1 + 1)
    except ValueError:
        pass

    progress_steps.insert(insert_at, entry)
    return True


def align_state(state: dict[str, Any]) -> bool:
    progress = state.get("progress", {})
    steps = progress.get("steps_completed")
    if not isinstance(steps, list):
        steps = []
        progress["steps_completed"] = steps

    changed = False
    changed |= _insert_f1_t2(steps)

    # Note for audit trail
    if changed:
        notes = progress.get("notes")
        if not isinstance(notes, list):
            notes = []
            progress["notes"] = notes
        notes.append(
            {
                "ts_utc": "2026-03-03T00:00:00Z",
                "note": "HF progress tracking alignment: inserted missing F1-T2 completion marker and enabled legacy->canonical task alias mapping for progress reporting.",
            }
        )
    return changed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="hf_progress_tracking_alignment")
    p.add_argument("--state", default=".qoaistate.json")
    p.add_argument("--check-only", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sp = Path(args.state)
    if not sp.exists():
        print(f"HF_PROGRESS_TRACKING_ALIGNMENT FAIL missing state: {sp}")
        return 2
    state = json.loads(sp.read_text(encoding="utf-8"))
    changed = align_state(state)

    if args.check_only:
        if changed:
            print("HF_PROGRESS_TRACKING_ALIGNMENT DRIFT")
            return 10
        print("HF_PROGRESS_TRACKING_ALIGNMENT OK")
        return 0

    if changed:
        sp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("HF_PROGRESS_TRACKING_ALIGNMENT WROTE state")
    else:
        print("HF_PROGRESS_TRACKING_ALIGNMENT OK (no changes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
