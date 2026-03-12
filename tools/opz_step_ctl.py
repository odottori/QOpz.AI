from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_dict(x: Any) -> Dict[str, Any]:
    if isinstance(x, dict):
        return x
    return {}


def _ensure_list(x: Any) -> List[Any]:
    if isinstance(x, list):
        return x
    return []


def _blocked_list(progress: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = progress.get("blocked_steps")
    items = _ensure_list(raw)
    out: List[Dict[str, Any]] = []
    for it in items:
        if isinstance(it, dict) and "id" in it:
            out.append(it)
        elif isinstance(it, str):
            out.append({"id": it})
    return out


def _completed_list(progress: Dict[str, Any]) -> List[Any]:
    return _ensure_list(progress.get("steps_completed"))


def _step_id_from_item(it: Any) -> Optional[str]:
    if isinstance(it, str):
        return it
    if isinstance(it, dict):
        v = it.get("id")
        return v if isinstance(v, str) else None
    return None


def _dump_json(path: Path, obj: Any) -> None:
    # Keep UTF-8 and stable formatting; newline at end.
    data = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(data + "\n", encoding="utf-8")


def freeze_step(state: Dict[str, Any], step_id: str, reason: str, advance_to: Optional[str]) -> bool:
    changed = False
    progress = _ensure_dict(state.get("progress"))
    state["progress"] = progress

    blocked = _blocked_list(progress)
    exists = next((b for b in blocked if b.get("id") == step_id), None)
    if exists is None:
        blocked.append({"id": step_id, "reason": reason, "ts_utc": _utc_now_iso()})
        changed = True
    else:
        if reason and exists.get("reason") != reason:
            exists["reason"] = reason
            changed = True
        if "ts_utc" not in exists:
            exists["ts_utc"] = _utc_now_iso()
            changed = True
    progress["blocked_steps"] = blocked

    if advance_to:
        cur_next = progress.get("next_step")
        if cur_next == step_id and advance_to != cur_next:
            progress["next_step"] = advance_to
            changed = True
    return changed


def unfreeze_step(state: Dict[str, Any], step_id: str) -> bool:
    progress = _ensure_dict(state.get("progress"))
    state["progress"] = progress
    blocked = _blocked_list(progress)
    new_blocked = [b for b in blocked if b.get("id") != step_id]
    if len(new_blocked) != len(blocked):
        progress["blocked_steps"] = new_blocked
        return True
    return False


def complete_step(state: Dict[str, Any], step_id: str, advance_to: Optional[str]) -> bool:
    changed = False
    progress = _ensure_dict(state.get("progress"))
    state["progress"] = progress

    items = _completed_list(progress)
    ids = [_step_id_from_item(it) for it in items]
    if step_id not in [i for i in ids if i]:
        # preserve legacy format: keep list[str] if it is list[str]
        if all(isinstance(it, str) for it in items):
            items.append(step_id)
        else:
            items.append({"id": step_id, "ts_utc": _utc_now_iso()})
        changed = True
    progress["steps_completed"] = items

    if advance_to:
        cur_next = progress.get("next_step")
        if cur_next == step_id and advance_to != cur_next:
            progress["next_step"] = advance_to
            changed = True
    return changed


def uncomplete_step(state: Dict[str, Any], step_id: str) -> bool:
    progress = _ensure_dict(state.get("progress"))
    state["progress"] = progress
    items = _completed_list(progress)
    new_items: List[Any] = []
    removed = False
    for it in items:
        sid = _step_id_from_item(it)
        if sid == step_id:
            removed = True
            continue
        new_items.append(it)
    if removed:
        progress["steps_completed"] = new_items
    return removed


def set_next(state: Dict[str, Any], step_id: str) -> bool:
    progress = _ensure_dict(state.get("progress"))
    state["progress"] = progress
    if progress.get("next_step") != step_id:
        progress["next_step"] = step_id
        return True
    return False


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="opz_step_ctl")
    p.add_argument("--state", default=".qoaistate.json")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--freeze", metavar="STEP_ID")
    g.add_argument("--unfreeze", metavar="STEP_ID")
    g.add_argument("--complete", metavar="STEP_ID")
    g.add_argument("--uncomplete", metavar="STEP_ID")
    g.add_argument("--set-next", metavar="STEP_ID")
    p.add_argument("--advance-to", default=None)
    p.add_argument("--reason", default="")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    sp = Path(args.state)
    if not sp.exists():
        raise SystemExit(f"state file not found: {sp}")

    state = json.loads(sp.read_text(encoding="utf-8"))
    changed = False

    if args.freeze:
        changed = freeze_step(state, args.freeze, args.reason or "", args.advance_to)
        print(f"OPZ_STEP_CTL freeze step={args.freeze} advance_to={args.advance_to or '-'} changed={changed}")
    elif args.unfreeze:
        changed = unfreeze_step(state, args.unfreeze)
        print(f"OPZ_STEP_CTL unfreeze step={args.unfreeze} changed={changed}")
    elif args.complete:
        changed = complete_step(state, args.complete, args.advance_to)
        print(f"OPZ_STEP_CTL complete step={args.complete} advance_to={args.advance_to or '-'} changed={changed}")
    elif args.uncomplete:
        changed = uncomplete_step(state, args.uncomplete)
        print(f"OPZ_STEP_CTL uncomplete step={args.uncomplete} changed={changed}")
    elif args.set_next:
        changed = set_next(state, args.set_next)
        print(f"OPZ_STEP_CTL set_next step={args.set_next} changed={changed}")

    if changed:
        _dump_json(sp, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
