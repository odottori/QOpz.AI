from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".qoaistate.json"


def _write_json_crlf(path: Path, obj: Any) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    text = text.replace("\r\n", "\n").replace("\n", "\r\n") + "\r\n"
    path.write_text(text, encoding="utf-8", newline="")


def _ensure_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _ensure_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def normalize_state(state: Dict[str, Any]) -> bool:
    """
    Ensure canonical progress schema is present and consistent:
    - state["progress"] is a dict
    - state["next_step"] mirrors progress["next_step"] (human/legacy convenience)
    - if legacy root keys exist (blocked_steps, steps_completed), merge into progress and remove.
    """
    changed = False
    progress = _ensure_dict(state.get("progress"))
    if state.get("progress") is not progress:
        state["progress"] = progress
        changed = True

    # Merge legacy root steps_completed -> progress.steps_completed (best-effort)
    legacy_sc = state.get("steps_completed")
    if isinstance(legacy_sc, list):
        sc = _ensure_list(progress.get("steps_completed"))
        for it in legacy_sc:
            if it not in sc:
                sc.append(it)
        progress["steps_completed"] = sc
        state.pop("steps_completed", None)
        changed = True

    # Merge legacy root blocked_steps -> progress.blocked_steps (best-effort)
    legacy_bs = state.get("blocked_steps")
    if isinstance(legacy_bs, list):
        bs = _ensure_list(progress.get("blocked_steps"))
        for it in legacy_bs:
            bs.append(it)
        progress["blocked_steps"] = bs
        state.pop("blocked_steps", None)
        changed = True
    elif isinstance(legacy_bs, dict):
        bs = _ensure_list(progress.get("blocked_steps"))
        for sid, reason in legacy_bs.items():
            if isinstance(sid, str):
                bs.append({"id": sid, "reason": str(reason) if reason is not None else ""})
        progress["blocked_steps"] = bs
        state.pop("blocked_steps", None)
        changed = True

    # Mirror next_step
    p_next = progress.get("next_step")
    if isinstance(p_next, str) and p_next:
        if state.get("next_step") != p_next:
            state["next_step"] = p_next
            changed = True
    return changed


def main() -> int:
    if not STATE_PATH.exists():
        print("OPZ_STATE_NORMALIZE: SKIP (missing .qoaistate.json)")
        return 0
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"OPZ_STATE_NORMALIZE: FAIL cannot read state: {e}")
        return 2

    if not isinstance(state, dict):
        print("OPZ_STATE_NORMALIZE: FAIL state is not a JSON object")
        return 2

    changed = normalize_state(state)
    if changed:
        _write_json_crlf(STATE_PATH, state)
        print("OPZ_STATE_NORMALIZE: WROTE .qoaistate.json")
    else:
        print("OPZ_STATE_NORMALIZE: OK (no changes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
