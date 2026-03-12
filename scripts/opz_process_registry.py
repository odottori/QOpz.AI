from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REG_PATH = ROOT / "logs" / "codex_process_registry.json"
DEFAULT_OWNER = os.environ.get("OPZ_AGENT_OWNER", "assistant").strip() or "assistant"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _proc_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _load() -> dict[str, Any]:
    if not REG_PATH.exists():
        return {"version": 1, "updated_at_utc": _utcnow_iso(), "entries": []}
    try:
        data = json.loads(REG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "updated_at_utc": _utcnow_iso(), "entries": []}
    if not isinstance(data, dict):
        return {"version": 1, "updated_at_utc": _utcnow_iso(), "entries": []}
    if not isinstance(data.get("entries"), list):
        data["entries"] = []
    return data


def _save(data: dict[str, Any]) -> None:
    REG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at_utc"] = _utcnow_iso()
    REG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _upsert_entry(data: dict[str, Any], entry: dict[str, Any]) -> None:
    pid = int(entry["pid"])
    owner = str(entry.get("owner") or "")
    kept: list[dict[str, Any]] = []
    for e in data.get("entries", []):
        if int(e.get("pid") or -1) != pid or str(e.get("owner") or "") != owner:
            kept.append(e)
    kept.append(entry)
    data["entries"] = sorted(kept, key=lambda x: (str(x.get("owner") or ""), int(x.get("pid") or 0)))


def _match_owner(entry_owner: str, owner_filter: str) -> bool:
    if not owner_filter or owner_filter == "*":
        return True
    return str(entry_owner or "") == owner_filter


def cmd_register(args: argparse.Namespace) -> int:
    pid = int(args.pid)
    owner = str(args.owner or DEFAULT_OWNER).strip() or DEFAULT_OWNER
    data = _load()
    entry = {
        "pid": pid,
        "owner": owner,
        "role": str(args.role or "generic"),
        "command": str(args.command or ""),
        "cwd": str(args.cwd or ""),
        "started_at_utc": str(args.started_at_utc or _utcnow_iso()),
        "note": str(args.note or ""),
    }
    _upsert_entry(data, entry)
    _save(data)
    print(f"REGISTRY REGISTERED owner={owner} pid={pid} role={entry['role']}")
    return 0


def cmd_unregister(args: argparse.Namespace) -> int:
    pid = int(args.pid)
    owner = str(args.owner or "").strip()
    data = _load()
    before = len(data.get("entries", []))
    data["entries"] = [
        e
        for e in data.get("entries", [])
        if not (int(e.get("pid") or -1) == pid and _match_owner(str(e.get("owner") or ""), owner or "*"))
    ]
    _save(data)
    after = len(data.get("entries", []))
    print(f"REGISTRY UNREGISTER owner={owner or '*'} pid={pid} removed={before-after}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    owner = str(args.owner or "").strip()
    data = _load()
    out: list[dict[str, Any]] = []
    for e in data.get("entries", []):
        if not _match_owner(str(e.get("owner") or ""), owner or "*"):
            continue
        pid = int(e.get("pid") or 0)
        row = dict(e)
        row["alive"] = _proc_alive(pid)
        out.append(row)
    payload = {
        "registry_path": str(REG_PATH),
        "count": len(out),
        "owner_filter": owner or "*",
        "entries": out,
    }
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"REGISTRY count={payload['count']} owner={payload['owner_filter']} path={payload['registry_path']}")
        for e in out:
            print(f"- owner={e.get('owner')} pid={e.get('pid')} alive={e.get('alive')} role={e.get('role')} cmd={e.get('command')}")
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    owner = str(args.owner or "").strip()
    data = _load()
    kept: list[dict[str, Any]] = []
    removed = 0
    for e in data.get("entries", []):
        e_owner = str(e.get("owner") or "")
        pid = int(e.get("pid") or 0)
        if _match_owner(e_owner, owner or "*") and not _proc_alive(pid):
            removed += 1
            continue
        kept.append(e)
    data["entries"] = kept
    _save(data)
    print(f"REGISTRY CLEANUP owner={owner or '*'} removed={removed} kept={len(kept)}")
    return 0


def cmd_is_tracked(args: argparse.Namespace) -> int:
    pid = int(args.pid)
    owner = str(args.owner or "").strip()
    data = _load()
    hit = any(
        int(e.get("pid") or -1) == pid and _match_owner(str(e.get("owner") or ""), owner or "*")
        for e in data.get("entries", [])
    )
    print(f"REGISTRY TRACKED owner={owner or '*'} pid={pid} tracked={str(hit).lower()}")
    return 0 if hit else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Assistant-owned process registry")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_reg = sub.add_parser("register")
    p_reg.add_argument("--pid", required=True, type=int)
    p_reg.add_argument("--owner", default="")
    p_reg.add_argument("--role", default="generic")
    p_reg.add_argument("--command", default="")
    p_reg.add_argument("--cwd", default="")
    p_reg.add_argument("--started-at-utc", default="")
    p_reg.add_argument("--note", default="")
    p_reg.set_defaults(func=cmd_register)

    p_unreg = sub.add_parser("unregister")
    p_unreg.add_argument("--pid", required=True, type=int)
    p_unreg.add_argument("--owner", default="")
    p_unreg.set_defaults(func=cmd_unregister)

    p_list = sub.add_parser("list")
    p_list.add_argument("--owner", default="")
    p_list.add_argument("--format", choices=["line", "json"], default="line")
    p_list.set_defaults(func=cmd_list)

    p_cleanup = sub.add_parser("cleanup")
    p_cleanup.add_argument("--owner", default="")
    p_cleanup.set_defaults(func=cmd_cleanup)

    p_tr = sub.add_parser("is-tracked")
    p_tr.add_argument("--pid", required=True, type=int)
    p_tr.add_argument("--owner", default="")
    p_tr.set_defaults(func=cmd_is_tracked)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
